"""
Traffic Driver & Basket Intelligence routes.
Endpoints voor TDS, BBS, SEVS, cross-sell en entry products.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any

from database import get_db
from auth import get_current_user
from models import (
    DimProduct,
    FactSkuEcosystemDaily,
    FactBasketIntelligenceDaily,
    FactTrafficDriverScoreDaily,
)
from engine.traffic_driver_engine import get_traffic_driver_dashboard
from engine.basket_intelligence import get_basket_dashboard
from engine.sku_ecosystem_engine import get_ecosystem_dashboard
from engine.cross_sell_engine import get_cross_sell_recommendations, get_cross_sell_overview

router = APIRouter(prefix="/api", tags=["ecosystem"])


# ── Traffic Driver ────────────────────────────────────────────────────────────

@router.get("/traffic-driver")
def get_traffic_driver(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Traffic Driver dashboard: TDS en EPS voor alle SKU's."""
    return get_traffic_driver_dashboard(db)


@router.get("/traffic-driver/sku/{sku_id}")
def get_traffic_driver_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Traffic Driver detail voor één SKU."""
    rec = (
        db.query(FactTrafficDriverScoreDaily)
        .filter(FactTrafficDriverScoreDaily.sku_id == sku_id)
        .order_by(FactTrafficDriverScoreDaily.date.desc())
        .first()
    )
    if not rec:
        raise HTTPException(404, "Geen traffic driver data voor dit SKU")
    return {
        "sku_id": sku_id,
        "naam": rec.sku_name,
        "categorie": rec.category,
        "datum": str(rec.date),
        "seo_traffic": rec.seo_traffic or 0,
        "sea_traffic": rec.sea_traffic or 0,
        "totaal_traffic": rec.total_traffic or 0,
        "organic_visibility": float(rec.organic_visibility or 0),
        "zoekvolume": rec.search_volume or 0,
        "nieuwe_klanten": rec.new_customer_entries or 0,
        "eerste_product_pct": float(rec.first_product_in_session_pct or 0),
        "nieuwe_klant_eerste_order_pct": float(rec.new_customer_first_order_pct or 0),
        "traffic_driver_score": float(rec.traffic_driver_score or 0),
        "entry_product_score": float(rec.entry_product_score or 0),
        "tds_label": rec.tds_label,
        "toelichting_nl": rec.toelichting_nl,
    }


# ── Basket Intelligence ───────────────────────────────────────────────────────

@router.get("/basket-intelligence")
def get_basket_intelligence(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Basket Intelligence dashboard: BBS voor alle SKU's."""
    return get_basket_dashboard(db)


@router.get("/basket-intelligence/sku/{sku_id}")
def get_basket_intelligence_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Basket Intelligence detail voor één SKU."""
    rec = (
        db.query(FactBasketIntelligenceDaily)
        .filter(FactBasketIntelligenceDaily.sku_id == sku_id)
        .order_by(FactBasketIntelligenceDaily.date.desc())
        .first()
    )
    if not rec:
        raise HTTPException(404, "Geen basket intelligence data voor dit SKU")
    return {
        "sku_id": sku_id,
        "naam": rec.sku_name,
        "categorie": rec.category,
        "datum": str(rec.date),
        "attach_rate": float(rec.attach_rate or 0),
        "gem_mandwaarde": float(rec.avg_basket_value or 0),
        "gem_items": float(rec.avg_items_per_basket or 0),
        "co_occurrence": float(rec.basket_co_occurrence_score or 0),
        "cross_sell_freq": float(rec.cross_sell_frequency or 0),
        "incrementele_marge": float(rec.incremental_margin or 0),
        "basket_uplift_eur": float(rec.basket_uplift_eur or 0),
        "bbs_score": float(rec.basket_builder_score or 0),
        "bbs_label": rec.bbs_label,
        "top_co_skus": (rec.top_co_skus or "").split(",") if rec.top_co_skus else [],
    }


# ── SKU Ecosystem ─────────────────────────────────────────────────────────────

@router.get("/sku-ecosystem")
def get_sku_ecosystem(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """SKU Ecosystem Value (SEVS) dashboard."""
    return get_ecosystem_dashboard(db)


@router.get("/sku-ecosystem/sku/{sku_id}")
def get_sku_ecosystem_detail(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Volledig ecosysteem-profiel voor één SKU."""
    eco = (
        db.query(FactSkuEcosystemDaily)
        .filter(FactSkuEcosystemDaily.sku_id == sku_id)
        .order_by(FactSkuEcosystemDaily.date.desc())
        .first()
    )
    basket = (
        db.query(FactBasketIntelligenceDaily)
        .filter(FactBasketIntelligenceDaily.sku_id == sku_id)
        .order_by(FactBasketIntelligenceDaily.date.desc())
        .first()
    )
    tds = (
        db.query(FactTrafficDriverScoreDaily)
        .filter(FactTrafficDriverScoreDaily.sku_id == sku_id)
        .order_by(FactTrafficDriverScoreDaily.date.desc())
        .first()
    )
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        raise HTTPException(404, "SKU niet gevonden")
    if not eco:
        raise HTTPException(404, "Geen ecosysteem data voor dit SKU")

    sp = float(prod.current_price or 0)
    cp = float(prod.cost_price or sp * 0.6)
    directe_marge = round((sp - cp) / sp * 100, 2) if sp > 0 else 0

    cross_sell = get_cross_sell_recommendations(sku_id, db)

    return {
        "sku_id": sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "verkoopprijs": sp,
        "inkoopprijs": cp,
        "directe_marge_pct": directe_marge,
        "ecosystem": {
            "sevs_score": float(eco.ecosystem_value_score or 0),
            "sevs_label": eco.sevs_label,
            "primaire_rol": eco.primary_sku_role,
            "secundaire_rollen": (eco.secondary_sku_role or "").split(",") if eco.secondary_sku_role else [],
            "traffic_driver_score": float(eco.traffic_driver_score or 0),
            "basket_builder_score": float(eco.basket_builder_score or 0),
            "margin_amplification_score": float(eco.margin_amplification_score or 0),
            "entry_product_score": float(eco.entry_product_score or 0),
            "repeat_contribution_score": float(eco.repeat_contribution_score or 0),
            "private_label_contribution": float(eco.private_label_contribution or 0),
            "margin_contribution_score": float(eco.margin_contribution_score or 0),
            "pricing_gevoeligheid": eco.pricing_sensitivity,
            "bescherming_advies": eco.protection_advice,
            "strategische_noot": eco.strategic_note_nl,
        },
        "basket": {
            "attach_rate": float(basket.attach_rate or 0) if basket else 0,
            "gem_mandwaarde": float(basket.avg_basket_value or 0) if basket else 0,
            "incrementele_marge": float(basket.incremental_margin or 0) if basket else 0,
            "bbs_label": basket.bbs_label if basket else None,
        },
        "traffic": {
            "seo_traffic": tds.seo_traffic or 0 if tds else 0,
            "sea_traffic": tds.sea_traffic or 0 if tds else 0,
            "zoekvolume": tds.search_volume or 0 if tds else 0,
            "nieuwe_klanten": tds.new_customer_entries or 0 if tds else 0,
            "tds_label": tds.tds_label if tds else None,
        },
        "cross_sell": cross_sell,
    }


# ── Cross-sell ────────────────────────────────────────────────────────────────

@router.get("/cross-sell")
def get_cross_sell(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Cross-sell intelligence overzicht voor alle SKU's."""
    return get_cross_sell_overview(db)


@router.get("/cross-sell/sku/{sku_id}")
def get_cross_sell_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Cross-sell aanbevelingen voor één SKU."""
    return get_cross_sell_recommendations(sku_id, db)


# ── Entry Products ────────────────────────────────────────────────────────────

@router.get("/entry-products")
def get_entry_products(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Entry Product Analyse: SKU's die het vaakst als startpunt dienen."""
    latest = db.query(func.max(FactTrafficDriverScoreDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs = (
        db.query(FactTrafficDriverScoreDaily)
        .filter(FactTrafficDriverScoreDaily.date == latest)
        .order_by(FactTrafficDriverScoreDaily.entry_product_score.desc())
        .all()
    )

    top_entry = [r for r in recs if r.entry_product_score and r.entry_product_score >= 0.60]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "top_entry_count": len(top_entry),
        "gemiddelde_eps": avg_f("entry_product_score"),
        "totaal_nieuwe_klanten": sum(r.new_customer_entries or 0 for r in recs),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "eerste_product_pct": float(r.first_product_in_session_pct or 0),
                "nieuwe_klant_eerste_order_pct": float(r.new_customer_first_order_pct or 0),
                "nieuwe_klanten": r.new_customer_entries or 0,
                "entry_product_score": float(r.entry_product_score or 0),
                "traffic_driver_score": float(r.traffic_driver_score or 0),
                "tds_label": r.tds_label,
                "toelichting_nl": r.toelichting_nl,
            }
            for r in recs
        ],
    }
