from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_session_token, hash_token, verify_password, hash_password
from app.database.connection import get_db
from app.models import LoginSession, User
from app.schemas.auth import LoginRequest, LoginResponse, SessionResponse, RegisterRequest, RegisterResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


def _current_session(authorization: str | None, db: Session):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(parts[1].strip())))
    now = datetime.now(timezone.utc)
    if not session or session.revoked:
        raise HTTPException(status_code=401, detail="Invalid or revoked session", headers={"WWW-Authenticate": "Bearer"})
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(status_code=401, detail="Session expired", headers={"WWW-Authenticate": "Bearer"})
    if not session.user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")
    return session


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    return _current_session(f"{credentials.scheme} {credentials.credentials}", db).user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    identifier = payload.identifier.strip().lower()
    user = db.scalar(select(User).where(or_(User.email == identifier, User.username == identifier)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username/email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")
    token = create_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    db.add(LoginSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires_at))
    db.commit()
    return LoginResponse(access_token=token, expires_at=expires_at, user=user)


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    username, email = payload.username.strip().lower(), str(payload.email).strip().lower()
    if payload.role not in {"admin", "operator", "viewer"}:
        raise HTTPException(status_code=422, detail="Invalid role")
    existing = db.scalar(select(User).where(or_(User.username == username, User.email == email)))
    if existing:
        if existing.username == username:
            raise HTTPException(status_code=409, detail="Username already registered")
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=payload.name.strip(), username=username, email=email, password_hash=hash_password(payload.password), role=payload.role, is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already registered")
    return user


@router.get("/session", response_model=SessionResponse)
def get_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    session = _current_session(f"{credentials.scheme} {credentials.credentials}", db)
    return SessionResponse(user=session.user, expires_at=session.expires_at)


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    session = _current_session(f"{credentials.scheme} {credentials.credentials}", db)
    session.revoked = True
    db.commit()
    return {"success": True, "message": "Logged out successfully"}
