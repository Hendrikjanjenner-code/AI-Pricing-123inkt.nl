"""Model health and model run trigger endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from database import get_db
import models
import auth as auth_utils
from engine.pricing_engine import run_pricing_engine

router = APIRouter(prefix="/api", tags=["model-health"])


@router.get("/model-health")
def get_model_health(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    last_run = db.query(models.ModelRun).order_by(models.ModelRun.started_at.desc()).first()
    total_skus = db.query(models.DimProduct).count()
    skus_with_issues = db.query(models.DimProduct).filter(
        models.DimProduct.cost_price.is_(None)
    ).count()
    dq_score = round(1 - (skus_with_issues / total_skus), 3) if total_skus > 0 else 1.0
    avg_conf = db.query(func.avg(models.FactPricingRecommendationDaily.confidence_score)).scalar() or 0.0

    errors = []
    warnings = []
    if skus_with_issues > 0:
        warnings.append(f"{skus_with_issues} SKUs missing cost price")
    no_strategy = db.query(models.DimProduct).filter(models.DimProduct.strategy_type.is_(None)).count()
    if no_strategy > 0:
        warnings.append(f"{no_strategy} SKUs without a strategy type")

    status = "healthy"
    if last_run and last_run.status == "failed":
        status = "error"
    elif len(warnings) > 2:
        status = "degraded"
    elif not last_run:
        status = "not_run"

    return {
        "last_run_at": last_run.started_at.isoformat() if last_run else None,
        "skus_processed": last_run.skus_processed if last_run else 0,
        "skus_skipped": last_run.skus_skipped if last_run else 0,
        "avg_confidence": round(float(avg_conf), 3),
        "data_quality_score": dq_score,
        "model_version": last_run.model_version if last_run else "v1.0.0",
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/model-runs")
def list_model_runs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    runs = db.query(models.ModelRun).order_by(models.ModelRun.started_at.desc()).limit(20).all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "skus_processed": r.skus_processed,
            "skus_skipped": r.skus_skipped,
            "model_version": r.model_version or "v1.0.0",
            "error_message": r.error_message,
        }
        for r in runs
    ]


@router.post("/model-runs")
def trigger_model_run(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    run = models.ModelRun(
        started_at=datetime.utcnow(),
        status="running",
        skus_processed=0,
        skus_skipped=0,
        model_version="v1.0.0",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        processed, skipped = run_pricing_engine(db)
        # Vernieuw de PCIS-concurrentiescores uit de actuele concurrentprijzen,
        # zodat één modelrun zowel aanbevelingen als concurrentie-intelligentie oplevert.
        # Een fout hier mag géén stille "completed" opleveren: laat 'm doorwerken
        # naar de except-tak zodat de run als 'failed' met foutmelding wordt gemarkeerd.
        import feed_ingest
        feed_ingest.score_competition(db)
        feed_ingest.build_ai_matches(db)
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.skus_processed = processed
        run.skus_skipped = skipped
    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = str(e)

    db.commit()
    db.refresh(run)
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "skus_processed": run.skus_processed,
        "skus_skipped": run.skus_skipped,
        "model_version": run.model_version,
        "error_message": run.error_message,
    }
