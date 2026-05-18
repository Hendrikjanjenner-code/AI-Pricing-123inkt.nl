"""
Explainability routes.
Endpoints voor score-uitleg, aanbeveling-uitleg en documentatiedata.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Optional

from database import get_db
from auth import get_current_user
from models import FactPricingRecommendationDaily, DimProduct
from engine.explainability_engine import (
    generate_score_explanation,
    generate_recommendation_explanation,
    generate_bcg_explanation,
    generate_alert_explanation,
    get_explainability_dashboard,
)

router = APIRouter(prefix="/api/explainability", tags=["explainability"])


@router.get("/dashboard")
def explainability_dashboard(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Overzicht betrouwbaarheidsniveaus openstaande aanbevelingen."""
    return get_explainability_dashboard(db)


@router.get("/score/{score_type}")
def uitleg_score(
    score_type: str,
    waarde: float = Query(..., ge=0.0, le=1.0),
    sku_naam: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Genereer uitleg voor een specifieke score-waarde."""
    ctx = {"sku_naam": sku_naam or "dit product"}
    return {
        "score_type": score_type,
        "waarde": waarde,
        "uitleg": generate_score_explanation(score_type, waarde, ctx),
    }


@router.get("/aanbeveling/{rec_id}")
def uitleg_aanbeveling(
    rec_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Genereer uitgebreide uitleg voor een pricing-aanbeveling."""
    rec = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.id == rec_id
    ).first()
    if not rec:
        raise HTTPException(404, "Aanbeveling niet gevonden")

    prod = db.query(DimProduct).filter(DimProduct.sku_id == rec.sku_id).first()

    rec_dict = {
        "sku_id":            rec.sku_id,
        "product_name":      prod.product_name if prod else rec.sku_id,
        "strategy_type":     rec.strategy_type,
        "current_price":     float(rec.current_price or 0),
        "recommended_price": float(rec.recommended_price or 0),
        "confidence_score":  float(rec.confidence_score or 0.5),
        "current_margin":    float(rec.expected_margin or 0),
    }

    uitleg = generate_recommendation_explanation(rec_dict, db)
    return {
        "aanbeveling_id": rec_id,
        "sku_id": rec.sku_id,
        **uitleg,
    }


@router.get("/bcg/{bcg_class}")
def uitleg_bcg(
    bcg_class: str,
    sku_naam: Optional[str] = Query(None),
    _=Depends(get_current_user),
) -> Any:
    """Genereer uitleg voor een BCG-classificatie."""
    ctx = {"sku_naam": sku_naam or "dit product"}
    return {
        "bcg_class": bcg_class,
        "uitleg": generate_bcg_explanation(bcg_class, ctx),
    }


@router.get("/alert/{alert_type}")
def uitleg_alert(
    alert_type: str,
    sku_naam: Optional[str] = Query(None),
    _=Depends(get_current_user),
) -> Any:
    """Genereer uitleg voor een alert-type."""
    ctx = {"sku_naam": sku_naam or "dit product"}
    return {
        "alert_type": alert_type,
        "uitleg": generate_alert_explanation(alert_type, ctx),
    }


@router.get("/kpi-overzicht")
def kpi_overzicht(
    _=Depends(get_current_user),
) -> Any:
    """Overzicht van alle beschikbare KPI-definities (gesynchroniseerd met frontend)."""
    return {
        "beschikbare_scores": [
            {"id": "tds",          "naam": "Traffic Driver Score",           "afkorting": "TDS"},
            {"id": "bbs",          "naam": "Basket Builder Score",           "afkorting": "BBS"},
            {"id": "sevs",         "naam": "SKU Ecosystem Value Score",      "afkorting": "SEVS"},
            {"id": "eps",          "naam": "Entry Product Score",            "afkorting": "EPS"},
            {"id": "pcis",         "naam": "Product Competition Intensity",  "afkorting": "PCIS"},
            {"id": "csrs",         "naam": "Competitor Stock Reliability",   "afkorting": "CSRS"},
            {"id": "ppfs",         "naam": "Price Pass-through Feasibility", "afkorting": "PPFS"},
            {"id": "elasticiteit", "naam": "Prijselasticiteit",              "afkorting": None},
            {"id": "confidence",   "naam": "Advies Betrouwbaarheid",         "afkorting": None},
        ]
    }
