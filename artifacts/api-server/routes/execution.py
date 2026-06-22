"""
Price Execution routes — /api/execution/...
Uitvoering van goedgekeurde prijswijzigingen via de interne prijsmodule.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from models import (
    PriceExecutionJob, PriceExecutionLine,
    FactPricingRecommendationDaily, DimProduct, User, AuditLog
)
from datetime import datetime, date
from fastapi.responses import StreamingResponse
import io

router = APIRouter(prefix="/api/execution", tags=["execution"])


@router.get("/jobs")
def get_execution_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal uitvoering-jobs op, meest recent eerst."""
    totaal = db.query(PriceExecutionJob).count()
    jobs = (
        db.query(PriceExecutionJob)
        .order_by(desc(PriceExecutionJob.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "created_at": str(j.created_at),
                "created_by": j.created_by,
                "execution_mode": j.execution_mode,
                "status": j.status,
                "approved_count": j.approved_count,
                "rejected_count": j.rejected_count,
                "export_file_path": j.export_file_path,
                "error_message": j.error_message,
            }
            for j in jobs
        ],
        "totaal": totaal,
        "page": page,
        "page_size": page_size,
    }


@router.get("/jobs/{job_id}/lines")
def get_job_lines(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal alle prijsregels op voor een specifieke job."""
    job = db.query(PriceExecutionJob).filter(PriceExecutionJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job niet gevonden")

    lines = db.query(PriceExecutionLine).filter(PriceExecutionLine.job_id == job_id).all()
    producten = {p.sku_id: p.product_name for p in db.query(DimProduct).all()}

    return {
        "job_id": job_id,
        "execution_mode": job.execution_mode,
        "status": job.status,
        "lines": [
            {
                "line_id": l.line_id,
                "sku_id": l.sku_id,
                "product_naam": producten.get(l.sku_id, l.sku_id),
                "old_price": float(l.old_price) if l.old_price else None,
                "new_price": float(l.new_price) if l.new_price else None,
                "change_pct": l.change_pct,
                "status": l.status,
                "reason_code": l.reason_code,
                "rollback_price": float(l.rollback_price) if l.rollback_price else None,
            }
            for l in lines
        ],
    }


@router.post("/dry-run")
def dry_run(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simuleer uitvoering zonder daadwerkelijke prijswijziging.
    Toont welke adviezen de safety rules doorstaan.
    """
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.execution_engine import create_execution_job, DRY_RUN
    lines = _haal_goedgekeurde_adviezen(db, payload.get("datum"))

    if not lines:
        return {"status": "geen_adviezen", "bericht": "Geen goedgekeurde adviezen beschikbaar"}

    resultaat = create_execution_job(db, lines, current_user.username, DRY_RUN)
    resultaat["bericht"] = "Dry run — geen prijzen gewijzigd"
    return resultaat


@router.post("/export-csv")
def export_csv(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Exporteer goedgekeurde prijsadviezen als CSV.
    Maakt een uitvoering-job aan met mode MANUAL_EXPORT.
    """
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.execution_engine import create_execution_job, generate_export_csv, MANUAL_EXPORT

    lines = _haal_goedgekeurde_adviezen(db, payload.get("datum"))
    if not lines:
        raise HTTPException(status_code=404, detail="Geen goedgekeurde adviezen beschikbaar voor export")

    job_info = create_execution_job(db, lines, current_user.username, MANUAL_EXPORT)

    # Update job status
    job = db.query(PriceExecutionJob).filter(PriceExecutionJob.job_id == job_info["job_id"]).first()
    if job:
        job.status = "geëxporteerd"
        db.commit()

    csv_inhoud = generate_export_csv(lines)

    _log_audit(db, current_user.username, "export_csv", "execution_job",
               str(job_info["job_id"]), f"CSV export: {len(lines)} adviezen")

    return StreamingResponse(
        io.StringIO(csv_inhoud),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prijswijzigingen_{date.today()}.csv"},
    )


@router.post("/push")
def push_prices(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Maak een API_PUSH_READY job aan (demo-connector).
    Vereist altijd goedkeuring — nooit automatisch live.
    """
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.execution_engine import create_execution_job, DemoCommerceConnector, API_PUSH_READY

    lines = _haal_goedgekeurde_adviezen(db, payload.get("datum"))
    if not lines:
        raise HTTPException(status_code=404, detail="Geen goedgekeurde adviezen")

    job_info = create_execution_job(db, lines, current_user.username, API_PUSH_READY)

    connector = DemoCommerceConnector()
    push_resultaat = connector.push_prices(lines)

    # Update job status
    job = db.query(PriceExecutionJob).filter(PriceExecutionJob.job_id == job_info["job_id"]).first()
    if job:
        job.status = "verstuurd_demo"
        db.commit()

    _log_audit(db, current_user.username, "api_push", "execution_job",
               str(job_info["job_id"]), f"API push: {push_resultaat.get('geslaagd', 0)} geslaagd")

    return {**job_info, "push_resultaat": push_resultaat}


@router.post("/rollback/{job_id}")
def rollback_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Draai een uitvoering-job terug naar originele prijzen."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.execution_engine import DemoCommerceConnector

    connector = DemoCommerceConnector()
    resultaat = connector.rollback_prices(job_id, db)

    job = db.query(PriceExecutionJob).filter(PriceExecutionJob.job_id == job_id).first()
    if job:
        job.status = "teruggedraaid"
        db.commit()

    _log_audit(db, current_user.username, "rollback", "execution_job",
               str(job_id), f"Rollback uitgevoerd: {resultaat.get('teruggezet', 0)} SKU's")

    return resultaat


# ── Helpers ──────────────────────────────────────────────────────────────────

def _haal_goedgekeurde_adviezen(db: Session, datum=None) -> list[dict]:
    """Haal goedgekeurde aanbevelingen op als uitvoering-payload."""
    q = db.query(FactPricingRecommendationDaily, DimProduct).join(
        DimProduct, DimProduct.sku_id == FactPricingRecommendationDaily.sku_id
    ).filter(FactPricingRecommendationDaily.approval_status == "approved")

    if datum:
        q = q.filter(FactPricingRecommendationDaily.date == datum)

    lines = []
    for rec, prod in q.all():
        lines.append({
            "sku_id": rec.sku_id,
            "old_price": float(rec.current_price) if rec.current_price else None,
            "new_price": float(rec.recommended_price) if rec.recommended_price else None,
            "min_price": float(prod.min_price) if prod.min_price else None,
            "max_price": float(prod.max_price) if prod.max_price else None,
            "cost_price": float(prod.cost_price) if prod.cost_price else None,
            "confidence_score": rec.confidence_score or 1.0,
            "reason_code": rec.reason_code,
            "approved_by": rec.approved_by,
            "approved_at": str(rec.approved_at) if rec.approved_at else None,
            "execution_status": "klaar",
        })
    return lines


def _log_audit(db: Session, gebruiker: str, actie: str, entiteit: str, entiteit_id: str, details: str):
    """Voeg een audit log entry toe."""
    log = AuditLog(
        entity_type=entiteit,
        entity_id=entiteit_id,
        action=actie,
        performed_by=gebruiker,
        details=details,
        timestamp=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
