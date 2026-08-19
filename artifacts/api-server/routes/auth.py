"""Authentication routes: login, logout, me, health."""
import asyncio
import logging
import os
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, DBAPIError, TimeoutError as SATimeoutError
from pydantic import BaseModel
from database import get_db, engine, SessionLocal
import models
import auth as auth_utils

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Hard end-to-end deadline for a single login attempt. Chosen so that a slow
# or unreachable database (or any other unexpected slowdown) fails fast with
# a structured error instead of hanging the request/worker indefinitely.
LOGIN_TIMEOUT_SECONDS = float(os.environ.get("LOGIN_TIMEOUT_SECONDS", "5"))


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


def _user_payload(db: Session, user: models.User) -> dict:
    """UserOut + authz-velden (permissies, afdelingen, workspace, scopes)."""
    import authz
    payload = UserOut.from_orm_user(user).model_dump()
    payload.update(authz.authz_payload(db, user))
    return payload


def _run_login(username: str, password: str) -> dict:
    """
    Runs the full blocking login flow (DB connect + query + password check +
    token generation) synchronously. Executed inside a worker thread that is
    itself wrapped by a hard deadline in the `login` route below, so a slow
    or unreachable database can never hang the request past that deadline.

    Opens its own DB session (rather than relying on FastAPI's Depends(get_db))
    so that even the connection-acquisition step — which is where an
    unreachable database typically blocks — is covered by the deadline.
    """
    logger.info("login: db session opening for username=%s", username)
    db = SessionLocal()
    try:
        logger.info("login: db session opened for username=%s", username)

        logger.info("login: user query started for username=%s", username)
        user = db.query(models.User).filter(models.User.username == username).first()
        logger.info("login: user query completed for username=%s found=%s", username, bool(user))

        logger.info("login: password check started for username=%s", username)
        password_ok = bool(user) and auth_utils.verify_password(password, user.hashed_password)
        logger.info("login: password check completed for username=%s ok=%s", username, password_ok)

        if not password_ok:
            logger.warning("login: invalid credentials for username=%s", username)
            return {"ok": False, "status_code": 401, "error_code": "INVALID_CREDENTIALS", "detail": "Invalid credentials"}

        if not user.is_active:
            logger.warning("login: account disabled for username=%s", username)
            return {"ok": False, "status_code": 401, "error_code": "ACCOUNT_DISABLED", "detail": "Account disabled"}

        logger.info("login: token generation started for username=%s", username)
        token = auth_utils.create_access_token({"sub": str(user.id)})
        logger.info("login: token generation completed for username=%s", username)

        return {"ok": True, "user": _user_payload(db, user), "token": token}
    finally:
        db.close()
        logger.info("login: db session closed for username=%s", username)


@router.post("/login")
async def login(req: LoginRequest):
    started_at = time.monotonic()
    logger.info("login: request received for username=%s", req.username)
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _run_login, req.username, req.password),
            timeout=LOGIN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started_at
        logger.error(
            "login: TIMEOUT after %.2fs (limit %.1fs) for username=%s — likely a slow/unreachable database",
            elapsed, LOGIN_TIMEOUT_SECONDS, req.username,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "LOGIN_TIMEOUT",
                "detail": "Login timed out. The database may be slow or unreachable. Please try again shortly.",
            },
        )
    except (OperationalError, DBAPIError, SATimeoutError) as exc:
        logger.error("login: DB_UNREACHABLE for username=%s: %s", req.username, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "DB_UNREACHABLE",
                "detail": "Could not reach the database. Please try again shortly.",
            },
        )
    except Exception as exc:
        logger.error("login: unexpected error for username=%s: %s", req.username, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "LOGIN_ERROR",
                "detail": "An unexpected error occurred during login.",
            },
        )

    if not result["ok"]:
        logger.info("login: response returned (%s) for username=%s", result["error_code"], req.username)
        return JSONResponse(
            status_code=result["status_code"],
            content={"error_code": result["error_code"], "detail": result["detail"]},
        )

    logger.info(
        "login: response returned (success) for username=%s in %.2fs",
        req.username, time.monotonic() - started_at,
    )
    return {"user": result["user"], "token": result["token"]}


@router.post("/logout")
def logout():
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    return _user_payload(db, current_user)


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
