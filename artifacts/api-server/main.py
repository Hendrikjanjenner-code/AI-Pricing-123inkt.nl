"""
AI Pricing Decision Engine — FastAPI main entry point.
Registers all API routers under the /api prefix.
"""
import os
import logging
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
    admin, pilot, drs,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create any brand-new tables
    Base.metadata.create_all(bind=engine)
    # 2. Add missing columns to existing tables (idempotent)
    run_migrations(engine, Base.metadata)
    # 3. Always ensure the 4 demo user accounts exist (needed for login)
    from seed import seed_users_only
    seed_users_only()
    # 3b. Controleer scraping-dependencies en log een duidelijke waarschuwing
    from services.scraping_engine import check_scraping_dependencies
    _scrape_deps = check_scraping_dependencies()
    if not _scrape_deps["ok"]:
        logging.getLogger("uvicorn.error").warning(
            "Scraping-dependencies ontbreken: %s", _scrape_deps["message"]
        )
    # 4. Only seed demo product/price/sales data when explicitly requested
    if os.environ.get("SEED_DEMO_DATA", "false").lower() in ("1", "true", "yes"):
        seed_database()
    # 5. Start de achtergrond-scheduler die scrapes automatisch volgens rooster draait
    scheduler_task = None
    if os.environ.get("DISABLE_SCRAPE_SCHEDULER", "false").lower() not in ("1", "true", "yes"):
        from services.scrape_scheduler import start_scheduler
        scheduler_task = start_scheduler()
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

# Health check at /api/healthz
from fastapi.routing import APIRouter
health_router = APIRouter(prefix="/api")

@health_router.get("/healthz")
def health_check():
    return {"status": "ok"}

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
