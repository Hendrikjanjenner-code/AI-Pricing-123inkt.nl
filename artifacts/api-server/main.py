"""
AI Pricing Decision Engine — FastAPI main entry point.
Registers all API routers under the /api prefix.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import engine, Base
from seed import seed_database
from routes import (
    auth, products, categories, recommendations,
    dashboard, uploads, data_quality, substitutions,
    model_health, exports, users, skus, competition, ab_tests,
    concurrentie, elasticiteit, huismerk,
    scraping, matching, monitoring, execution, audit_log,
    bcg,
    traffic, search_demand,
    cost, procurement, economic, reporting, bcg_transitions,
    category_hierarchy, break_even, ecosystem,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed on startup
    Base.metadata.create_all(bind=engine)
    seed_database()
    yield


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
