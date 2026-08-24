"""
AI Pricing Decision Engine — FastAPI main entry point.
Registers all API routers under the /api prefix.
"""
import asyncio
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
    model_health, exports, users, skus, copilot, competition, ab_tests,
    concurrentie, elasticiteit, huismerk,
    monitoring, execution, audit_log, notifications,
    bcg,
    traffic, search_demand,
    cost, procurement, economic, reporting, bcg_transitions,
    category_hierarchy, break_even, ecosystem, explainability,
    admin, connectors, data_sources,
    signals, shops, platform, loyalty,
    basket, promotion_intelligence, forecast, opportunities, model_registry, decisions,
    pim,
    command_center, governance, engine_jobs,
    product_hierarchy,
    saved_views, global_search, management_drilldown,
    competitor_profile,
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
for _mod_name in ("drs", "priceshape", "bigquery"):
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
# Eén keer per proces: DDL, migraties en seeding. Herhaalde lifespans in
# hetzelfde proces (bv. TestClient per testmodule) slaan deze stappen over.
_db_bootstrap_done = False

startup_state: dict = {
    "backend_status": "starting",
    "database_status": "unknown",
    "started_at": None,
    "last_start_error": None,
    "ai_provider_reachable": None,   # True / False / None (nog niet getest)
    "ai_provider_error": None,       # foutmelding als probe mislukt
    # Zware hiërarchie-seed draait op de achtergrond ná het openen van de
    # poort (taak #296): pending → running → done/skipped/error.
    "hierarchy_seed_status": "pending",
    "hierarchy_seed_error": None,
}


def _seed_hierarchy_blocking() -> None:
    """Zware, eenmalige hiërarchie-seeding (Excel-import + fallback
    auto-opbouw). Draait in een thread op de achtergrond zodat de poort en
    healthcheck niet worden geblokkeerd. Beide stappen zijn idempotent en
    faalveilig; een reeds geseede omgeving slaat direct over."""
    startup_state["hierarchy_seed_status"] = "running"
    _excel_status = "error: onbekend"
    try:
        from seed import seed_hierarchy_from_excel
        _excel_status = seed_hierarchy_from_excel() or "done"
        if _excel_status.startswith("error"):
            startup_state["hierarchy_seed_error"] = _excel_status
    except Exception as _excel_exc:
        logger.warning("Achtergrond: Excel-hiërarchie seeding mislukt "
                       "(niet kritiek): %s", _excel_exc)
        _excel_status = f"error: {_excel_exc}"
        startup_state["hierarchy_seed_error"] = str(_excel_exc)

    # Automatische hiërarchie uit feed-categorieën als er nog helemaal geen
    # hiërarchie bestaat (taak #274) — daarna houdt elke feed-sync hem actueel
    # via run_model_refresh. Overgeslagen als de Excel-import nodes maakte.
    try:
        from services.hierarchy_autobuild import autobuild_hierarchy
        from database import SessionLocal as _HSL
        _hdb = _HSL()
        try:
            if _hdb.query(models.ProductHierarchyNode.id).first() is None:
                autobuild_hierarchy(_hdb)
        finally:
            _hdb.close()
    except Exception as _hb_exc:
        logger.warning("Achtergrond: automatische hiërarchie-opbouw "
                       "mislukt (niet kritiek): %s", _hb_exc)
        startup_state["hierarchy_seed_error"] = (
            startup_state["hierarchy_seed_error"] or str(_hb_exc))

    startup_state["hierarchy_seed_status"] = (
        "error" if startup_state["hierarchy_seed_error"]
        else ("skipped" if _excel_status in ("skipped_existing", "disabled",
                                             "missing_file") else "done"))
    logger.info("Achtergrond: hiërarchie-seeding afgerond (status=%s).",
                startup_state["hierarchy_seed_status"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: backend starting (version %s).", APP_VERSION)
    global _db_bootstrap_done
    _schedule_hierarchy_seed = False
    hierarchy_seed_task = None
    try:
        # De DDL/seed-stappen (1 t/m 4) zijn idempotent maar niet gratis:
        # elke run kost ~1-2s aan schema-introspectie. In productie start het
        # proces één keer, maar in de testsuite maakt elke testmodule een
        # eigen TestClient die deze lifespan opnieuw draait. Binnen hetzelfde
        # proces (zelfde DB-configuratie) is één keer bootstrappen voldoende.
        if not _db_bootstrap_done:
            # 1. Create any brand-new tables
            Base.metadata.create_all(bind=engine)
            logger.info("Startup: database tables ensured (create_all complete).")

            # 2. Add missing columns to existing tables (idempotent)
            run_migrations(engine, Base.metadata)
            logger.info("Startup: migrations applied.")

            # 2a. BigQuery kostenmeting-tabel aanmaken (idempotent, faalveilig)
            try:
                from bigquery.cost_tracker import ensure_cost_table
                ensure_cost_table(engine)
                logger.info("Startup: BigQuery kostenmeting-tabel ensured.")
            except Exception as _bq_exc:
                logger.warning("Startup: BigQuery kostenmeting-tabel aanmaken mislukt (niet kritiek): %s", _bq_exc)

        # 2b. Confirm the database is actually reachable (not just configured)
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        startup_state["database_status"] = "connected"
        logger.info("Startup: database connected.")

        if not _db_bootstrap_done:
            # 2c. Canonical model: default shop aanmaken + shop_id backfill
            from canonical import ensure_default_shop
            ensure_default_shop()
            logger.info("Startup: default shop ensured en shop_id backfill uitgevoerd.")

            # 3. Always ensure the 4 demo user accounts exist (needed for login)
            from seed import seed_users_only
            seed_users_only()
            logger.info("Startup: demo user accounts ensured.")

            # 3-bis. Departments/permissies seeden + eenmalige migratie van
            # bestaande gebruikers naar het granulaire model (taak 219).
            from authz import seed_authz
            seed_authz()
            logger.info("Startup: authz (departments/permissies) ensured.")

            # 3-ter. Eenmalige merge van concurrent-domeinvarianten
            # (www./https-schrijfwijzen) — idempotent via AuditLog-marker.
            from services.domain_normalize import merge_competitor_domain_variants
            from database import SessionLocal as _SL
            _mdb = _SL()
            try:
                merge_competitor_domain_variants(_mdb)
            finally:
                _mdb.close()
            logger.info("Startup: concurrent-domeinmerge gecontroleerd/uitgevoerd.")

            # 3-quater-a/b. Producthiërarchie-seeding (Excel-import + fallback
            # auto-opbouw) is de enige zware startup-stap (115k+ rijen stagen
            # en toepassen, ~60-90s). Dat mag het openen van de poort nooit
            # blokkeren: het deployment-platform SIGKILLt het proces als de
            # poort niet binnen de timeout opengaat (taak #296). De seed wordt
            # daarom hieronder — ná de snelle bootstrap — als achtergrondtaak
            # gestart; zie _seed_hierarchy_background().
            _schedule_hierarchy_seed = True

            # 3a. Dev-only safety net: guarantee a recoverable admin login exists
            # locally without ever touching/deleting existing data (no-op in prod).
            from auth import create_default_admin_if_missing
            create_default_admin_if_missing()

            # 3b. Idempotently ensure the configured real owner admin account exists
            # (OWNER_ADMIN_EMAIL + OWNER_ADMIN_PASSWORD). No-op when unset; runs in
            # dev and production so the same login works on the published app.
            from seed import ensure_owner_admin
            ensure_owner_admin()
            logger.info("Startup: owner admin account ensured (if configured).")

            # 3c. Eenmalige backfill (taak #288): bestaande discovery-
            # goedkeuringen naar de canonieke competitor-master. Idempotent;
            # overschrijft nooit een al gezette masterstatus.
            try:
                from services.competitor_master import backfill_master_approvals
                from database import SessionLocal as _CMSL
                _cmdb = _CMSL()
                try:
                    _n = backfill_master_approvals(_cmdb)
                finally:
                    _cmdb.close()
                if _n:
                    logger.info("Startup: %d competitor-goedkeuringen naar master gemigreerd.", _n)
            except Exception as _cm_exc:
                logger.warning("Startup: master-approval backfill mislukt (niet kritiek): %s", _cm_exc)

            # 4. Only seed demo product/price/sales data when explicitly requested
            if os.environ.get("SEED_DEMO_DATA", "false").lower() in ("1", "true", "yes"):
                seed_database()
                logger.info("Startup: demo product/sales data seeded (SEED_DEMO_DATA=true).")

            _db_bootstrap_done = True

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

        # 5a. Start de PriceShape feed-sync scheduler zodat de app onafgebroken
        # verse concurrentdata inleest (met retries + bescherming van laatst-goede
        # data). Uit te schakelen via DISABLE_FEED_SYNC.
        feed_sync_task = None
        if os.environ.get("DISABLE_FEED_SYNC", "false").lower() not in ("1", "true", "yes"):
            from services.feed_sync_scheduler import start_feed_sync_scheduler
            feed_sync_task = start_feed_sync_scheduler()
            logger.info("Startup: PriceShape feed-sync scheduler started.")
        else:
            logger.info("Startup: PriceShape feed-sync scheduler disabled via DISABLE_FEED_SYNC.")

        # 5b. Start de datakwaliteits-scan scheduler die de §30-detecties
        # dagelijks draait en eigenaren waarschuwt bij nieuwe error-issues.
        # Uit te schakelen via DISABLE_DATA_QUALITY_SCAN (bijv. op autoscale;
        # gebruik daar een Scheduled Deployment met
        # `python -m services.data_quality_scheduler`).
        dq_scan_task = None
        if os.environ.get("DISABLE_DATA_QUALITY_SCAN", "false").lower() not in ("1", "true", "yes"):
            from services.data_quality_scheduler import start_data_quality_scheduler
            dq_scan_task = start_data_quality_scheduler()
            logger.info("Startup: datakwaliteits-scan scheduler started.")
        else:
            logger.info("Startup: datakwaliteits-scan scheduler disabled via DISABLE_DATA_QUALITY_SCAN.")

        # 5c. Start de onafhankelijke AI-budgetslot-opruiming: verwijdert
        # periodiek AiBudgetSlot-rijen ouder dan de bewaartermijn
        # (AI_BUDGET_SLOT_RETENTION_DAYS, default 90 dagen). Bewust een eigen
        # scheduler met eigen disable-vlag, zodat het uitschakelen van andere
        # schedulers (bv. DISABLE_DQ_SCAN) deze onderhoudstaak niet raakt.
        budget_cleanup_task = None
        if os.environ.get("DISABLE_AI_BUDGET_CLEANUP", "false").lower() not in ("1", "true", "yes"):
            from services.ai_budget_cleanup_scheduler import start_ai_budget_cleanup_scheduler
            budget_cleanup_task = start_ai_budget_cleanup_scheduler()
            logger.info("Startup: AI-budgetslot opruim-scheduler started.")
        else:
            logger.info("Startup: AI-budgetslot opruiming disabled via DISABLE_AI_BUDGET_CLEANUP.")

        # 6. AI-sleutel bereikbaarheidstest (goedkope probe, geen tokenverbruik).
        # Resultaat wordt opgeslagen in startup_state én in ai_gateway._probe_cache
        # zodat /api/copilot/status het direct kan teruggeven.
        try:
            from ai_gateway import probe_provider
            _ai_reachable, _ai_error = probe_provider(force=True)
            startup_state["ai_provider_reachable"] = _ai_reachable
            startup_state["ai_provider_error"] = _ai_error
            if _ai_reachable:
                logger.info("Startup: AI provider bereikbaar.")
            else:
                logger.warning("Startup: AI provider NIET bereikbaar — %s", _ai_error)
                # Stel direct een beheerder-alert in voor een ongeldige/verlopen
                # sleutel bij opstarten — niet wachten op de eerste monitorcyclus.
                try:
                    from services.ai_key_monitor import _emit_alert
                    _emit_alert(False, _ai_error)
                except Exception as _alert_exc:
                    logger.warning("Startup: alert aanmaken mislukt: %s", _alert_exc)
        except Exception as _probe_exc:
            startup_state["ai_provider_reachable"] = False
            startup_state["ai_provider_error"] = str(_probe_exc)
            logger.warning("Startup: AI provider-probe mislukt: %s", _probe_exc)
            try:
                from services.ai_key_monitor import _emit_alert
                _emit_alert(False, str(_probe_exc))
            except Exception as _alert_exc:
                logger.warning("Startup: alert aanmaken mislukt: %s", _alert_exc)

        # 7. Start de AI-sleutel monitor die periodiek bereikbaarheid controleert
        # en beheerders actief waarschuwt bij statuswijzigingen.
        ai_key_monitor_task = None
        if os.environ.get("DISABLE_AI_KEY_MONITOR", "false").lower() not in ("1", "true", "yes"):
            from services.ai_key_monitor import start_ai_key_monitor
            ai_key_monitor_task = start_ai_key_monitor()
            logger.info("Startup: AI-sleutel monitor started.")
        else:
            logger.info("Startup: AI-sleutel monitor disabled via DISABLE_AI_KEY_MONITOR.")

        # 8. Zware hiërarchie-seeding op de achtergrond (taak #296): pas ná de
        # snelle bootstrap, in een thread, zodat uvicorn de poort direct kan
        # openen en de healthcheck op /api meteen 2xx geeft. De seed zelf is
        # idempotent; een reeds geseede omgeving is vrijwel meteen klaar.
        # In testomgevingen (conftest zet DISABLE_HIERARCHY_SEED) wordt er
        # helemaal niets gepland: ook de autobuild-fallback mag de
        # hiërarchietabellen dan niet muteren.
        if os.environ.get("DISABLE_HIERARCHY_SEED", "false").lower() in ("1", "true", "yes"):
            _schedule_hierarchy_seed = False
        if _schedule_hierarchy_seed:
            hierarchy_seed_task = asyncio.create_task(
                asyncio.to_thread(_seed_hierarchy_blocking))
            logger.info("Startup: hiërarchie-seeding als achtergrondtaak gestart.")
        else:
            startup_state["hierarchy_seed_status"] = "skipped"

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
        feed_sync_task = None
        ai_key_monitor_task = None
        dq_scan_task = None
        budget_cleanup_task = None
        hierarchy_seed_task = None
        # Re-raise so the process doesn't silently pretend to be healthy —
        # but the error is now captured in startup_state for diagnostics.
        raise
    try:
        yield
    finally:
        for _bg_task in (health_monitor_task, feed_sync_task, ai_key_monitor_task, dq_scan_task, budget_cleanup_task, hierarchy_seed_task):
            if _bg_task is not None:
                _bg_task.cancel()
                try:
                    await _bg_task
                except asyncio.CancelledError:
                    # CancelledError is een BaseException (geen Exception);
                    # zonder expliciete vangst zou een shutdown tijdens de
                    # seed de lifespan abrupt laten falen. NB: een
                    # to_thread-taak stopt de draaiende thread niet — de
                    # seed-stappen zijn idempotent, dus een volgende start
                    # maakt het werk veilig af of slaat over.
                    pass
                except Exception:
                    pass


app = FastAPI(
    title="AI Pricing Decision Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# ------------------------------------------------------------------
# Observability-middleware (§41-§42): correlation ID per request,
# gestructureerde JSON-logs, rolling API-metrics en cost-metering.
# ------------------------------------------------------------------
import json
import time as _time
import uuid

from services import metering as _metering

# /api/health* wordt zeer frequent gepolst; niet meteren om ruis te voorkomen.
_METERING_EXCLUDE = ("/api/healthz", "/api/health", "/api", "/api/")


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
    request.state.correlation_id = correlation_id
    start = _time.perf_counter()
    status_code = 500
    error_msg = None
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        error_msg = str(exc)
        raise
    finally:
        duration_ms = (_time.perf_counter() - start) * 1000
        path = request.url.path
        if path.startswith("/api") and path not in _METERING_EXCLUDE:
            module = _metering.module_from_path(path)
            _metering.track_request(module, duration_ms, status_code)
            _actor_username, _actor_shop_id = _metering.actor_from_request(request)
            _metering.record_usage(
                "api_request", module=module,
                username=_actor_username, shop_id=_actor_shop_id,
                correlation_id=correlation_id,
                endpoint=path, method=request.method,
                status_code=status_code, duration_ms=duration_ms,
            )
            if status_code >= 500 or error_msg:
                _metering.track_error(
                    correlation_id=correlation_id, method=request.method,
                    path=path, status_code=status_code,
                    message=error_msg or f"HTTP {status_code}", module=module,
                )
            # Gestructureerde logregel (JSON) met correlation ID
            logger.info(json.dumps({
                "type": "http_request",
                "correlation_id": correlation_id,
                "method": request.method,
                "path": path,
                "status": status_code,
                "duration_ms": round(duration_ms, 1),
            }))
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# ------------------------------------------------------------------
# Autorisatie-middleware (taak 219): dwingt de Route Registry-permissies
# (authz.ROUTE_PERMISSIONS) af op ÉLKE /api-route, zodat verboden endpoints
# ook via directe URL 403 geven. Menu-verbergen in de frontend is alleen UX.
# Zonder (geldig) token laat de middleware het verzoek door: de bestaande
# per-route dependencies geven dan zoals voorheen 401.
# ------------------------------------------------------------------
import authz as _authz
import auth as _auth_utils
import models
import jwt as _pyjwt
from database import SessionLocal as _AuthzSessionLocal


@app.middleware("http")
async def authz_middleware(request: Request, call_next):
    # View-permissie per padsegment; voor schrijfmethodes geldt daarnaast
    # een actie-permissie (bv. pricing.approve op goedkeurings-endpoints).
    required = (_authz.required_action_permission(request.url.path, request.method)
                or _authz.required_permission_for_path(request.url.path))
    if required:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = _pyjwt.decode(token, _auth_utils.SECRET_KEY,
                                        algorithms=[_auth_utils.ALGORITHM])
                user_id = int(payload.get("sub"))
            except Exception:
                user_id = None
            if user_id is not None:
                db = _AuthzSessionLocal()
                try:
                    user = db.query(models.User).filter(models.User.id == user_id).first()
                    if user and user.is_active and user.role != "admin":
                        if required not in _authz.effective_permissions(db, user):
                            return JSONResponse(
                                status_code=403,
                                content={"detail": f"Permissie '{required}' vereist",
                                         "error_code": "PERMISSION_DENIED",
                                         "required_permission": required},
                            )
                finally:
                    db.close()
    return await call_next(request)


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

    # BigQuery analytische laag — faalveilig: storing hier crasht /api/health nooit
    bq_module_status: dict = {"ok": "bigquery" not in disabled_optional_routers}
    try:
        from bigquery.client import bq_status as _bq_status
        _bs = _bq_status()
        bq_module_status["available"] = _bs.get("available", False)
        bq_module_status["project"] = _bs.get("project", "")
        if _bs.get("error"):
            bq_module_status["error"] = _bs["error"]
    except Exception as _bq_err:
        bq_module_status["available"] = False
        bq_module_status["error"] = str(_bq_err)
    optional_modules["bigquery"] = bq_module_status

    return {
        "status": "ok" if startup_state["backend_status"] == "running" and database_status == "connected" else "degraded",
        "backend_status": startup_state["backend_status"],
        "database_status": database_status,
        "frontend_status": "not_monitored_by_backend",
        "environment": "production" if os.environ.get("REPLIT_DEPLOYMENT") else "development",
        "app_version": APP_VERSION,
        "started_at": startup_state["started_at"],
        "last_start_error": startup_state["last_start_error"],
        "hierarchy_seed": {
            "status": startup_state["hierarchy_seed_status"],
            "error": startup_state["hierarchy_seed_error"],
        },
        "auth": auth_status,
        "optional_modules": optional_modules,
    }


@health_router.get("")
@health_router.get("/")
def api_root():
    """Lightweight liveness response on the bare service path.

    The deployment router health-checks the service at its registered base path
    (`/api`), NOT `/api/healthz`. Without a route here the app returned 404 (and
    503/500 while still booting), so the platform never considered the service
    healthy and the deployment would fail to stay live ("This app isn't live
    yet"). Returning a plain 200 here gives the health check a valid response
    the moment uvicorn is serving.
    """
    return {"status": "ok", "service": "api-server", "version": APP_VERSION}


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
app.include_router(competitor_profile.router)
app.include_router(ab_tests.router)
app.include_router(concurrentie.router)
app.include_router(elasticiteit.router)
app.include_router(huismerk.router)
app.include_router(monitoring.router)
app.include_router(execution.router)
app.include_router(audit_log.router)
app.include_router(notifications.router)
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
app.include_router(product_hierarchy.router)
app.include_router(break_even.router)
app.include_router(ecosystem.router)
app.include_router(explainability.router)
app.include_router(admin.router)
app.include_router(connectors.router)
app.include_router(data_sources.router)
app.include_router(signals.router)
app.include_router(shops.router)
app.include_router(platform.router)
app.include_router(loyalty.router)
app.include_router(basket.router)
app.include_router(promotion_intelligence.router)
app.include_router(forecast.router)
app.include_router(opportunities.router)
app.include_router(engine_jobs.router)
app.include_router(model_registry.router)
app.include_router(decisions.router)
app.include_router(copilot.router)
app.include_router(pim.router)
app.include_router(command_center.router)
app.include_router(governance.router)
app.include_router(saved_views.router)
app.include_router(saved_views.prefs_router)
app.include_router(global_search.router)
app.include_router(management_drilldown.router)
from routes import authz as authz_routes
app.include_router(authz_routes.router)

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
