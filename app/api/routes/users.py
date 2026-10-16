from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user, require_admin
from app.core.security import hash_password
from app.database.connection import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["user management"])

class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: str = "operator"

class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)

class UserOut(BaseModel):
    id: int
    name: str
    username: str
    email: str
    role: str
    is_active: bool
    model_config = {"from_attributes": True}

@router.get("")
def list_users(q: str | None = None, role: str | None = None, is_active: bool | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
               db: Session = Depends(get_db), _: User = Depends(require_admin)):
    query = select(User)
    if q:
        term = f"%{q.strip()}%"
        query = query.where(or_(User.name.ilike(term), User.username.ilike(term), User.email.ilike(term)))
    if role: query = query.where(User.role == role)
    if is_active is not None: query = query.where(User.is_active == is_active)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [UserOut.model_validate(x) for x in rows], "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}

@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    username, email = payload.username.strip().lower(), str(payload.email).strip().lower()
    if payload.role not in {"admin", "operator", "viewer"}: raise HTTPException(422, "Invalid role")
    if db.scalar(select(User).where(or_(User.username == username, User.email == email))): raise HTTPException(409, "Username or email already registered")
    user = User(name=payload.name.strip(), username=username, email=email, password_hash=hash_password(payload.password), role=payload.role, is_active=True)
    db.add(user)
    try: db.commit(); db.refresh(user)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Username or email already registered")
    return user

@router.get("/me", response_model=UserOut)
def my_profile(user: User = Depends(get_current_user)):
    return user

@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    return user

@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    values = payload.model_dump(exclude_unset=True)
    if "role" in values and values["role"] not in {"admin", "operator", "viewer"}: raise HTTPException(422, "Invalid role")
    if user.id == actor.id and values.get("is_active") is False: raise HTTPException(400, "You cannot disable your own account")
    if "username" in values: values["username"] = values["username"].strip().lower()
    if "email" in values: values["email"] = str(values["email"]).strip().lower()
    if "name" in values and values["name"] is not None: values["name"] = values["name"].strip()
    if "password" in values:
        values["password_hash"] = hash_password(values.pop("password"))
    for key in ("username", "email"):
        if values.get(key) and db.scalar(select(User).where(getattr(User, key) == values[key], User.id != user_id)):
            raise HTTPException(409, f"{key.capitalize()} already registered")
    for key, value in values.items(): setattr(user, key, value)
    try: db.commit(); db.refresh(user)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Username or email already registered")
    return user

@router.delete("/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    if user.id == actor.id: raise HTTPException(400, "You cannot deactivate your own account")
    user.is_active = False
    # Revoke active sessions on deactivation.
    for session in user.sessions: session.revoked = True
    db.commit()
    return {"success": True, "message": "User deactivated", "id": user_id}
