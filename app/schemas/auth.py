from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator


class LoginRequest(BaseModel):
    # Backward compatible: accepts the new `identifier` field or the old
    # frontend's `email` field. `username` is also accepted explicitly.
    identifier: str | None = Field(default=None, min_length=1, max_length=255, description="Username or email")
    email: str | None = Field(default=None, min_length=1, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def require_identifier(self):
        if not any(value and value.strip() for value in (self.identifier, self.email, self.username)):
            raise ValueError("Provide identifier, email, or username")
        return self

    @property
    def login_identifier(self) -> str:
        value = self.identifier or self.email or self.username
        return value.strip().lower()


class UserResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    role: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class SessionResponse(BaseModel):
    success: bool = True
    user: UserResponse
    expires_at: datetime


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: str = "operator"


class RegisterResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
