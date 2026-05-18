"""
Basket Intelligence Engine
Berekent Basket Builder Score (BBS) en winkelmandanalyse per SKU.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from models import DimProduct, FactBasketAffinity


# ── Gewichten ─────────────────────────────────────────────────────────────────

BBS_WEIGHTS = {
    "attach_rate":           0.30,
    "co_occurrence":         0.20,
    "basket_uplift":         0.20,
    "cross_sell_frequency":  0.15,
    "incremental_margin":    0.15,
}

# Categorie-specifieke basket-profielen
CATEGORY_BASKET_PROFILE = {
    "Ink & Toner": {
        "baseline_attach": 0.45, "basket_lift": 1.35,
        "cross_sell_freq": 2.1, "margin_uplift": 0.15,
    },
    "Paper": {
        "baseline_attach": 0.55, "basket_lift": 1.40,
        "cross_sell_freq": 2.5, "margin_uplift": 0.12,
    },
    "Office Supplies": {
        "baseline_attach": 0.60, "basket_lift": 1.50,
        "cross_sell_freq": 3.2, "margin_uplift": 0.18,
    },
    "Packaging": {
        "baseline_attach": 0.65, "basket_lift": 1.60,
        "cross_sell_freq": 2.8, "margin_uplift": 0.20,
    },
    "Cleaning": {
        "baseline_attach": 0.50, "basket_lift": 1.30,
        "cross_sell_freq": 2.0, "margin_uplift": 0.10,
    },
    "Electronics": {
        "baseline_attach": 0.35, "basket_lift": 1.25,
        "cross_sell_freq": 1.5, "margin_uplift": 0.08,
    },
    "Furniture": {
        "baseline_attach": 0.25, "basket_lift": 1.20,
        "cross_sell_freq": 1.2, "margin_uplift": 0.05,
    },
}

DEFAULT_BASKET_PROFILE = {
    "baseline_attach": 0.40, "basket_lift": 1.30,
    "cross_sell_freq": 2.0, "margin_uplift": 0.12,
}


def _get_basket_profile(category: str) -> Dict[str, float]:
    for k, v in CATEGORY_BASKET_PROFILE.items():
        if k.lower() in (category or "").lower():
            return v
    return DEFAULT_BASKET_PROFILE


def calculate_basket_builder_score(
    attach_rate: float,
    co_occurrence_score: float,
    basket_uplift_normalized: float,
    cross_sell_frequency: float,
    incremental_margin_normalized: float,
) -> Dict[str, Any]:
    """
    Basket Builder Score (BBS) 0–1.
    Hoe sterk draagt dit SKU bij aan winkelmandvulling?
    """
    bbs = (
        min(1.0, attach_rate)                    * BBS_WEIGHTS["attach_rate"]
        + min(1.0, co_occurrence_score)          * BBS_WEIGHTS["co_occurrence"]
        + min(1.0, basket_uplift_normalized)     * BBS_WEIGHTS["basket_uplift"]
        + min(1.0, cross_sell_frequency / 5.0)  * BBS_WEIGHTS["cross_sell_frequency"]
        + min(1.0, incremental_margin_normalized) * BBS_WEIGHTS["incremental_margin"]
    )
    bbs = round(min(1.0, bbs), 3)

    if bbs >= 0.75:
        label = "KRITIEK WINKELMANDVULLER"
    elif bbs >= 0.55:
        label = "STERK WINKELMANDVULLER"
    elif bbs >= 0.35:
        label = "MATIG WINKELMANDVULLER"
    else:
        label = "ZWAKKE WINKELMANDVULLER"

    return {"bbs_score": bbs, "bbs_label": label}


def calculate_incremental_margin(
    avg_basket_value: float,
    base_basket_value: float,
    margin_pct: float,
) -> float:
    """Extra marge door basket-uitbreiding van dit SKU."""
    incremental_revenue = max(0, avg_basket_value - base_basket_value)
    return round(incremental_revenue * margin_pct, 4)


def generate_basket_record(
    prod: DimProduct,
    db: Session,
    ref_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Genereer een volledig basket intelligence record voor één SKU."""
    import random
    if ref_date is None:
        ref_date = date.today()

    profile = _get_basket_profile(prod.category or "")

    # Simuleer realistische waarden op basis van categorieprofiel
    rng = random.Random(hash(prod.sku_id) % 10000)
    attach_rate = min(0.95, profile["baseline_attach"] + rng.uniform(-0.10, 0.15))
    co_occ = min(1.0, rng.uniform(0.30, 0.85))
    basket_lift = profile["basket_lift"] + rng.uniform(-0.15, 0.20)
    basket_uplift_norm = min(1.0, (basket_lift - 1.0) / 1.0)  # 0=geen lift, 1=+100%
    cross_sell = profile["cross_sell_freq"] + rng.uniform(-0.5, 0.8)
    sp = float(prod.current_price or 10)
    avg_basket = sp * basket_lift * rng.uniform(0.9, 1.1)
    base_basket = sp * rng.uniform(0.8, 1.0)
    margin_pct = (float(prod.current_price or 10) - float(prod.cost_price or 6)) / max(1, float(prod.current_price or 10))
    inc_margin = calculate_incremental_margin(avg_basket, base_basket, margin_pct)
    inc_margin_norm = min(1.0, inc_margin / max(1, sp * 0.3))

    bbs = calculate_basket_builder_score(attach_rate, co_occ, basket_uplift_norm, cross_sell, inc_margin_norm)

    # Top co-SKU's (gesimuleerd op basis van categorie)
    all_skus = [p.sku_id for p in db.query(DimProduct).filter(
        DimProduct.category == prod.category,
        DimProduct.sku_id != prod.sku_id,
        DimProduct.lifecycle_status == "active",
    ).limit(5).all()]
    top_co = ",".join(all_skus[:3])

    return {
        "date": ref_date,
        "sku_id": prod.sku_id,
        "sku_name": prod.product_name,
        "category": prod.category,
        "attach_rate": round(attach_rate, 4),
        "avg_basket_value": round(avg_basket, 4),
        "avg_items_per_basket": round(cross_sell + 1.0, 2),
        "basket_co_occurrence_score": round(co_occ, 3),
        "cross_sell_frequency": round(cross_sell, 2),
        "incremental_margin": round(inc_margin, 4),
        "basket_uplift_eur": round(avg_basket - base_basket, 4),
        "basket_builder_score": bbs["bbs_score"],
        "bbs_label": bbs["bbs_label"],
        "top_co_skus": top_co,
    }


def get_basket_dashboard(db: Session) -> Dict[str, Any]:
    """Basket Intelligence dashboard."""
    from models import FactBasketIntelligenceDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactBasketIntelligenceDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs = (
        db.query(FactBasketIntelligenceDaily)
        .filter(FactBasketIntelligenceDaily.date == latest)
        .order_by(FactBasketIntelligenceDaily.basket_builder_score.desc())
        .all()
    )

    kritiek = [r for r in recs if r.bbs_label and "KRITIEK" in r.bbs_label]
    sterk = [r for r in recs if r.bbs_label and "STERK" in r.bbs_label]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "kritiek_count": len(kritiek),
        "sterk_count": len(sterk),
        "gemiddelde_bbs": avg_f("basket_builder_score"),
        "gemiddelde_attach_rate": avg_f("attach_rate"),
        "gemiddelde_basket_waarde": avg_f("avg_basket_value"),
        "totale_incrementele_marge": round(sum(float(r.incremental_margin or 0) for r in recs), 2),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "attach_rate": float(r.attach_rate or 0),
                "gem_mandwaarde": float(r.avg_basket_value or 0),
                "gem_items": float(r.avg_items_per_basket or 0),
                "co_occurrence": float(r.basket_co_occurrence_score or 0),
                "cross_sell_freq": float(r.cross_sell_frequency or 0),
                "incrementele_marge": float(r.incremental_margin or 0),
                "basket_uplift_eur": float(r.basket_uplift_eur or 0),
                "bbs_score": float(r.basket_builder_score or 0),
                "bbs_label": r.bbs_label,
                "top_co_skus": (r.top_co_skus or "").split(",") if r.top_co_skus else [],
            }
            for r in recs
        ],
    }
