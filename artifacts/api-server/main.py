"""
AI Pricing Decision Engine — FastAPI main entry point.
Registers all API routers under the /api prefix.
"""
import os
import logging
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from database import engine, Base
from seed import seed_database
from migrate import run_migrations

logger = logging.getLogger("uvicorn.error")

from routes import (
    auth, products, categories, recommendations,
    dashboard, uploads, data_quality, substitutions,
    model_health, exports, users, skus, competition, ab_tests,
    concurrentie, elasticiteit, huismerk,
    monitoring, execution, audit_log,
    bcg,
    traffic, search_demand,
    cost, procurement, economic, reporting, bcg_transitions,
    category_hierarchy, break_even, ecosystem, explainability,
    admin, connectors,
)

# Optional modules (DRS import, PriceShape feed import) are imported
# individually, each in its own try/except. An import-time failure in one of
# them (e.g. a missing optional dependency) only disables that module — it can
# never crash the whole backend process and therefore can never block
# login/dashboard startup. This is intentionally done at import time (before
# router registration) since a bad top-level `from routes import (...)` for any
# of these names would otherwise abort the entire module load.
import importlib

disabled_optional_routers: set[str] = set()
_optional_router_modules: dict[str, object] = {}
for _mod_name in ("drs", "priceshape"):
    try:
        _optional_router_modules[_mod_name] = importlib.import_module(f"routes.{_mod_name}")
    except Exception as exc:
        disabled_optional_routers.add(_mod_name)
        logger.error(
            "Optional module '%s' failed to import and has been disabled "
            "(login/dashboard remain unaffected): %s", _mod_name, exc,
        )

APP_VERSION = "1.0.0"

# Populated during lifespan startup; surfaced via /api/healthz and /api/health
# so operators can see the last startup error without digging through logs.
startup_state: dict = {
    "backend_status": "starting",
    "database_status": "unknown",
    "started_at": None,
    "last_start_error": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: backend starting (version %s).", APP_VERSION)
    try:
        # 1. Create any brand-new tables
        Base.metadata.create_all(bind=engine)
        logger.info("Startup: database tables ensured (create_all complete).")

        # 2. Add missing columns to existing tables (idempotent)
        run_migrations(engine, Base.metadata)
        logger.info("Startup: migrations applied.")

        # 2b. Confirm the database is actually reachable (not just configured)
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        startup_state["database_status"] = "connected"
        logger.info("Startup: database connected.")

        # 3. Always ensure the 4 demo user accounts exist (needed for login)
        from seed import seed_users_only
        seed_users_only()
        logger.info("Startup: demo user accounts ensured.")

        # 3a. Dev-only safety net: guarantee a recoverable admin login exists
        # locally without ever touching/deleting existing data (no-op in prod).
        from auth import create_default_admin_if_missing
        create_default_admin_if_missing()

        # 4. Only seed demo product/price/sales data when explicitly requested
        if os.environ.get("SEED_DEMO_DATA", "false").lower() in ("1", "true", "yes"):
            seed_database()
            logger.info("Startup: demo product/sales data seeded (SEED_DEMO_DATA=true).")

        logger.info("Startup: routes loaded (%d routers registered).", len(app.routes))

        # 5. Start de connector-gezondheidsmonitor die databronnen bewaakt en
        # analisten per e-mail/webhook waarschuwt zodra een bron uitvalt.
        health_monitor_task = None
        if os.environ.get("DISABLE_HEALTH_MONITOR", "false").lower() not in ("1", "true", "yes"):
            from services.connector_health_monitor import start_health_monitor
            health_monitor_task = start_health_monitor()
            logger.info("Startup: connector health monitor started.")
        else:
            logger.info("Startup: connector health monitor disabled via DISABLE_HEALTH_MONITOR.")

        startup_state["backend_status"] = "running"
        startup_state["started_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Startup: backend started successfully.")
    except Exception as exc:
        startup_state["backend_status"] = "error"
        startup_state["last_start_error"] = {
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        if startup_state["database_status"] == "unknown":
            startup_state["database_status"] = "error"
        logger.error("Startup FAILED: %s\n%s", exc, traceback.format_exc())
        health_monitor_task = None
        # Re-raise so the process doesn't silently pretend to be healthy —
        # but the error is now captured in startup_state for diagnostics.
        raise
    try:
        yield
    finally:
        for _bg_task in (health_monitor_task,):
            if _bg_task is not None:
                _bg_task.cancel()
                try:
                    await _bg_task
                except Exception:
                    pass


app = FastAPI(
    title="AI Pricing Decision Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Return a clean 400 for malformed/missing request bodies (e.g. login with
    missing username/password) instead of FastAPI's default 422, and never a
    bare unhandled 500.
    """
    logger.info("Request validation failed on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Last-resort safety net: log the full traceback server-side but never leak
    internal error details to the client. Prevents raw tracebacks/500s with
    stack traces from reaching the frontend.
    """
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, exc, traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Health check at /api/healthz and /api/health
from fastapi.routing import APIRouter
health_router = APIRouter(prefix="/api")


def _build_health_payload() -> dict:
    """Assemble the full diagnostics payload shared by /healthz and /health."""
    from sqlalchemy import text

    database_status = "unknown"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception as exc:
        database_status = f"error: {exc}"

    # Merge auth-subsystem diagnostics so /api/health is a single source of
    # truth for "is login possible right now" without a second round-trip.
    auth_status: dict = {"available": False}
    try:
        from routes.auth import auth_health
        from database import SessionLocal
        db = SessionLocal()
        try:
            auth_status = {"available": True, **auth_health(db=db)}
        finally:
            db.close()
    except Exception as exc:
        logger.error("health: auth subsystem diagnostics failed: %s", exc)
        auth_status = {"available": False, "error": str(exc)}

    # Optional/non-critical modules — reported for visibility, never block
    # overall status. Each check is isolated so one broken optional module
    # can't take down /api/health itself.
    optional_modules: dict = {}
    optional_modules["drs"] = {"ok": "drs" not in disabled_optional_routers}
    optional_modules["priceshape"] = {"ok": "priceshape" not in disabled_optional_routers}

    return {
        "status": "ok" if startup_state["backend_status"] == "running" and database_status == "connected" else "degraded",
        "backend_status": startup_state["backend_status"],
        "database_status": database_status,
        "frontend_status": "not_monitored_by_backend",
        "environment": "production" if os.environ.get("REPLIT_DEPLOYMENT") else "development",
        "app_version": APP_VERSION,
        "started_at": startup_state["started_at"],
        "last_start_error": startup_state["last_start_error"],
        "auth": auth_status,
        "optional_modules": optional_modules,
    }


@health_router.get("/healthz")
def health_check():
    return _build_health_payload()


@health_router.get("/health")
def health_check_full():
    return _build_health_payload()


app.include_router(health_router)

# All domain routers (each defines its own /api prefix)
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(categories.router)
app.include_router(recommendations.router)
app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(data_quality.router)
app.include_router(substitutions.router)
app.include_router(model_health.router)
app.include_router(exports.router)
app.include_router(users.router)
app.include_router(skus.router)
app.include_router(competition.router)
app.include_router(ab_tests.router)
app.include_router(concurrentie.router)
app.include_router(elasticiteit.router)
app.include_router(huismerk.router)
app.include_router(monitoring.router)
app.include_router(execution.router)
app.include_router(audit_log.router)
app.include_router(bcg.router)
app.include_router(traffic.router)
app.include_router(traffic.conversie_router)
app.include_router(search_demand.router)
app.include_router(cost.router)
app.include_router(procurement.router)
app.include_router(economic.router)
app.include_router(reporting.router)
app.include_router(bcg_transitions.router)
app.include_router(category_hierarchy.router)
app.include_router(break_even.router)
app.include_router(ecosystem.router)
app.include_router(explainability.router)
app.include_router(admin.router)
app.include_router(connectors.router)

# Register whichever optional modules imported successfully above. Modules
# that failed to import were already recorded in disabled_optional_routers
# and are simply skipped here — registration is also wrapped in try/except
# in case a router raises during include_router itself (e.g. duplicate
# path/tag registration), so that failure mode is equally non-fatal.
for _name, _mod in _optional_router_modules.items():
    try:
        app.include_router(_mod.router)
    except Exception as exc:
        disabled_optional_routers.add(_name)
        logger.error(
            "Optional module '%s' failed to register and has been disabled "
            "(login/dashboard remain unaffected): %s", _name, exc,
        )
