"""
Marketing Margin Engine
Vergelijkt marketing-push vs prijsverlaging en berekent MEDS score.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import (
    DimProduct, FactSalesDaily, FactMarketingCostDaily,
    SkuCompetitionScore, SkuElasticity,
)


# ── Constanten ────────────────────────────────────────────────────────────────

# Aanname: extra SEO budget verhoogt traffic met factor per EUR
SEO_TRAFFIC_MULTIPLIER = 0.8   # 1 EUR SEO → 0.8 extra bezoekers (langetermijn)
SEA_TRAFFIC_MULTIPLIER = 2.5   # 1 EUR SEA → 2.5 extra bezoekers (kortetermijn)

# Prijselasticiteitsschatting per % verlaging
DEFAULT_ELASTICITY = -0.8


def _estimate_demand_uplift(price_change_pct: float, elasticity: float) -> float:
    """Schat % volume uplift bij prijswijziging."""
    return abs(elasticity * price_change_pct)  # positief, want verlaging = meer vraag


def simulate_price_reduction_scenario(
    prod: DimProduct,
    price_change_pct: float,    # negatief getal, bv -10
    current_units: int,
    current_revenue: float,
    current_margin_pct: float,
    roas: float,
    elasticity: float | None = None,
) -> Dict[str, Any]:
    """Scenario A: prijsverlaging."""
    if elasticity is None:
        elasticity = DEFAULT_ELASTICITY

    uplift_pct = _estimate_demand_uplift(price_change_pct, elasticity)
    new_price = float(prod.current_price or 0) * (1 + price_change_pct / 100)
    new_units = int(current_units * (1 + uplift_pct / 100))
    new_revenue = new_units * new_price

    # Marge daalt door lagere prijs
    new_margin_pct = current_margin_pct + price_change_pct * 0.7  # 70% van prijsdaling gaat naar marge
    new_margin_eur = new_revenue * (new_margin_pct / 100)

    return {
        "scenario_type": "PRICE_REDUCTION",
        "price_change_pct": price_change_pct,
        "expected_revenue": round(new_revenue, 2),
        "expected_margin": round(new_margin_pct, 2),
        "expected_margin_eur": round(new_margin_eur, 2),
        "expected_units": new_units,
        "expected_traffic": None,
        "expected_conversion": None,
        "expected_roas": None,
    }


def simulate_seo_scenario(
    prod: DimProduct,
    extra_seo_budget: float,
    current_units: int,
    current_revenue: float,
    current_margin_pct: float,
    current_traffic: int,
    conversion_rate: float,
) -> Dict[str, Any]:
    """Scenario B: extra SEO budget."""
    extra_traffic = extra_seo_budget * SEO_TRAFFIC_MULTIPLIER
    new_traffic = current_traffic + int(extra_traffic)
    new_units = int(new_traffic * conversion_rate) + current_units
    price = float(prod.current_price or 0)
    new_revenue = new_units * price
    margin_after_seo = (new_revenue * current_margin_pct / 100) - extra_seo_budget
    roas = (new_revenue - current_revenue) / extra_seo_budget if extra_seo_budget > 0 else 0

    return {
        "scenario_type": "PUSH_SEO",
        "extra_budget": extra_seo_budget,
        "expected_revenue": round(new_revenue, 2),
        "expected_margin": round(current_margin_pct, 2),
        "expected_margin_eur": round(margin_after_seo, 2),
        "expected_units": new_units,
        "expected_traffic": new_traffic,
        "expected_conversion": round(conversion_rate, 4),
        "expected_roas": round(roas, 2),
    }


def simulate_sea_scenario(
    prod: DimProduct,
    extra_sea_budget: float,
    current_units: int,
    current_revenue: float,
    current_margin_pct: float,
    current_traffic: int,
    conversion_rate: float,
) -> Dict[str, Any]:
    """Scenario C: extra SEA budget."""
    extra_traffic = extra_sea_budget * SEA_TRAFFIC_MULTIPLIER
    new_traffic = current_traffic + int(extra_traffic)
    new_units = int(new_traffic * conversion_rate) + current_units
    price = float(prod.current_price or 0)
    new_revenue = new_units * price
    margin_after_sea = (new_revenue * current_margin_pct / 100) - extra_sea_budget
    roas = (new_revenue - current_revenue) / extra_sea_budget if extra_sea_budget > 0 else 0

    return {
        "scenario_type": "PUSH_SEA",
        "extra_budget": extra_sea_budget,
        "expected_revenue": round(new_revenue, 2),
        "expected_margin": round(current_margin_pct, 2),
        "expected_margin_eur": round(margin_after_sea, 2),
        "expected_units": new_units,
        "expected_traffic": new_traffic,
        "expected_conversion": round(conversion_rate, 4),
        "expected_roas": round(roas, 2),
    }


def calculate_meds(
    margin_after_marketing: float,
    margin_after_discount: float,
    roas: float,
    elasticity: float | None,
) -> Dict[str, Any]:
    """
    Marketing Efficiency vs Discount Score (MEDS).
    >0.5 → marketing slimmer; <0.5 → korting slimmer.
    """
    # Factor 1: marketing levert meer marge op
    margin_factor = 0.6 if margin_after_marketing > margin_after_discount else 0.2

    # Factor 2: ROAS > 3 = uitstekend
    roas_factor = min(1.0, roas / 5.0)

    # Factor 3: hoge elasticiteit = korting werkt beter = lagere MEDS
    elast_val = abs(elasticity) if elasticity else 0.8
    elasticity_factor = max(0.0, 1.0 - (elast_val / 2.0))

    meds = round(margin_factor * 0.50 + roas_factor * 0.30 + elasticity_factor * 0.20, 3)

    if meds >= 0.65:
        label = "MARKETING_BETER"
        aanbeveling = "PUSH_TRAFFIC_INSTEAD"
        toelichting = "Marketing levert meer marge op dan prijsverlaging. Verhoog SEO/SEA budget."
    elif meds >= 0.40:
        label = "VERGELIJKBAAR"
        aanbeveling = "TEST_PRICE_INCREASE"
        toelichting = "Beide opties vergelijkbaar. Test met kleine prijswijziging naast marketingcampagne."
    else:
        label = "KORTING_BETER"
        aanbeveling = "REDUCE_PRICE"
        toelichting = "Gerichte prijsverlaging effectiever. Hoge elasticiteit maakt volumeboost haalbaar."

    return {
        "meds_score": meds,
        "meds_label": label,
        "recommendation": aanbeveling,
        "toelichting_nl": toelichting,
    }


def get_meds_dashboard(db: Session) -> Dict[str, Any]:
    """MEDS overzichtsdashboard."""
    from models import FactMarketingVsDiscountDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactMarketingVsDiscountDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    # Neem één record per SKU (meest recente, PRICE_REDUCTION scenario als basis)
    subq = (
        db.query(
            FactMarketingVsDiscountDaily.sku_id,
            func.max(FactMarketingVsDiscountDaily.id).label("max_id")
        )
        .filter(FactMarketingVsDiscountDaily.date == latest)
        .group_by(FactMarketingVsDiscountDaily.sku_id)
        .subquery()
    )
    recs = (
        db.query(FactMarketingVsDiscountDaily)
        .join(subq, FactMarketingVsDiscountDaily.id == subq.c.max_id)
        .order_by(FactMarketingVsDiscountDaily.meds_score.desc())
        .all()
    )

    mkt_beter = [r for r in recs if r.recommended_strategy in ("PUSH_SEO", "PUSH_SEA", "PUSH_TRAFFIC_INSTEAD")]
    korting_beter = [r for r in recs if r.recommended_strategy == "REDUCE_PRICE"]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "marketing_beter_count": len(mkt_beter),
        "korting_beter_count": len(korting_beter),
        "gemiddelde_meds": avg_f("meds_score"),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "scenario": r.scenario_type,
                "verwachte_omzet": float(r.expected_revenue or 0),
                "verwachte_marge_pct": float(r.expected_margin or 0),
                "verwachte_marge_eur": float(r.expected_margin_eur or 0),
                "verwachte_traffic": r.expected_traffic,
                "verwachte_conversie": float(r.expected_conversion or 0),
                "verwachte_roas": float(r.expected_roas or 0),
                "meds_score": float(r.meds_score or 0),
                "aanbeveling": r.recommended_strategy,
                "toelichting_nl": r.toelichting_nl,
            }
            for r in recs
        ],
    }
