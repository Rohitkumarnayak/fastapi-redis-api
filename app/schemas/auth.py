from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255, description="Username or email")
    password: str = Field(min_length=1, max_length=200)


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
