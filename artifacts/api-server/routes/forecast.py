"""Forecast & Risk API — forecasts met horizon en risicosignalen (§20)."""
from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from services.engine_jobs import start_engine_job
from engine.forecast_engine import run_forecast_engine, get_forecast_dashboard

router = APIRouter(prefix="/api/forecast", tags=["forecast-risk"])


@router.get("/dashboard")
def forecast_dashboard(
    horizon: int = Query(30, description="Forecast-horizon in dagen (30 of 90)"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    if horizon not in (30, 90):
        horizon = 30
    return get_forecast_dashboard(db, horizon=horizon, shop_id=shop_id)


@router.get("/sku/{sku_id}")
def forecast_sku(
    sku_id: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    from engine.signal_publisher import resolve_shop_id
    sid = resolve_shop_id(db, shop_id)
    rows = (
        db.query(models.FactForecastDaily)
        .filter(models.FactForecastDaily.sku_id == sku_id,
                models.FactForecastDaily.shop_id == sid)
        .order_by(models.FactForecastDaily.run_date.desc(),
                  models.FactForecastDaily.horizon_days)
        .limit(16)
        .all()
    )
    return [
        {
            "run_date": str(r.run_date),
            "type": r.forecast_type,
            "horizon_dagen": r.horizon_days,
            "waarde": float(r.forecast_value or 0),
            "laag": float(r.lower_bound or 0),
            "hoog": float(r.upper_bound or 0),
            "confidence": float(r.confidence or 0),
            "trend_pct": float(r.trend_pct or 0),
            "factoren": r.factors or {},
            "model_version": r.model_version,
        }
        for r in rows
    ]


@router.post("/run")
def trigger_forecast_run(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    return start_engine_job(
        "forecast", run_forecast_engine,
        shop_id=shop_id, username=current_user.username,
        audit_entity_id="forecast_risk",
        audit_details=lambda r: (f"Forecast engine: {r.get('forecasts', 0)} forecasts, "
                                 f"{r.get('risk_signals', 0)} risicosignalen"),
    )
