"""Procurement Forecasting routes — /api/procurement/*"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Any, Optional

from database import get_db
from auth import get_current_user
from routes.global_filters import resolve_sku_filter
from models import FactProcurementForecastDaily

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("")
def get_procurement_overview(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Procurement forecast overzicht: POS + FMR scores voor alle SKU's."""
    latest = db.query(func.max(FactProcurementForecastDaily.date)).scalar() or date.today()
    q = (
        db.query(FactProcurementForecastDaily)
        .filter(FactProcurementForecastDaily.date == latest)
    )
    # Globale filtercontext: None = geen filter; een lege set matcht niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands)
    if _gf is not None:
        q = q.filter(FactProcurementForecastDaily.sku_id.in_(_gf))
    recs = q.order_by(
        FactProcurementForecastDaily.procurement_opportunity_score.desc()
    ).all()

    def avg(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs]
        return round(sum(vals) / len(vals), 4) if vals else 0

    koop_nu = [r for r in recs if r.signal_code in ("BUY_NOW", "URGENT_BUY")]
    marge_risico = [r for r in recs if r.signal_code == "MARGIN_RISK"]

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "gemiddelde_pos": avg("procurement_opportunity_score"),
        "gemiddelde_fmr": avg("future_margin_risk_score"),
        "koop_nu_count": len(koop_nu),
        "marge_risico_count": len(marge_risico),
        "totale_aanbevolen_investering_eur": round(
            sum(
                float(r.recommended_order_qty or 0) * float(r.current_purchase_price or 0)
                for r in koop_nu
            ), 2
        ),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "huidige_inkoopprijs": float(r.current_purchase_price or 0),
                "voorraad_dagen": r.current_stock_days,
                "levertijd_dagen": r.lead_time_days,
                "forecast_prijs_30d": float(r.forecast_purchase_price_30d or 0),
                "forecast_prijs_90d": float(r.forecast_purchase_price_90d or 0),
                "prijswijziging_30d_pct": float(r.price_change_pct_30d or 0),
                "prijswijziging_90d_pct": float(r.price_change_pct_90d or 0),
                "vraag_forecast_30d": r.demand_forecast_30d,
                "vraag_forecast_90d": r.demand_forecast_90d,
                "pos": float(r.procurement_opportunity_score or 0),
                "fmr": float(r.future_margin_risk_score or 0),
                "signaal_code": r.signal_code,
                "signaal_nl": r.signal_label_nl,
                "aanbevolen_order": r.recommended_order_qty,
                "aanbeveling": r.recommended_action_nl,
            }
            for r in recs
        ],
    }


@router.get("/sku/{sku_id}")
def get_procurement_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Procurement detail voor één SKU."""
    rec = (
        db.query(FactProcurementForecastDaily)
        .filter(FactProcurementForecastDaily.sku_id == sku_id)
        .order_by(FactProcurementForecastDaily.date.desc())
        .first()
    )
    if not rec:
        raise HTTPException(404, f"Geen procurement data voor SKU: {sku_id}")

    return {
        "sku_id": rec.sku_id,
        "naam": rec.sku_name,
        "categorie": rec.category,
        "datum": str(rec.date),
        "huidige_inkoopprijs": float(rec.current_purchase_price or 0),
        "voorraad_dagen": rec.current_stock_days,
        "levertijd_dagen": rec.lead_time_days,
        "forecast": {
            "prijs_30d": float(rec.forecast_purchase_price_30d or 0),
            "prijs_90d": float(rec.forecast_purchase_price_90d or 0),
            "wijziging_30d_pct": float(rec.price_change_pct_30d or 0),
            "wijziging_90d_pct": float(rec.price_change_pct_90d or 0),
            "vraag_30d": rec.demand_forecast_30d,
            "vraag_90d": rec.demand_forecast_90d,
            "seizoensfactor": float(rec.seasonality_factor or 0),
        },
        "scores": {
            "pos": float(rec.procurement_opportunity_score or 0),
            "fmr": float(rec.future_margin_risk_score or 0),
        },
        "signaal": {
            "code": rec.signal_code,
            "label": rec.signal_label_nl,
            "aanbevolen_order": rec.recommended_order_qty,
            "actie": rec.recommended_action_nl,
        },
    }


@router.get("/risico")
def get_procurement_risico(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Top SKU's met hoogste toekomstig margerisico (FMR)."""
    latest = db.query(func.max(FactProcurementForecastDaily.date)).scalar() or date.today()
    q = (
        db.query(FactProcurementForecastDaily)
        .filter(FactProcurementForecastDaily.date == latest)
    )
    # Globale filtercontext: None = geen filter; een lege set matcht niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands)
    if _gf is not None:
        q = q.filter(FactProcurementForecastDaily.sku_id.in_(_gf))
    recs = q.order_by(
        FactProcurementForecastDaily.future_margin_risk_score.desc()
    ).limit(10).all()

    return {
        "datum": str(latest),
        "top_risico_skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "fmr": float(r.future_margin_risk_score or 0),
                "pos": float(r.procurement_opportunity_score or 0),
                "prijswijziging_90d_pct": float(r.price_change_pct_90d or 0),
                "signaal_code": r.signal_code,
                "aanbeveling": r.recommended_action_nl,
            }
            for r in recs
        ],
    }
