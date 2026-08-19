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


NIGHTLY_ENGINES = [
    ("basket", "Basket-engine"),
    ("promotion", "Promotion-engine"),
    ("forecast", "Forecast/Risk-engine"),
    ("opportunity", "Opportunity-engine"),
]

# Een nachtelijke run hoort elke nacht te draaien; ouder dan 26 uur = verouderd.
STALE_AFTER_HOURS = 26


@router.get("/engine-runs/status")
def get_engine_run_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Status van de nachtelijke engine-runs (scheduled_engines.py) per engine.

    Per engine: laatste run-tijdstip en status. Een engine krijgt status
    'failed' als minstens één shop in de laatste run mislukt is, 'stale' als
    de laatste run ouder is dan 26 uur, en 'missing' als er nog nooit een run
    is gelogd.
    """
    now = datetime.utcnow()
    stale_cutoff = STALE_AFTER_HOURS * 3600
    engines_out = []
    any_warning = False

    # Uitgangspunt zijn de actieve shops: een shop zonder run telt als 'missing'.
    active_shops = db.query(models.DimShop).filter(models.DimShop.active == True).all()  # noqa: E712

    for engine_name, label in NIGHTLY_ENGINES:
        # Per shop de meest recente run van deze engine.
        latest_per_shop = (
            db.query(
                models.EngineRun.shop_id,
                func.max(models.EngineRun.started_at).label("max_started"),
            )
            .filter(models.EngineRun.engine_name == engine_name)
            .group_by(models.EngineRun.shop_id)
            .subquery()
        )
        runs = (
            db.query(models.EngineRun)
            .join(
                latest_per_shop,
                (models.EngineRun.shop_id == latest_per_shop.c.shop_id)
                & (models.EngineRun.started_at == latest_per_shop.c.max_started),
            )
            .filter(models.EngineRun.engine_name == engine_name)
            .all()
        )
        runs_by_shop = {r.shop_id: r for r in runs}

        # Per actieve shop een status; shops zonder run zijn 'missing',
        # succesvolle runs ouder dan de drempel zijn 'stale'.
        shops = []
        for shop in active_shops:
            r = runs_by_shop.get(shop.id)
            if r is None:
                shop_status = "missing"
                shops.append({
                    "shop_id": shop.id,
                    "shop_code": shop.shop_code,
                    "status": shop_status,
                    "last_run_at": None,
                    "error_message": None,
                })
                continue
            if r.status == "failed":
                shop_status = "failed"
            elif r.started_at and (now - r.started_at).total_seconds() > stale_cutoff:
                shop_status = "stale"
            else:
                shop_status = r.status  # success (of nog running)
            shops.append({
                "shop_id": shop.id,
                "shop_code": shop.shop_code,
                "status": shop_status,
                "last_run_at": r.started_at.isoformat() if r.started_at else None,
                "error_message": r.error_message,
            })

        # Engine-status: slechtste status over alle actieve shops.
        # failed > missing > stale > success.
        shop_statuses = {s["status"] for s in shops}
        if "failed" in shop_statuses:
            status = "failed"
        elif "missing" in shop_statuses:
            status = "missing"
        elif "stale" in shop_statuses:
            status = "stale"
        elif shops:
            status = "success"
        else:
            status = "missing"  # geen actieve shops geconfigureerd

        run_times = [r.started_at for r in runs if r.started_at]
        last_run_at = max(run_times) if run_times else None
        error_message = next(
            (s["error_message"] for s in shops if s["status"] == "failed" and s["error_message"]),
            None,
        )

        if status != "success":
            any_warning = True
        engines_out.append({
            "engine": engine_name,
            "label": label,
            "status": status,
            "last_run_at": last_run_at.isoformat() if last_run_at else None,
            "error_message": error_message,
            "shops": shops,
        })

    return {
        "overall": "warning" if any_warning else "ok",
        "checked_at": now.isoformat(),
        "engines": engines_out,
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
        # Volledige competition-intelligence-laag: dekking, prijs/promo-events,
        # beschikbaarheid, elasticiteit en profielen.
        from engine.competition_intelligence import run_all as run_competition_intelligence
        run_competition_intelligence(db)
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.skus_processed = processed
        run.skus_skipped = skipped
    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = str(e)

    # Cost/usage-metering van deze job (§37): duur + resultaat per modelrun.
    try:
        from services.metering import record_usage
        duur_ms = (run.completed_at - run.started_at).total_seconds() * 1000 if run.completed_at else None
        record_usage(
            "job", module="pricing_engine",
            username=current_user.username,
            job_id=f"model_run:{run.id}",
            status_code=200 if run.status == "completed" else 500,
            duration_ms=duur_ms,
            quantity=float(run.skus_processed or 0),
            extra={"status": run.status},
            flush=True,
        )
    except Exception:
        pass

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
