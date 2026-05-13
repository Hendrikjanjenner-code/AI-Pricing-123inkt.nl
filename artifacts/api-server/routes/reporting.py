"""Executive Reporting routes — /api/rapportages/*"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Any, Optional
import json

from database import get_db
from auth import get_current_user
from models import FactManagementReport
from engine.reporting_engine import run_reporting_engine

router = APIRouter(prefix="/api/rapportages", tags=["rapportages"])


def _serialize_report(r: FactManagementReport) -> dict:
    def safe_json(v):
        try:
            return json.loads(v) if v else {}
        except Exception:
            return {}

    return {
        "id": r.id,
        "rapport_datum": str(r.report_date),
        "type": r.report_type,
        "periode_start": str(r.period_start) if r.period_start else None,
        "periode_eind": str(r.period_end) if r.period_end else None,
        "titel": r.title_nl,
        "samenvatting": r.summary_nl,
        "kpis": safe_json(r.kpis_json),
        "alerts": safe_json(r.alerts_json),
        "inzichten": safe_json(r.insights_json),
        "aanbevelingen": safe_json(r.recommendations_json),
        "aangemaakt_op": str(r.generated_at) if r.generated_at else None,
        "geexporteerd": r.is_exported,
    }


@router.get("")
def list_rapportages(
    type: Optional[str] = Query(None, description="DAGELIJKS / WEKELIJKS / MAANDELIJKS"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Lijst van alle managementrapportages."""
    q = db.query(FactManagementReport).order_by(
        FactManagementReport.report_date.desc(),
        FactManagementReport.report_type,
    )
    if type:
        q = q.filter(FactManagementReport.report_type == type.upper())
    reports = q.limit(50).all()

    return {
        "totaal": len(reports),
        "rapportages": [_serialize_report(r) for r in reports],
    }


@router.get("/{report_id}")
def get_rapportage(
    report_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Detail van één managementrapportage."""
    r = db.query(FactManagementReport).filter(FactManagementReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Rapportage niet gevonden")
    return _serialize_report(r)


@router.post("/genereer")
def genereer_rapportages(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Genereer dagelijkse, wekelijkse en maandelijkse rapportages voor vandaag."""
    count = run_reporting_engine(db)
    return {
        "status": "gegenereerd",
        "aangemaakt": count,
        "rapport_datum": str(date.today()),
    }


@router.get("/export/{report_id}")
def export_rapportage(
    report_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Exporteer rapportage als JSON (mail/API-ready)."""
    r = db.query(FactManagementReport).filter(FactManagementReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Rapportage niet gevonden")
    r.is_exported = True
    db.commit()
    return {
        "export": _serialize_report(r),
        "export_format": "json",
        "export_timestamp": str(date.today()),
    }
