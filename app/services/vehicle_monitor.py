"""Background vehicle connectivity monitor and journey-report delivery.

The worker uses its own SQLAlchemy sessions and never runs inside an API request.
"""
import asyncio
import html
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import SessionLocal
from app.models import Device, Event, VehicleJourneyReport
from app.services.email_service import send_email

logger = logging.getLogger(__name__)


def _aware_utc(value: datetime) -> datetime:
    # PostgreSQL returns timezone-aware values; tolerate legacy naive values.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _build_report(db: Session, device: Device, offline_at: datetime) -> VehicleJourneyReport:
    online_at = _aware_utc(device.last_online_at or device.last_seen_at or offline_at)
    event_query = select(Event).where(
        Event.camera_id == device.device_id,
        Event.created_at >= online_at,
        Event.created_at <= offline_at,
    )
    events = db.scalars(event_query).all()

    breakdown = {}
    for event in events:
        key = event.event_type or "Unknown"
        breakdown[key] = breakdown.get(key, 0) + 1

    statuses = [(event.status or "").strip().lower() for event in events]
    total_detections = sum(max(int(event.object_count or 0), 0) for event in events)

    return VehicleJourneyReport(
        device_id=device.device_id,
        device_name=device.name,
        online_at=online_at,
        offline_at=offline_at,
        duration_seconds=max(int((offline_at - online_at).total_seconds()), 0),
        total_detections=total_detections,
        total_events=len(events),
        assigned_events=sum(
            event.assigned_at is not None or status == "assigned"
            for event, status in zip(events, statuses)
        ),
        acknowledged_events=sum(
            event.acknowledged_at is not None or status == "acknowledged"
            for event, status in zip(events, statuses)
        ),
        resolved_events=sum(
            event.resolved_at is not None or status in {"resolved", "closed"}
            for event, status in zip(events, statuses)
        ),
        event_breakdown=breakdown,
        recipients=list(device.email_recipients or []),
        email_sent=False,
    )


def _email_body(report: VehicleJourneyReport) -> str:
    duration = timedelta(seconds=report.duration_seconds)
    rows = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{count}</td></tr>"
        for name, count in sorted((report.event_breakdown or {}).items())
    ) or "<tr><td colspan='2'>No events recorded</td></tr>"
    return f"""
    <html><body>
      <h2>Vehicle Journey Offline Report</h2>
      <table cellpadding="6" cellspacing="0" border="1">
        <tr><td><b>Vehicle</b></td><td>{html.escape(report.device_name)} ({html.escape(report.device_id)})</td></tr>
        <tr><td><b>Online since</b></td><td>{report.online_at.isoformat()}</td></tr>
        <tr><td><b>Went offline</b></td><td>{report.offline_at.isoformat()}</td></tr>
        <tr><td><b>Journey duration</b></td><td>{duration}</td></tr>
        <tr><td><b>Total detected objects</b></td><td>{report.total_detections}</td></tr>
        <tr><td><b>Total events</b></td><td>{report.total_events}</td></tr>
        <tr><td><b>Assigned</b></td><td>{report.assigned_events}</td></tr>
        <tr><td><b>Acknowledged</b></td><td>{report.acknowledged_events}</td></tr>
        <tr><td><b>Resolved / closed</b></td><td>{report.resolved_events}</td></tr>
      </table>
      <h3>Event type breakdown</h3>
      <table cellpadding="6" cellspacing="0" border="1">
        <tr><th>Event type</th><th>Count</th></tr>{rows}
      </table>
    </body></html>
    """


async def _deliver_report(report_id: int, recipients: list[str]) -> None:
    if not recipients:
        return

    with SessionLocal() as db:
        report = db.get(VehicleJourneyReport, report_id)
        if report is None:
            return
        subject = f"Vehicle Offline Report - {report.device_name} ({report.device_id})"
        body = _email_body(report)

    try:
        await send_email(
            recipients=recipients,
            subject=subject,
            message=body,
            html=True,
        )
        with SessionLocal() as db:
            report = db.get(VehicleJourneyReport, report_id)
            if report:
                report.email_sent = True
                report.email_error = None
                db.commit()
        logger.info("Vehicle offline report %s emailed to %s", report_id, len(recipients))
    except Exception as exc:
        logger.exception("Failed to email vehicle report %s", report_id)
        with SessionLocal() as db:
            report = db.get(VehicleJourneyReport, report_id)
            if report:
                report.email_error = str(exc)[:2000]
                db.commit()


def check_vehicles_once() -> int:
    """Mark stale vehicle devices offline and create one journey report each."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(settings.vehicle_offline_after_seconds, 1))
    pending_emails: list[tuple[int, list[str]]] = []
    changed = 0

    with SessionLocal() as db:
        try:
            # FOR UPDATE SKIP LOCKED prevents duplicate processing if the API
            # is accidentally run with multiple worker processes.
            stale_devices = db.scalars(
                select(Device)
                .where(
                    Device.enabled.is_(True),
                    func.lower(Device.device_type) == "vehicle",
                    func.lower(Device.status).in_(["active", "online"]),
                    Device.last_seen_at.is_not(None),
                    Device.last_seen_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
            ).all()

            for device in stale_devices:
                device.status = "offline"
                device.last_offline_at = now
                report = _build_report(db, device, now)
                db.add(report)
                db.flush()
                if device.email_notifications_enabled and device.email_recipients:
                    pending_emails.append((report.id, list(device.email_recipients)))
                changed += 1

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Vehicle status monitoring cycle failed")
            return 0

    # Email is sent outside the DB transaction; SMTP latency cannot hold locks.
    for report_id, recipients in pending_emails:
        try:
            asyncio.run(_deliver_report(report_id, recipients))
        except Exception:
            logger.exception("Unexpected report delivery error for report %s", report_id)

    return changed


class VehicleMonitor:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="vehicle-status-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Vehicle monitor started (offline threshold=%ss, interval=%ss)",
            settings.vehicle_offline_after_seconds,
            settings.vehicle_monitor_interval_seconds,
        )

    def _run(self) -> None:
        interval = max(settings.vehicle_monitor_interval_seconds, 5)
        while not self._stop.wait(interval):
            check_vehicles_once()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None


vehicle_monitor = VehicleMonitor()
