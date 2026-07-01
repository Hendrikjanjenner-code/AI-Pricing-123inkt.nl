"""
AI Pricing Decision Engine — FastAPI main entry point.
Registers all API routers under the /api prefix.
"""
import os
import logging
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import engine, Base
from seed import seed_database
from migrate import run_migrations
from routes import (
    auth, products, categories, recommendations,
    dashboard, uploads, data_quality, substitutions,
    model_health, exports, users, skus, competition, ab_tests,
    concurrentie, elasticiteit, huismerk,
    scraping, matching, monitoring, execution, audit_log,
    bcg,
    traffic, search_demand,
    cost, procurement, economic, reporting, bcg_transitions,
    category_hierarchy, break_even, ecosystem, explainability,
    admin, pilot, drs, paper_copy, priceshape,
)

logger = logging.getLogger("uvicorn.error")

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

        # 3b. Controleer scraping-dependencies en log een duidelijke waarschuwing
        from services.scraping_engine import check_scraping_dependencies
        _scrape_deps = check_scraping_dependencies()
        if not _scrape_deps["ok"]:
            logger.warning(
                "Scraping-dependencies ontbreken: %s", _scrape_deps["message"]
            )
        else:
            logger.info("Startup: scraping dependencies present.")

        # 4. Only seed demo product/price/sales data when explicitly requested
        if os.environ.get("SEED_DEMO_DATA", "false").lower() in ("1", "true", "yes"):
            seed_database()
            logger.info("Startup: demo product/sales data seeded (SEED_DEMO_DATA=true).")

        logger.info("Startup: routes loaded (%d routers registered).", len(app.routes))

        # 5. Start de achtergrond-scheduler die scrapes automatisch volgens rooster draait
        scheduler_task = None
        if os.environ.get("DISABLE_SCRAPE_SCHEDULER", "false").lower() not in ("1", "true", "yes"):
            from services.scrape_scheduler import start_scheduler
            scheduler_task = start_scheduler()
            logger.info("Startup: scrape scheduler started.")
        else:
            logger.info("Startup: scrape scheduler disabled via DISABLE_SCRAPE_SCHEDULER.")

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
        scheduler_task = None
        # Re-raise so the process doesn't silently pretend to be healthy —
        # but the error is now captured in startup_state for diagnostics.
        raise
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
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

    return {
        "status": "ok" if startup_state["backend_status"] == "running" and database_status == "connected" else "degraded",
        "backend_status": startup_state["backend_status"],
        "database_status": database_status,
        "frontend_status": "not_monitored_by_backend",
        "environment": "production" if os.environ.get("REPLIT_DEPLOYMENT") else "development",
        "app_version": APP_VERSION,
        "started_at": startup_state["started_at"],
        "last_start_error": startup_state["last_start_error"],
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
app.include_router(scraping.router)
app.include_router(matching.router)
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
app.include_router(pilot.router)
app.include_router(drs.router)
app.include_router(paper_copy.router)
app.include_router(priceshape.router)
