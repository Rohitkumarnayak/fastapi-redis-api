
import aiosmtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


async def send_email(
    recipients: list[str],
    subject: str,
    message: str,
    attachments: list[dict] | None = None,
    html: bool = False
):
    email = EmailMessage()

    email["From"] = formataddr((
        settings.smtp_from_name,
        settings.smtp_from_email
    ))

    # Hide recipients from each other
    email["To"] = "undisclosed-recipients:;"
    email["Subject"] = subject

    if html:
        email.set_content(
            "Please view this email in an HTML-compatible client."
        )
        email.add_alternative(message, subtype="html")
    else:
        email.set_content(message)

    # Add attachments
    for attachment in attachments or []:
        email.add_attachment(
            attachment["content"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["filename"]
        )

    await aiosmtplib.send(
        email,
        recipients=recipients,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        timeout=30
    )

    return True
