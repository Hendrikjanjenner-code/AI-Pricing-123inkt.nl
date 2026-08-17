"""
Uniforme bronregistratie (§29) — één endpoint dat voor élke databron
(API-connector, CSV/Excel-upload, webhook) dezelfde statusvelden teruggeeft:

  verbindingsstatus, laatste sync, volgende sync, records, waarschuwingen,
  fouten, freshness (dagen) en datakwaliteit per bron.

GET /api/data-sources
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, date as _date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])

RECENT_JOB_WINDOW_DAYS = 30


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _job_stats(db: Session, filter_fn) -> dict:
    """Statistieken over recente ImportJobs voor deze bron."""
    cutoff = datetime.utcnow() - timedelta(days=RECENT_JOB_WINDOW_DAYS)
    jobs = filter_fn(db.query(models.ImportJob)).filter(
        models.ImportJob.created_at >= cutoff
    ).order_by(models.ImportJob.created_at.desc()).limit(200).all()

    last_job = jobs[0] if jobs else None
    warnings = sum(len(j.warnings_json or []) for j in jobs)
    errors = sum(1 for j in jobs if j.status in ("fout", "failed"))
    rows_failed = sum(j.rows_failed or 0 for j in jobs)
    rows_processed = sum(j.rows_processed or 0 for j in jobs)
    return {
        "last_job": {
            "id": last_job.id,
            "batch_id": last_job.batch_id,
            "status": last_job.status,
            "filename": last_job.filename,
            "rows_processed": last_job.rows_processed,
            "rows_failed": last_job.rows_failed,
            "rows_duplicates": last_job.rows_duplicates or 0,
            "created_at": _iso(last_job.created_at),
            "completed_at": _iso(last_job.completed_at),
        } if last_job else None,
        "jobs_recent": len(jobs),
        "failed_jobs_recent": errors,
        "warnings_recent": warnings,
        "rows_failed_recent": rows_failed,
        "rows_processed_recent": rows_processed,
        "last_sync_at": _iso(last_job.completed_at or last_job.created_at) if last_job else None,
    }


def _freshness(db: Session, date_col, extra_filter=None) -> dict:
    q = db.query(func.max(date_col))
    if extra_filter is not None:
        q = q.filter(extra_filter)
    newest = q.scalar()
    if newest is None:
        return {"newest_data_date": None, "freshness_days": None}
    return {
        "newest_data_date": newest.isoformat(),
        "freshness_days": (_date.today() - newest).days,
    }


def _quality_for_source(issue_rows: list, source_label: str) -> dict:
    rows = [r for r in issue_rows
            if r.source == source_label and r.status not in ("opgelost", "genegeerd")]
    errors = sum(1 for r in rows if r.severity == "error")
    warnings = sum(1 for r in rows if r.severity == "warning")
    score = max(0.0, 1.0 - errors * 0.2 - warnings * 0.05)
    return {
        "quality_score": round(score * 100, 1),
        "open_issues": len(rows),
        "issue_errors": errors,
        "issue_warnings": warnings,
    }


@router.get("")
def list_data_sources(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Uniform statusoverzicht van alle databronnen."""
    from routes.connectors import (
        VALID_CONNECTORS, CONNECTOR_LABELS, _connector_summary,
    )

    issue_rows = db.query(models.DataQualityIssue).all()
    now = datetime.now(timezone.utc)

    # Volgende geplande sync: alleen PriceShape draait op de feed-scheduler.
    feed_interval = int(os.environ.get("FEED_SYNC_INTERVAL", "21600"))
    feed_sync_disabled = bool(os.environ.get("DISABLE_FEED_SYNC"))

    # Per-connector configuratie van de datavelden
    connector_meta = {
        "priceshape": {
            "kind": "api",
            "quality_source": "PriceShape",
            "job_filter": lambda q: q.filter(
                (models.ImportJob.source == "PriceShape")
                | (models.ImportJob.upload_type == "api_sync_priceshape")),
            "freshness": lambda: _freshness(db, models.FactCompetitorPriceDaily.date),
            "records": lambda: db.query(models.FactCompetitorPriceDaily).count(),
            "records_label": "concurrentprijzen",
        },
        "drs": {
            "kind": "api",
            "quality_source": "DRS",
            "job_filter": lambda q: q.filter(
                (models.ImportJob.source == "DRS")
                | (models.ImportJob.upload_type.in_(["api_sync_drs", "api_sync"]))),
            "freshness": lambda: _freshness(db, models.FactSalesDaily.date),
            "records": lambda: db.query(models.DimProduct).count(),
            "records_label": "producten",
        },
        "ga4": {
            "kind": "api",
            "quality_source": "GA4",
            "job_filter": lambda q: q.filter(models.ImportJob.upload_type == "api_sync_ga4"),
            "freshness": lambda: _freshness(db, models.FactTrafficDaily.date),
            "records": lambda: db.query(models.FactTrafficDaily).count(),
            "records_label": "traffic-rijen",
        },
        "search_console": {
            "kind": "api",
            "quality_source": "Search Console",
            "job_filter": lambda q: q.filter(models.ImportJob.upload_type == "api_sync_search_console"),
            "freshness": lambda: _freshness(db, models.FactSearchDemandDaily.date,
                                            models.FactSearchDemandDaily.source == "gsc"),
            "records": lambda: db.query(models.FactSearchDemandDaily).filter(
                models.FactSearchDemandDaily.source == "gsc").count(),
            "records_label": "zoekterm-rijen",
        },
        "google_ads": {
            "kind": "api",
            "quality_source": "Google Ads",
            "job_filter": lambda q: q.filter(models.ImportJob.upload_type == "api_sync_google_ads"),
            "freshness": lambda: _freshness(db, models.FactMarketingCostDaily.date,
                                            models.FactMarketingCostDaily.category == "Google Ads"),
            "records": lambda: db.query(models.FactMarketingCostDaily).filter(
                models.FactMarketingCostDaily.category == "Google Ads").count(),
            "records_label": "campagne-kostenrijen",
        },
        "microsoft_ads": {
            "kind": "api",
            "quality_source": "Microsoft Ads",
            "job_filter": lambda q: q.filter(models.ImportJob.upload_type == "api_sync_microsoft_ads"),
            "freshness": lambda: _freshness(db, models.FactMarketingCostDaily.date,
                                            models.FactMarketingCostDaily.category == "Microsoft Ads"),
            "records": lambda: db.query(models.FactMarketingCostDaily).filter(
                models.FactMarketingCostDaily.category == "Microsoft Ads").count(),
            "records_label": "campagne-kostenrijen",
        },
    }

    sources: list[dict] = []

    for name in VALID_CONNECTORS:
        meta = connector_meta.get(name)
        if meta is None:
            continue
        summary = _connector_summary(db, name)
        stats = _job_stats(db, meta["job_filter"])
        fresh = meta["freshness"]()
        quality = _quality_for_source(issue_rows, meta["quality_source"])

        # Verbindingsstatus zonder trage live-check: configuratie + laatste teststatus.
        if not summary["configured"]:
            conn_status = "not_configured"
        elif summary["last_test_status"] in ("ok", None):
            conn_status = "ok" if summary["last_test_status"] == "ok" or summary["source"] == "env" else "unknown"
        else:
            conn_status = summary["last_test_status"]

        last_sync = summary["last_synced_at"] or stats["last_sync_at"]

        next_sync = None
        if name == "priceshape" and summary["configured"] and not feed_sync_disabled:
            if last_sync:
                try:
                    base = datetime.fromisoformat(last_sync)
                    if base.tzinfo is None:
                        base = base.replace(tzinfo=timezone.utc)
                    next_sync = (base + timedelta(seconds=feed_interval)).isoformat()
                except ValueError:
                    next_sync = None
            else:
                next_sync = now.isoformat()

        sources.append({
            "key": name,
            "label": CONNECTOR_LABELS[name],
            "kind": meta["kind"],
            "connection_status": conn_status,
            "configured": summary["configured"],
            "config_source": summary["source"],
            "last_test_status": summary["last_test_status"],
            "last_test_message": summary["last_test_message"],
            "last_sync_at": last_sync,
            "next_sync_at": next_sync,
            "sync_schedule": ("automatisch" if next_sync else "handmatig"),
            "records": meta["records"](),
            "records_label": meta["records_label"],
            **fresh,
            **stats,
            **quality,
        })

    # ── Niet-connector bronnen: handmatige uploads & Paper_Copy ──────────
    upload_sources = [
        ("handmatig", "CSV/Excel-upload", "Handmatig",
         lambda q: q.filter(models.ImportJob.source == "Handmatig")),
        ("paper_copy", "Paper_Copy import", "Handmatig",
         lambda q: q.filter(models.ImportJob.source == "Paper_Copy")),
    ]
    for key, label, quality_source, job_filter in upload_sources:
        stats = _job_stats(db, job_filter)
        quality = _quality_for_source(issue_rows, quality_source)
        sources.append({
            "key": key,
            "label": label,
            "kind": "upload",
            "connection_status": "ok" if stats["last_job"] else "not_configured",
            "configured": stats["last_job"] is not None,
            "config_source": None,
            "last_test_status": None,
            "last_test_message": None,
            "last_sync_at": stats["last_sync_at"],
            "next_sync_at": None,
            "sync_schedule": "handmatig",
            "records": stats["rows_processed_recent"],
            "records_label": "rijen (30 dagen)",
            "newest_data_date": None,
            "freshness_days": None,
            **stats,
            **quality,
        })

    return {
        "sources": sources,
        "generated_at": now.isoformat(),
        "feed_sync_interval_seconds": feed_interval,
    }
