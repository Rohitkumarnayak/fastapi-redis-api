
import io
from collections import Counter
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from openpyxl import Workbook
from openpyxl.styles import (
    Font,
    PatternFill,
    Border,
    Side,
    Alignment,
)
from openpyxl.chart import BarChart, PieChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension

from app.api.routes.auth import get_current_user
from app.database.connection import get_db
from app.models import Event


router = APIRouter(prefix="/reports", tags=["reports"])


# ============================================================
# HENXS MODERN EXCEL THEME
# ============================================================

COLORS = {
    "navy": "142B4A",
    "navy_dark": "0B1D33",
    "blue": "2563EB",
    "blue_light": "DBEAFE",
    "teal": "0D9488",
    "teal_light": "CCFBF1",
    "green": "16A34A",
    "green_light": "DCFCE7",
    "orange": "EA580C",
    "orange_light": "FFEDD5",
    "red": "DC2626",
    "red_light": "FEE2E2",
    "purple": "7C3AED",
    "purple_light": "EDE9FE",
    "background": "F3F6FA",
    "white": "FFFFFF",
    "text": "1E293B",
    "muted": "64748B",
    "border": "DCE4EE",
    "alternate": "F8FAFC",
}

THIN_SIDE = Side(style="thin", color=COLORS["border"])

STANDARD_BORDER = Border(
    left=THIN_SIDE,
    right=THIN_SIDE,
    top=THIN_SIDE,
    bottom=THIN_SIDE,
)


# ============================================================
# COMMON HELPERS
# ============================================================

def get_value(obj, field, default=None):
    return getattr(obj, field, default)


def clean_excel_value(value):
    """Convert Python values to safe Excel-compatible values."""

    if value is None:
        return ""

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if isinstance(value, date):
        return value

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    value = str(value)

    # Prevent spreadsheet formula injection.
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        value = "'" + value

    return value


def normalized(value):
    return str(value or "Unknown").strip().lower()


def inclusive_end_date(value):
    """
    If the caller supplies a date-only midnight value,
    include the complete end date.
    """
    if value and value.time() == time.min:
        return value + timedelta(days=1) - timedelta(microseconds=1)
    return value


def duration_seconds(event):
    created = get_value(event, "created_at")
    resolved = get_value(event, "resolved_at")

    if not isinstance(created, datetime):
        return None

    if not isinstance(resolved, datetime):
        return None

    if created.tzinfo is None and resolved.tzinfo is not None:
        created = created.replace(tzinfo=timezone.utc)

    elif created.tzinfo is not None and resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)

    try:
        seconds = (resolved - created).total_seconds()
        return seconds if seconds >= 0 else None
    except (TypeError, ValueError):
        return None


def format_duration(seconds):
    if seconds is None:
        return "N/A"

    seconds = int(seconds)

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h {minutes}m"

    if hours:
        return f"{hours}h {minutes}m"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


def apply_standard_cell_style(cell, alternate=False):
    cell.border = STANDARD_BORDER
    cell.font = Font(
        name="Aptos",
        size=10,
        color=COLORS["text"],
    )
    cell.alignment = Alignment(
        vertical="center",
        wrap_text=True,
    )

    if alternate:
        cell.fill = PatternFill(
            "solid",
            fgColor=COLORS["alternate"],
        )


# ============================================================
# WORKSHEET DESIGN HELPERS
# ============================================================

def setup_sheet(ws, tab_color=None):

    ws.sheet_view.showGridLines = False

    if tab_color:
        ws.sheet_properties.tabColor = tab_color

    ws.sheet_view.zoomScale = 90

    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.orientation = "landscape"

    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5


def add_sheet_header(ws, title, subtitle, end_column=12):

    setup_sheet(ws, COLORS["navy"])

    # Main title
    ws.merge_cells(
        start_row=1,
        start_column=1,
        end_row=2,
        end_column=end_column,
    )

    title_cell = ws.cell(1, 1, title)

    title_cell.fill = PatternFill(
        "solid",
        fgColor=COLORS["navy_dark"],
    )

    title_cell.font = Font(
        name="Aptos Display",
        size=23,
        bold=True,
        color=COLORS["white"],
    )

    title_cell.alignment = Alignment(
        horizontal="left",
        vertical="center",
        indent=1,
    )

    for row in (1, 2):
        for col in range(1, end_column + 1):
            ws.cell(row, col).fill = PatternFill(
                "solid",
                fgColor=COLORS["navy_dark"],
            )

    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 24

    # Subtitle
    ws.merge_cells(
        start_row=3,
        start_column=1,
        end_row=3,
        end_column=end_column,
    )

    subtitle_cell = ws.cell(3, 1, subtitle)
    subtitle_cell.font = Font(
        name="Aptos",
        size=10,
        italic=True,
        color=COLORS["muted"],
    )
    subtitle_cell.alignment = Alignment(
        vertical="center",
        indent=1,
    )

    ws.row_dimensions[3].height = 25
    ws.row_dimensions[4].height = 9


def style_table_header(ws, row, start_col, end_col):

    for col in range(start_col, end_col + 1):

        cell = ws.cell(row, col)

        cell.fill = PatternFill(
            "solid",
            fgColor=COLORS["navy"],
        )

        cell.font = Font(
            name="Aptos",
            size=10,
            bold=True,
            color=COLORS["white"],
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        cell.border = STANDARD_BORDER

    ws.row_dimensions[row].height = 34


def add_excel_table(ws, table_name, header_row, last_col, last_row):

    if last_row <= header_row:
        return

    ref = (
        f"A{header_row}:"
        f"{get_column_letter(last_col)}{last_row}"
    )

    table = Table(
        displayName=table_name,
        ref=ref,
    )

    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )

    ws.add_table(table)


def add_kpi_card(
    ws,
    start_col,
    title,
    value,
    color,
    light_color,
):

    end_col = start_col + 2

    # KPI title
    ws.merge_cells(
        start_row=6,
        start_column=start_col,
        end_row=6,
        end_column=end_col,
    )

    # KPI value
    ws.merge_cells(
        start_row=7,
        start_column=start_col,
        end_row=8,
        end_column=end_col,
    )

    for row in range(6, 9):
        for col in range(start_col, end_col + 1):
            ws.cell(row, col).border = STANDARD_BORDER

    title_cell = ws.cell(6, start_col, title)

    title_cell.fill = PatternFill(
        "solid",
        fgColor=color,
    )

    title_cell.font = Font(
        name="Aptos",
        size=10,
        bold=True,
        color=COLORS["white"],
    )

    title_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
    )

    value_cell = ws.cell(7, start_col, value)

    value_cell.fill = PatternFill(
        "solid",
        fgColor=light_color,
    )

    value_cell.font = Font(
        name="Aptos Display",
        size=22,
        bold=True,
        color=color,
    )

    value_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
    )

    for row in (7, 8):
        for col in range(start_col, end_col + 1):
            ws.cell(row, col).fill = PatternFill(
                "solid",
                fgColor=light_color,
            )

    ws.row_dimensions[6].height = 25
    ws.row_dimensions[7].height = 28
    ws.row_dimensions[8].height = 20


def add_section_heading(ws, row, title, end_col=6):

    ws.merge_cells(
        start_row=row,
        start_column=1,
        end_row=row,
        end_column=end_col,
    )

    cell = ws.cell(row, 1, title)

    cell.fill = PatternFill(
        "solid",
        fgColor=COLORS["blue_light"],
    )

    cell.font = Font(
        name="Aptos",
        size=12,
        bold=True,
        color=COLORS["navy"],
    )

    cell.alignment = Alignment(
        vertical="center",
        indent=1,
    )

    ws.row_dimensions[row].height = 27


# ============================================================
# CHART HELPER
# ============================================================

def add_chart(
    ws,
    source_ws,
    title,
    data_start_row,
    data_end_row,
    anchor,
    chart_type="bar",
):

    if data_end_row <= data_start_row:
        return

    if chart_type == "pie":

        chart = PieChart()

        chart.dataLabels = DataLabelList()
        chart.dataLabels.showPercent = True
        chart.dataLabels.showLeaderLines = True

    elif chart_type == "line":

        chart = LineChart()
        chart.style = 13
        chart.smooth = True

    else:

        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.legend = None

    chart.add_data(
        Reference(
            source_ws,
            min_col=2,
            min_row=data_start_row,
            max_row=data_end_row,
        ),
        titles_from_data=True,
    )

    chart.set_categories(
        Reference(
            source_ws,
            min_col=1,
            min_row=data_start_row + 1,
            max_row=data_end_row,
        )
    )

    chart.title = title
    chart.height = 8.2
    chart.width = 14.5

    chart.graphical_properties = None if chart_type == "pie" else chart.graphical_properties

    ws.add_chart(chart, anchor)


# ============================================================
# ANALYSIS WORKSHEET
# ============================================================

def create_analysis_sheet(
    wb,
    name,
    title,
    subtitle,
    data,
    chart_title,
    chart_type="bar",
):

    ws = wb.create_sheet(name)

    add_sheet_header(
        ws,
        title,
        subtitle,
        12,
    )

    headers = [
        "Category",
        "Event Count",
        "Share of Total",
    ]

    for col, header in enumerate(headers, 1):
        ws.cell(5, col, header)

    style_table_header(ws, 5, 1, 3)

    total = sum(count for _, count in data)

    for row_num, (label, count) in enumerate(data, 6):

        ws.cell(row_num, 1, clean_excel_value(label))
        ws.cell(row_num, 2, count)

        ws.cell(
            row_num,
            3,
            count / total if total else 0,
        )

        ws.cell(row_num, 3).number_format = "0.0%"

        for col in range(1, 4):
            apply_standard_cell_style(
                ws.cell(row_num, col),
                alternate=(row_num % 2 == 0),
            )

        ws.row_dimensions[row_num].height = 25

    last_row = 5 + len(data)

    add_excel_table(
        ws,
        "Tbl" + "".join(c for c in name if c.isalnum()),
        5,
        3,
        last_row,
    )

    if data:

        chart = BarChart() if chart_type == "bar" else PieChart()

        if chart_type == "pie":
            chart.dataLabels = DataLabelList()
            chart.dataLabels.showPercent = True
        else:
            chart.type = "bar"
            chart.style = 10
            chart.legend = None

        chart.add_data(
            Reference(
                ws,
                min_col=2,
                min_row=5,
                max_row=last_row,
            ),
            titles_from_data=True,
        )

        chart.set_categories(
            Reference(
                ws,
                min_col=1,
                min_row=6,
                max_row=last_row,
            )
        )

        chart.title = chart_title
        chart.height = 9
        chart.width = 16

        ws.add_chart(chart, "E5")

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 19
    ws.column_dimensions["C"].width = 20

    ws.freeze_panes = "A6"

    return ws


# ============================================================
# FILTERED EVENT QUERY
# ============================================================

def fetch_filtered_events(
    db,
    start_date=None,
    end_date=None,
    severity=None,
    status=None,
    camera_id=None,
):

    query = select(Event)

    if start_date:
        query = query.where(
            Event.created_at >= start_date
        )

    if end_date:
        query = query.where(
            Event.created_at <= inclusive_end_date(end_date)
        )

    if severity:
        query = query.where(
            func.lower(Event.severity) == severity.lower()
        )

    if status:
        query = query.where(
            func.lower(Event.status) == status.lower()
        )

    if camera_id is not None:
        query = query.where(
            Event.camera_id == camera_id
        )

    return db.scalars(
        query.order_by(desc(Event.created_at))
    ).all()


# ============================================================
# EXISTING SUMMARY ENDPOINT
# ============================================================

@router.get("/summary")
def report_summary(
    start_date: datetime,
    end_date: datetime,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before end_date",
        )

    end_date = inclusive_end_date(end_date)

    filters = (
        Event.created_at >= start_date,
        Event.created_at <= end_date,
    )

    total = db.scalar(
        select(func.count(Event.id)).where(*filters)
    ) or 0

    severity_rows = db.execute(
        select(
            Event.severity,
            func.count(Event.id),
        )
        .where(*filters)
        .group_by(Event.severity)
    ).all()

    status_rows = db.execute(
        select(
            Event.status,
            func.count(Event.id),
        )
        .where(*filters)
        .group_by(Event.status)
    ).all()

    type_rows = db.execute(
        select(
            Event.event_type,
            func.count(Event.id),
        )
        .where(*filters)
        .group_by(Event.event_type)
    ).all()

    camera_rows = db.execute(
        select(
            Event.camera_id,
            func.count(Event.id),
        )
        .where(*filters)
        .group_by(Event.camera_id)
    ).all()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_events": total,

        "by_severity": [
            {"name": key, "count": value}
            for key, value in severity_rows
        ],

        "by_status": [
            {"name": key, "count": value}
            for key, value in status_rows
        ],

        "by_event_type": [
            {"name": key, "count": value}
            for key, value in type_rows
        ],

        "by_camera": [
            {"name": key, "count": value}
            for key, value in camera_rows
        ],
    }


# ============================================================
# PREMIUM EXCEL EXPORT ENDPOINT
# ============================================================

@router.get("/events.xlsx")
def export_events_excel(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    camera_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    if start_date and end_date and start_date > inclusive_end_date(end_date):
        raise HTTPException(
            status_code=422,
            detail="Invalid date range",
        )

    # --------------------------------------------------------
    # FETCH FILTERED EVENTS
    # --------------------------------------------------------

    events = fetch_filtered_events(
        db=db,
        start_date=start_date,
        end_date=end_date,
        severity=severity,
        status=status,
        camera_id=camera_id,
    )

    # --------------------------------------------------------
    # KPI CALCULATIONS
    # --------------------------------------------------------

    total = len(events)

    assigned = [
        event for event in events
        if normalized(get_value(event, "status")) == "assigned"
    ]

    resolved = [
        event for event in events
        if normalized(get_value(event, "status")) == "resolved"
    ]

    pending = [
        event for event in events
        if normalized(get_value(event, "status")) in ("new", "pending")
    ]

    acknowledged = [
        event for event in events
        if get_value(event, "acknowledged_at") is not None
    ]

    high_severity = [
        event for event in events
        if normalized(get_value(event, "severity")) == "high"
    ]

    durations = [
        duration_seconds(event)
        for event in resolved
    ]

    durations = [
        value for value in durations
        if value is not None
    ]

    average_resolution = (
        sum(durations) / len(durations)
        if durations else None
    )

    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------

    severity_counts = Counter(
        str(get_value(event, "severity") or "Unknown").title()
        for event in events
    )

    status_counts = Counter(
        str(get_value(event, "status") or "Unknown").title()
        for event in events
    )

    type_counts = Counter(
        str(get_value(event, "event_type") or "Unknown")
        for event in events
    )

    camera_counts = Counter(
        str(get_value(event, "camera_id") or "Unknown")
        for event in events
    )

    zone_counts = Counter(
        str(get_value(event, "zone") or "Unknown")
        for event in events
    )

    hourly_counts = Counter()

    for event in events:
        created = get_value(event, "created_at")

        if isinstance(created, datetime):
            hourly_counts[created.hour] += 1

    hourly_data = [
        (f"{hour:02d}:00", hourly_counts.get(hour, 0))
        for hour in range(24)
    ]

    # --------------------------------------------------------
    # CREATE WORKBOOK
    # --------------------------------------------------------

    wb = Workbook()

    dashboard = wb.active
    dashboard.title = "Executive Dashboard"

    generated_at = datetime.now().astimezone()

    period_text = (
        f"{start_date.strftime('%d %b %Y') if start_date else 'All dates'}"
        f" - "
        f"{end_date.strftime('%d %b %Y') if end_date else 'Present'}"
    )

    add_sheet_header(
        dashboard,
        "HENXS | GARBAGE ANALYTICS",
        f"Executive Report  |  {period_text}  |  Generated {generated_at:%d %b %Y, %H:%M}",
        12,
    )

    # --------------------------------------------------------
    # KPI CARDS
    # --------------------------------------------------------

    add_kpi_card(
        dashboard,
        1,
        "TOTAL DETECTED EVENTS",
        total,
        COLORS["blue"],
        COLORS["blue_light"],
    )

    add_kpi_card(
        dashboard,
        4,
        "ASSIGNED EVENTS",
        len(assigned),
        COLORS["orange"],
        COLORS["orange_light"],
    )

    add_kpi_card(
        dashboard,
        7,
        "RESOLVED EVENTS",
        len(resolved),
        COLORS["green"],
        COLORS["green_light"],
    )

    add_kpi_card(
        dashboard,
        10,
        "AVG. RESOLUTION TIME",
        format_duration(average_resolution),
        COLORS["teal"],
        COLORS["teal_light"],
    )

    # --------------------------------------------------------
    # SECONDARY KPI ROW
    # --------------------------------------------------------

    add_section_heading(
        dashboard,
        10,
        "OPERATIONAL OVERVIEW",
        12,
    )

    secondary_metrics = [
        ("High Severity", len(high_severity), COLORS["red"]),
        ("Acknowledged", len(acknowledged), COLORS["purple"]),
        ("Pending", len(pending), COLORS["orange"]),
        ("Resolved With Time Data", len(durations), COLORS["teal"]),
    ]

    metric_positions = [1, 4, 7, 10]

    for (label, value, color), col in zip(
        secondary_metrics,
        metric_positions,
    ):

        dashboard.merge_cells(
            start_row=11,
            start_column=col,
            end_row=11,
            end_column=col + 2,
        )

        dashboard.merge_cells(
            start_row=12,
            start_column=col,
            end_row=12,
            end_column=col + 2,
        )

        label_cell = dashboard.cell(11, col, label)
        label_cell.font = Font(
            bold=True,
            color=COLORS["muted"],
            size=10,
        )
        label_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        value_cell = dashboard.cell(12, col, value)
        value_cell.font = Font(
            bold=True,
            color=color,
            size=17,
        )
        value_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        for row in (11, 12):
            for c in range(col, col + 3):
                dashboard.cell(row, c).border = STANDARD_BORDER

    dashboard.row_dimensions[11].height = 24
    dashboard.row_dimensions[12].height = 32

    # --------------------------------------------------------
    # CHART SOURCE DATA - HIDDEN WORKSHEET
    # --------------------------------------------------------

    source_ws = wb.create_sheet("_ChartData")
    source_ws.sheet_state = "hidden"

    chart_definitions = [
        (
            "Severity Distribution",
            list(severity_counts.items()),
            "pie",
            "A15",
        ),
        (
            "Event Status Distribution",
            list(status_counts.items()),
            "bar",
            "G15",
        ),
        (
            "Top Event Types",
            type_counts.most_common(10),
            "bar",
            "A32",
        ),
        (
            "Hourly Detection Trend",
            hourly_data,
            "line",
            "G32",
        ),
    ]

    for index, (title, data, chart_type, anchor) in enumerate(
        chart_definitions
    ):

        start_row = index * 30 + 1

        source_ws.cell(start_row, 1, "Category")
        source_ws.cell(start_row, 2, "Count")

        for row_num, (label, count) in enumerate(
            data,
            start_row + 1,
        ):
            source_ws.cell(
                row_num,
                1,
                clean_excel_value(label),
            )
            source_ws.cell(
                row_num,
                2,
                count,
            )

        if data:
            add_chart(
                dashboard,
                source_ws,
                title,
                start_row,
                start_row + len(data),
                anchor,
                chart_type,
            )

    # --------------------------------------------------------
    # DASHBOARD WIDTH AND HEIGHT
    # --------------------------------------------------------

    for col in range(1, 13):
        dashboard.column_dimensions[
            get_column_letter(col)
        ].width = 15

    dashboard.row_dimensions[14].height = 12
    dashboard.freeze_panes = "A6"

    # --------------------------------------------------------
    # EVENT REGISTER
    # --------------------------------------------------------

    ws = wb.create_sheet("Event Register")

    add_sheet_header(
        ws,
        "HENXS | EVENT REGISTER",
        "Detailed event history with assignment and resolution information",
        25,
    )

    fields = [
        ("Event ID", "id"),
        ("Event Type", "event_type"),
        ("Camera ID", "camera_id"),
        ("Zone", "zone"),
        ("Description", "message"),
        ("Severity", "severity"),
        ("Status", "status"),
        ("Assigned To", "assigned_to"),
        ("Assigned By", "assigned_by"),
        ("Assigned At", "assigned_at"),
        ("Acknowledged By", "acknowledged_by"),
        ("Acknowledged At", "acknowledged_at"),
        ("Resolved By", "resolved_by"),
        ("Resolved At", "resolved_at"),
        ("Resolution Notes", "resolution_notes"),
        ("Detection Latitude", "latitude"),
        ("Detection Longitude", "longitude"),
        ("Detection Time", "created_at"),
        ("Resolution Latitude", "resolve_latitude"),
        ("Resolution Longitude", "resolve_longitude"),
        ("Resolution Message", "resolve_message"),
        ("Detection Image Available", "image_base64"),
        ("Detection Image MIME", "image_mime_type"),
        ("Resolution Image Available", "resolve_image_base64"),
        ("Resolution Image MIME", "resolve_image_mime_type"),
    ]

    duration_col = len(fields) + 1

    for col, (label, field) in enumerate(fields, 1):
        ws.cell(5, col, label)

    ws.cell(5, duration_col, "Resolution Duration")

    style_table_header(ws, 5, 1, duration_col)

    for row_num, event in enumerate(events, 6):

        for col, (label, field) in enumerate(fields, 1):

            value = get_value(event, field)

            if field in ("image_base64", "resolve_image_base64"):
                value = bool(value)

            value = clean_excel_value(value)

            cell = ws.cell(row_num, col, value)

            apply_standard_cell_style(
                cell,
                alternate=(row_num % 2 == 0),
            )

            if field in (
                "created_at",
                "assigned_at",
                "acknowledged_at",
                "resolved_at",
            ) and isinstance(value, datetime):

                cell.number_format = "dd-mmm-yyyy hh:mm:ss"

        seconds = duration_seconds(event)

        duration_cell = ws.cell(
            row_num,
            duration_col,
            format_duration(seconds),
        )

        apply_standard_cell_style(
            duration_cell,
            alternate=(row_num % 2 == 0),
        )

        ws.row_dimensions[row_num].height = 34

    last_row = 5 + len(events)

    add_excel_table(
        ws,
        "HENXSEventRegister",
        5,
        duration_col,
        last_row,
    )

    # Severity conditional formatting
    severity_letter = get_column_letter(6)

    ws.conditional_formatting.add(
        f"{severity_letter}6:{severity_letter}{max(last_row, 6)}",
        FormulaRule(
            formula=['LOWER(F6)="high"'],
            fill=PatternFill("solid", fgColor=COLORS["red_light"]),
            font=Font(color=COLORS["red"], bold=True),
        ),
    )

    ws.conditional_formatting.add(
        f"{severity_letter}6:{severity_letter}{max(last_row, 6)}",
        FormulaRule(
            formula=['LOWER(F6)="medium"'],
            fill=PatternFill("solid", fgColor=COLORS["orange_light"]),
            font=Font(color=COLORS["orange"], bold=True),
        ),
    )

    ws.freeze_panes = "A6"

    # Practical widths for readable content
    column_widths = {
        1: 15,
        2: 20,
        3: 13,
        4: 20,
        5: 42,
        6: 14,
        7: 15,
        8: 22,
        9: 18,
        10: 21,
        11: 20,
        12: 21,
        13: 20,
        14: 21,
        15: 42,
        16: 18,
        17: 18,
        18: 22,
        19: 18,
        20: 18,
        21: 40,
        22: 20,
        23: 22,
        24: 22,
        25: 24,
        26: 22,
    }

    for col, width in column_widths.items():
        ws.column_dimensions[
            get_column_letter(col)
        ].width = width

    # --------------------------------------------------------
    # ANALYSIS SHEETS
    # --------------------------------------------------------

    create_analysis_sheet(
        wb,
        "Severity Analysis",
        "HENXS | SEVERITY ANALYSIS",
        "Distribution of events by severity level",
        severity_counts.most_common(),
        "Severity Distribution",
        "pie",
    )

    create_analysis_sheet(
        wb,
        "Status Analysis",
        "HENXS | STATUS ANALYSIS",
        "Current operational status of detected events",
        status_counts.most_common(),
        "Event Status Distribution",
        "bar",
    )

    create_analysis_sheet(
        wb,
        "Event Type Analysis",
        "HENXS | EVENT TYPE ANALYSIS",
        "Most frequently detected event categories",
        type_counts.most_common(),
        "Event Type Distribution",
        "bar",
    )

    create_analysis_sheet(
        wb,
        "Camera Analysis",
        "HENXS | CAMERA ANALYSIS",
        "Event distribution across cameras",
        camera_counts.most_common(),
        "Camera-wise Events",
        "bar",
    )

    create_analysis_sheet(
        wb,
        "Zone Analysis",
        "HENXS | ZONE ANALYSIS",
        "Event distribution across configured zones",
        zone_counts.most_common(),
        "Zone-wise Events",
        "pie",
    )

    # --------------------------------------------------------
    # TASK PERFORMANCE
    # --------------------------------------------------------

    ws = wb.create_sheet("Task Performance")

    add_sheet_header(
        ws,
        "HENXS | TASK PERFORMANCE",
        "Assignment, acknowledgement and resolution metrics",
        8,
    )

    task_headers = [
        "Performance Metric",
        "Event Count",
        "Percentage",
    ]

    for col, header in enumerate(task_headers, 1):
        ws.cell(5, col, header)

    style_table_header(ws, 5, 1, 3)

    task_metrics = [
        ("Total Detected Events", total),
        ("Assigned Events", len(assigned)),
        ("Acknowledged Events", len(acknowledged)),
        ("Resolved Events", len(resolved)),
        ("Pending Events", len(pending)),
        ("High Severity Events", len(high_severity)),
        ("Events With Resolution Time", len(durations)),
    ]

    for row_num, (label, count) in enumerate(task_metrics, 6):

        ws.cell(row_num, 1, label)
        ws.cell(row_num, 2, count)

        ws.cell(
            row_num,
            3,
            count / total if total else 0,
        )

        ws.cell(row_num, 3).number_format = "0.0%"

        for col in range(1, 4):
            apply_standard_cell_style(
                ws.cell(row_num, col),
                alternate=(row_num % 2 == 0),
            )

        ws.row_dimensions[row_num].height = 27

    add_excel_table(
        ws,
        "HENXSTaskPerformance",
        5,
        3,
        5 + len(task_metrics),
    )

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 20

    # --------------------------------------------------------
    # HOURLY ANALYSIS
    # --------------------------------------------------------

    ws = wb.create_sheet("Hourly Analysis")

    add_sheet_header(
        ws,
        "HENXS | HOURLY DETECTION ANALYSIS",
        "Event detection activity across the 24-hour period",
        10,
    )

    hourly_headers = [
        "Hour",
        "Event Count",
        "Share of Total",
    ]

    for col, header in enumerate(hourly_headers, 1):
        ws.cell(5, col, header)

    style_table_header(ws, 5, 1, 3)

    for row_num, (hour, count) in enumerate(hourly_data, 6):

        ws.cell(row_num, 1, hour)
        ws.cell(row_num, 2, count)

        ws.cell(
            row_num,
            3,
            count / total if total else 0,
        )

        ws.cell(row_num, 3).number_format = "0.0%"

        for col in range(1, 4):
            apply_standard_cell_style(
                ws.cell(row_num, col),
                alternate=(row_num % 2 == 0),
            )

        ws.row_dimensions[row_num].height = 25

    add_excel_table(
        ws,
        "HENXSHourlyAnalysis",
        5,
        3,
        29,
    )

    hourly_chart = LineChart()
    hourly_chart.title = "Hourly Detection Trend"
    hourly_chart.style = 13
    hourly_chart.height = 10
    hourly_chart.width = 18
    hourly_chart.smooth = True

    hourly_chart.add_data(
        Reference(
            ws,
            min_col=2,
            min_row=5,
            max_row=29,
        ),
        titles_from_data=True,
    )

    hourly_chart.set_categories(
        Reference(
            ws,
            min_col=1,
            min_row=6,
            max_row=29,
        )
    )

    ws.add_chart(hourly_chart, "E5")

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 20

    # --------------------------------------------------------
    # FINAL WORKBOOK SETTINGS
    # --------------------------------------------------------

    for sheet in wb.worksheets:

        sheet.sheet_view.showGridLines = False

        sheet.sheet_properties.pageSetUpPr.fitToPage = True

        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.page_setup.orientation = "landscape"

        sheet.page_margins.left = 0.25
        sheet.page_margins.right = 0.25
        sheet.page_margins.top = 0.5
        sheet.page_margins.bottom = 0.5

    wb.active = 0

    # --------------------------------------------------------
    # RETURN EXCEL FILE
    # --------------------------------------------------------

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = "HENXS_Garbage_Analytics_Report.xlsx"

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Cache-Control": "no-store",
        },
    )
