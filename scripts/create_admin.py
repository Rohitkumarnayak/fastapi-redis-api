"""Create the first admin user using BOOTSTRAP_ADMIN_* variables in .env."""
from sqlalchemy import select
from app.core.config import settings
from app.core.security import hash_password
from app.database.connection import Base, SessionLocal, engine
from app.models import Event, LoginSession, User  # noqa: F401 - register models


def main():
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise SystemExit("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in .env first.")
    if len(settings.bootstrap_admin_password) < 4:
        raise SystemExit("Admin password must be at least 4 characters.")
    Base.metadata.create_all(bind=engine)
    email = settings.bootstrap_admin_email.lower().strip()
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            raise SystemExit("A user with this email already exists; no changes made.")
        username = email.split("@", 1)[0].lower().strip()
        if db.scalar(select(User).where(User.username == username)):
            username = f"admin_{email.split(chr(64), 1)[0][:35]}"
        user = User(name=settings.bootstrap_admin_name, username=username, email=email, password_hash=hash_password(settings.bootstrap_admin_password), role="admin", is_active=True)
        db.add(user)
        db.commit()
        print(f"Created admin user: {email}")

if __name__ == "__main__":
    main()
