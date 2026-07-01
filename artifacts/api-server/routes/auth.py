"""Authentication routes: login, logout, me, health."""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from database import get_db, engine
import models
import auth as auth_utils

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: str | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_user(cls, u: models.User) -> "UserOut":
        return cls(
            id=u.id,
            username=u.username,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
        )


class AuthResponse(BaseModel):
    user: UserOut
    token: str


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    logger.info("login started: username=%s", req.username)
    user = db.query(models.User).filter(models.User.username == req.username).first()
    if not user or not auth_utils.verify_password(req.password, user.hashed_password):
        logger.warning("login failed: invalid credentials for username=%s", req.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        logger.warning("login failed: account disabled for username=%s", req.username)
        raise HTTPException(status_code=401, detail="Account disabled")
    token = auth_utils.create_access_token({"sub": str(user.id)})
    logger.info("login success: username=%s user_id=%s role=%s", req.username, user.id, user.role)
    return {"user": UserOut.from_orm_user(user), "token": token}


@router.post("/logout")
def logout():
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def get_me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return UserOut.from_orm_user(current_user)


@router.get("/health")
def auth_health(db: Session = Depends(get_db)):
    """
    Diagnostics for the auth subsystem. Reports each dependency independently
    so a broken login can be root-caused without digging through server logs.
    """
    database_connected = False
    users_table_exists = False
    admin_user_exists = False
    dev_admin_available = False
    password_hashing_working = False

    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as exc:
        logger.error("auth/health: database connectivity check failed: %s", exc)

    if database_connected:
        try:
            from sqlalchemy import inspect as sa_inspect
            users_table_exists = sa_inspect(engine).has_table("users")
        except Exception as exc:
            logger.error("auth/health: users table existence check failed: %s", exc)

        if users_table_exists:
            try:
                admin_user_exists = db.query(models.User).filter(
                    models.User.role == "admin"
                ).first() is not None
                dev_admin_available = db.query(models.User).filter(
                    models.User.email == auth_utils.DEV_ADMIN_EMAIL
                ).first() is not None
            except Exception as exc:
                logger.error("auth/health: admin user lookup failed: %s", exc)

    jwt_configured = bool(auth_utils.SECRET_KEY)
    jwt_roundtrip_ok = False
    try:
        _test_token = auth_utils.create_access_token({"sub": "healthcheck"})
        import jwt as pyjwt
        pyjwt.decode(_test_token, auth_utils.SECRET_KEY, algorithms=[auth_utils.ALGORITHM])
        jwt_roundtrip_ok = True
    except Exception as exc:
        logger.error("auth/health: JWT round-trip check failed: %s", exc)

    try:
        _test_hash = auth_utils.hash_password("healthcheck")
        password_hashing_working = auth_utils.verify_password("healthcheck", _test_hash)
    except Exception as exc:
        logger.error("auth/health: password hashing check failed: %s", exc)

    is_development = not bool(os.environ.get("REPLIT_DEPLOYMENT"))

    return {
        "auth_router_loaded": True,
        "database_connected": database_connected,
        "users_table_exists": users_table_exists,
        "admin_user_exists": admin_user_exists,
        "jwt_configured": jwt_configured and jwt_roundtrip_ok,
        "password_hashing_working": password_hashing_working,
        "environment": "development" if is_development else "production",
        "dev_admin_available": is_development and dev_admin_available,
    }
