"""
BigQuery API-routes — status, sync-trigger en kostenmeting.

Eindpunten:
  GET  /api/bigquery/status          — verbindingsstatus + BQ-project
  GET  /api/bigquery/sync/history    — recente sync-batches
  POST /api/bigquery/sync            — handmatige incrementele sync (admin)
  POST /api/bigquery/sync/full       — volledige herlaad (admin)
  GET  /api/bigquery/costs           — kostensamenvatting per module
  GET  /api/bigquery/schema          — overzicht geregistreerde tabellen

Faalveilig: als BigQuery niet beschikbaar is geven deze endpoints een
duidelijke foutstatus terug; de rest van de applicatie blijft werken.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/bigquery", tags=["bigquery"])

# ── Helper ────────────────────────────────────────────────────────────────────

def _require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Alleen admins mogen BigQuery-syncs starten")
    return current_user


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def bigquery_status():
    """
    Geef de BigQuery-verbindingsstatus terug.
    Bevat ook de sync-kosten-tabel-status en configuratie-instructies.
    """
    try:
        from bigquery.client import bq_status
        status = bq_status()
    except Exception as exc:
        status = {
            "available": False,
            "project": "",
            "error": str(exc),
            "checked_at": None,
        }

    # Configuratie-instructies wanneer BigQuery niet geconfigureerd is
    if not status.get("available"):
        status["configuration_help"] = {
            "option_1": {
                "env_var": "BQ_SERVICE_ACCOUNT_JSON",
                "description": "JSON-inhoud van een Google Cloud service-account sleutel",
                "example": "Stel in via Replit Secrets → BQ_SERVICE_ACCOUNT_JSON = '{...}'",
            },
            "option_2": {
                "env_vars": ["BQ_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS"],
                "description": "Project-ID + pad naar service-account JSON-bestand",
            },
        }

    return status


# ── Schema ────────────────────────────────────────────────────────────────────

@router.get("/schema")
def bigquery_schema(current_user: models.User = Depends(get_current_user)):
    """Overzicht van alle BigQuery-tabelschema's en hun PostgreSQL-bronnen."""
    try:
        from bigquery.schema import BQ_TABLE_DEFINITIONS, ALL_DATASETS
        tables = [
            {
                "dataset": t.dataset_id,
                "table": t.table_id,
                "pg_source": t.pg_table,
                "description": t.description,
                "partition_by": t.partition_by,
                "cluster_by": t.cluster_by,
                "columns": len(t.columns),
            }
            for t in BQ_TABLE_DEFINITIONS
        ]
        return {
            "datasets": ALL_DATASETS,
            "tables": tables,
            "total_tables": len(tables),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    tables: Optional[list[str]] = None  # None = alle tabellen


def _do_sync(tables: Optional[list[str]], full_refresh: bool):
    """Voer de sync uit (bedoeld als achtergrondtaak)."""
    try:
        from bigquery.sync import sync_table, sync_all_tables
        if tables:
            results = [sync_table(t, full_refresh=full_refresh) for t in tables]
        else:
            results = sync_all_tables(full_refresh=full_refresh)
        ok = sum(1 for r in results if r["status"] == "ok")
        err = sum(1 for r in results if r["status"] == "error")
        logger.info(
            "BigQuery sync klaar: %d ok, %d fout, full_refresh=%s",
            ok, err, full_refresh,
        )
    except Exception as exc:
        logger.error("BigQuery sync achtergrondtaak fout: %s", exc)


@router.post("/sync")
def trigger_sync(
    request: SyncRequest = SyncRequest(),
    background_tasks: BackgroundTasks = None,
    current_user: models.User = Depends(_require_admin),
):
    """
    Start een incrementele BigQuery-sync in de achtergrond.
    Alleen tabellen met nieuwe rijen (na het laatste watermerk) worden
    geëxporteerd.
    """
    from bigquery.client import bq_available
    if not bq_available():
        raise HTTPException(
            status_code=503,
            detail="BigQuery niet beschikbaar. Controleer BQ_SERVICE_ACCOUNT_JSON of BQ_PROJECT_ID.",
        )

    tables = request.tables
    if background_tasks:
        background_tasks.add_task(_do_sync, tables, False)
        return {
            "status": "gestart",
            "mode": "incrementeel",
            "tables": tables or "alle",
            "message": "Sync gestart in achtergrond. Controleer /api/bigquery/sync/history voor voortgang.",
        }
    # Synchrone fallback (voor tests)
    from bigquery.sync import sync_table, sync_all_tables
    if tables:
        results = [sync_table(t) for t in tables]
    else:
        results = sync_all_tables()
    return {"status": "klaar", "mode": "incrementeel", "results": results}


@router.post("/sync/full")
def trigger_full_sync(
    request: SyncRequest = SyncRequest(),
    background_tasks: BackgroundTasks = None,
    current_user: models.User = Depends(_require_admin),
):
    """
    Start een volledige herlaad van alle (of opgegeven) tabellen.
    LET OP: dit kan lang duren bij grote tabellen.
    """
    from bigquery.client import bq_available
    if not bq_available():
        raise HTTPException(
            status_code=503,
            detail="BigQuery niet beschikbaar. Controleer BQ_SERVICE_ACCOUNT_JSON of BQ_PROJECT_ID.",
        )

    tables = request.tables
    if background_tasks:
        background_tasks.add_task(_do_sync, tables, True)
        return {
            "status": "gestart",
            "mode": "volledig",
            "tables": tables or "alle",
            "message": "Volledige sync gestart in achtergrond.",
        }
    from bigquery.sync import sync_table, sync_all_tables
    if tables:
        results = [sync_table(t, full_refresh=True) for t in tables]
    else:
        results = sync_all_tables(full_refresh=True)
    return {"status": "klaar", "mode": "volledig", "results": results}


@router.get("/sync/history")
def sync_history(
    table: Optional[str] = Query(None, description="Filter op PostgreSQL-tabel"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Geef de meest recente sync-batches terug."""
    try:
        from bigquery.sync import get_sync_history
        return {"history": get_sync_history(db, pg_table=table, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Kostenmeting ──────────────────────────────────────────────────────────────

@router.get("/costs")
def query_costs(
    days: int = Query(30, ge=1, le=365, description="Periode in dagen"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Overzicht van BigQuery-scankosten per module voor de opgegeven periode.
    Kosten worden berekend op basis van $6.25/TB (on-demand EU).
    """
    try:
        from bigquery.cost_tracker import get_cost_summary
        return get_cost_summary(db, days=days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
