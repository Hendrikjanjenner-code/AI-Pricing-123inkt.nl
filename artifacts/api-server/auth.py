"""
Authentication utilities: password hashing, JWT token creation/verification,
and the get_current_user FastAPI dependency.
"""
import logging
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
import jwt as pyjwt
from jwt.exceptions import InvalidTokenError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
import models

logger = logging.getLogger("uvicorn.error")

DEV_ADMIN_EMAIL = "admin@example.com"
DEV_ADMIN_USERNAME = "dev_admin"
DEV_ADMIN_PASSWORD = "admin123"

SECRET_KEY = os.environ.get("SESSION_SECRET")
if not SECRET_KEY:
    SECRET_KEY = "dev-secret-key-change-in-production"
    if os.environ.get("REPLIT_DEPLOYMENT"):
        logger.error(
            "SESSION_SECRET is not set in production! Falling back to an insecure "
            "development key — set the SESSION_SECRET secret immediately."
        )
    else:
        logger.warning(
            "SESSION_SECRET is not set. Using an insecure development fallback key. "
            "This is fine for local development but must be set before deploying."
        )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = int(sub)
    except (InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def create_default_admin_if_missing() -> None:
    """
    Dev-only safety net: ensures a recoverable admin login always exists in
    development, without ever touching or deleting any existing data.

    - Only runs when not deployed (REPLIT_DEPLOYMENT unset), i.e. development.
    - Only INSERTs a new user if one with DEV_ADMIN_EMAIL doesn't already
      exist. Never updates, deletes, or resets other rows/tables.
    """
    if os.environ.get("REPLIT_DEPLOYMENT"):
        return  # never auto-create accounts in production

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(
            models.User.email == DEV_ADMIN_EMAIL
        ).first()
        if existing:
            return

        db.add(models.User(
            username=DEV_ADMIN_USERNAME,
            email=DEV_ADMIN_EMAIL,
            full_name="Development Admin",
            hashed_password=hash_password(DEV_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        ))
        db.commit()
        logger.info(
            "Dev admin account created (%s / %s) — development only, safe to ignore in production.",
            DEV_ADMIN_EMAIL, DEV_ADMIN_USERNAME,
        )
    except Exception as exc:
        db.rollback()
        logger.error("create_default_admin_if_missing failed (non-fatal): %s", exc)
    finally:
        db.close()


def require_role(*roles: str):
    """Dependency factory that checks the current user's role."""
    def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker
