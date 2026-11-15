import json
import mimetypes

from email_validator import validate_email, EmailNotValidError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.api.routes.auth import require_admin
from app.models import User
from app.services.email_service import send_email


router = APIRouter(
    prefix="/email",
    tags=["Email Service"]
)

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 20 * 1024 * 1024
MAX_RECIPIENTS = 50


@router.post("/send")
async def send_email_api(
    recipients: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    html: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_admin)
):

    # Parse recipients
    try:
        recipient_list = json.loads(recipients)

        if not isinstance(recipient_list, list):
            raise ValueError()

    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Recipients must be a JSON list of email addresses"
        )

    if not recipient_list:
        raise HTTPException(
            status_code=422,
            detail="At least one recipient is required"
        )

    if len(recipient_list) > MAX_RECIPIENTS:
        raise HTTPException(
            status_code=422,
            detail="Maximum 50 recipients allowed"
        )

    # Validate recipients
    validated = []

    for address in recipient_list:
        if not isinstance(address, str):
            raise HTTPException(422, "Invalid recipient")

        try:
            clean_email = validate_email(
                address.strip(),
                check_deliverability=False
            ).normalized
            validated.append(clean_email)

        except EmailNotValidError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid email address: {address}"
            )

    # Remove duplicate email addresses
    validated = list(dict.fromkeys(validated))

    if not subject.strip() or not message.strip():
        raise HTTPException(
            status_code=422,
            detail="Subject and message cannot be empty"
        )

    attachments = []
    total_size = 0

    # Process optional attachments
    for file in files or []:

        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"{file.filename} exceeds 10 MB"
            )

        total_size += len(content)

        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Total attachment size exceeds 20 MB"
            )

        mime_type, _ = mimetypes.guess_type(
            file.filename or ""
        )

        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        attachments.append({
            "filename": file.filename or "attachment",
            "content": content,
            "maintype": maintype,
            "subtype": subtype
        })

    # Send email
    try:

        await send_email(
            recipients=validated,
            subject=subject,
            message=message,
            attachments=attachments,
            html=html
        )

        return {
            "success": True,
            "message": "Email sent successfully",
            "total_recipients": len(validated),
            "attachments": len(attachments)
        }

    except Exception:
        import logging

        logging.exception("Email delivery failed")

        raise HTTPException(
            status_code=502,
            detail="Email delivery failed. Please check SMTP configuration."
        )