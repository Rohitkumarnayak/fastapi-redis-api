import base64
import binascii
import io
from datetime import datetime

from PIL import Image
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_ENCODED_LENGTH = 4 * ((MAX_IMAGE_BYTES + 2) // 3)

SUPPORTED_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def inspect_image(value: str | None) -> tuple[str, int] | None:
    """Validate Base64 image data and return (MIME type, decoded size)."""
    if value is None:
        return None

    # Accept a raw Base64 string or a browser data URL.
    if value.startswith("data:"):
        try:
            header, value = value.split(",", 1)
        except ValueError as exc:
            raise ValueError("Invalid image data URL") from exc

        if ";base64" not in header.lower():
            raise ValueError("Image data URL must use Base64")

    if not value:
        raise ValueError("Image cannot be empty")

    if len(value) > MAX_ENCODED_LENGTH:
        raise ValueError("Image exceeds the 5 MB limit")

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid Base64 image data") from exc

    if not decoded:
        raise ValueError("Image cannot be empty")

    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 5 MB limit")

    try:
        with Image.open(io.BytesIO(decoded)) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise ValueError("Invalid or corrupted image") from exc

    if image_format not in SUPPORTED_IMAGE_TYPES:
        raise ValueError("Only JPEG, PNG, and WebP images are supported")

    return SUPPORTED_IMAGE_TYPES[image_format], len(decoded)


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)

    # Zone associated with the event
    zone: str | None = Field(default=None, max_length=100)

    message: str = Field(default="", max_length=4000)

    severity: str = Field(
        default="info",
        pattern=r"^(info|warning|critical)$",
    )
    status: str = Field(
        default="pending",
        pattern=r"^(pending|assigned|acknowledged|resolved|closed)$",
    )

    assigned_to: str | None = Field(default=None, max_length=2000)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    image_base64: str | None = None
    image_mime_type: str | None = Field(
        default=None,
        pattern=r"^image/(jpeg|png|webp)$",
    )

    @field_validator("image_base64")
    @classmethod
    def validate_image_base64(cls, value: str | None) -> str | None:
        if value is None:
            return None

        # Normalize data URLs to raw Base64 before storing.
        if value.startswith("data:"):
            try:
                _, value = value.split(",", 1)
            except ValueError as exc:
                raise ValueError("Invalid image data URL") from exc

        inspect_image(value)
        return value

    @model_validator(mode="after")
    def validate_event_data(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "latitude and longitude must be provided together"
            )

        if self.image_base64 is None:
            if self.image_mime_type is not None:
                raise ValueError(
                    "image_base64 is required when image_mime_type is provided"
                )
            return self

        if self.image_mime_type is None:
            raise ValueError(
                "image_mime_type is required when an image is provided"
            )

        image_info = inspect_image(self.image_base64)
        actual_mime_type = image_info[0]

        if self.image_mime_type != actual_mime_type:
            raise ValueError(
                "image_mime_type does not match the actual image format"
            )

        return self


class EventUpdate(BaseModel):
    event_type: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    camera_id: str | None = Field(
        default=None, min_length=1, max_length=100
    )

    # Zone can be updated independently
    zone: str | None = Field(default=None, max_length=100)

    message: str | None = Field(default=None, max_length=4000)

    severity: str | None = Field(
        default=None,
        pattern=r"^(info|warning|critical)$",
    )
    status: str | None = Field(
        default=None,
        pattern=r"^(pending|assigned|acknowledged|resolved|closed)$",
    )

    assigned_to: str | None = Field(default=None, max_length=2000)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    image_base64: str | None = None
    image_mime_type: str | None = Field(
        default=None,
        pattern=r"^image/(jpeg|png|webp)$",
    )

    @field_validator("image_base64")
    @classmethod
    def validate_image_base64(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if value.startswith("data:"):
            try:
                _, value = value.split(",", 1)
            except ValueError as exc:
                raise ValueError("Invalid image data URL") from exc

        inspect_image(value)
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if (
            "latitude" in self.model_fields_set
            and "longitude" in self.model_fields_set
            and (self.latitude is None) != (self.longitude is None)
        ):
            raise ValueError(
                "latitude and longitude must be provided together"
            )

        # Validate image consistency when both image fields are supplied.
        if (
            "image_base64" in self.model_fields_set
            and "image_mime_type" in self.model_fields_set
        ):
            if self.image_base64 is None and self.image_mime_type is not None:
                raise ValueError(
                    "image_base64 is required when image_mime_type is provided"
                )

            if self.image_base64 is not None and self.image_mime_type is None:
                raise ValueError(
                    "image_mime_type is required when an image is provided"
                )

            if self.image_base64 is not None:
                image_info = inspect_image(self.image_base64)

                if self.image_mime_type != image_info[0]:
                    raise ValueError(
                        "image_mime_type does not match the actual image format"
                    )

        return self


class EventResponse(BaseModel):
    id: int
    event_type: str
    camera_id: str
    message: str
    severity: str
    status: str

    # Zone included in event API responses
    zone: str | None = None

    assigned_to: str | None = None
    assigned_by: int | None = None
    assigned_at: datetime | None = None

    acknowledged_by: int | None = None
    acknowledged_at: datetime | None = None

    resolved_by: int | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    latitude: float | None = None
    longitude: float | None = None

    image_base64: str | None = None
    image_mime_type: str | None = None

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResolveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)


class AssignRequest(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=2000)
