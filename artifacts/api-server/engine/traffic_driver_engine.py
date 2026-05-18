"""
Traffic Driver Engine
Berekent Traffic Driver Score (TDS) en Entry Product Score (EPS) per SKU.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List
import random
from sqlalchemy.orm import Session
from models import DimProduct, FactTrafficDaily, FactSearchDemandDaily, FactTrafficIntelligenceDaily


# ── Gewichten ─────────────────────────────────────────────────────────────────

TDS_WEIGHTS = {
    "seo_traffic_factor":       0.20,
    "sea_traffic_factor":       0.10,
    "organic_visibility":       0.15,
    "search_volume_factor":     0.20,
    "landing_page_factor":      0.10,
    "new_customer_factor":      0.15,
    "ctr_factor":               0.05,
    "trend_factor":             0.05,
}

EPS_WEIGHTS = {
    "first_product_pct":        0.40,
    "new_customer_first_order": 0.35,
    "landing_conversions":      0.25,
}

TDS_CATEGORY_MODIFIERS = {
    "Ink & Toner":     1.15,
    "Paper":           0.90,
    "Office Supplies": 0.85,
    "Electronics":     1.05,
    "Printers":        1.10,
    "Packaging":       0.75,
    "Cleaning":        0.80,
    "Furniture":       0.80,
    "Canteen":         0.70,
}


def _category_modifier(category: str) -> float:
    for k, v in TDS_CATEGORY_MODIFIERS.items():
        if k.lower() in (category or "").lower():
            return v
    return 0.90


def calculate_traffic_driver_score(
    seo_traffic: int,
    sea_traffic: int,
    organic_visibility: float,
    search_volume: int,
    landing_page_sessions: int,
    new_customer_entries: int,
    ctr: float,
    trend_index: float,
    category: str,
    max_traffic_ref: int = 5000,
    max_volume_ref: int = 50000,
) -> Dict[str, Any]:
    """Bereken TDS 0–1 op basis van traffic-factoren."""
    seo_f = min(1.0, seo_traffic / max(1, max_traffic_ref))
    sea_f = min(1.0, sea_traffic / max(1, max_traffic_ref * 0.5))
    vis_f = min(1.0, organic_visibility)
    vol_f = min(1.0, search_volume / max(1, max_volume_ref))
    lp_f  = min(1.0, landing_page_sessions / max(1, max_traffic_ref * 0.4))
    nc_f  = min(1.0, new_customer_entries / max(1, max_traffic_ref * 0.3))
    ctr_f = min(1.0, ctr / 0.10)           # 10% CTR = perfecte score
    trend_f = min(1.0, max(0.0, trend_index))

    tds = (
        seo_f     * TDS_WEIGHTS["seo_traffic_factor"]
        + sea_f   * TDS_WEIGHTS["sea_traffic_factor"]
        + vis_f   * TDS_WEIGHTS["organic_visibility"]
        + vol_f   * TDS_WEIGHTS["search_volume_factor"]
        + lp_f    * TDS_WEIGHTS["landing_page_factor"]
        + nc_f    * TDS_WEIGHTS["new_customer_factor"]
        + ctr_f   * TDS_WEIGHTS["ctr_factor"]
        + trend_f * TDS_WEIGHTS["trend_factor"]
    ) * _category_modifier(category)

    tds = round(min(1.0, tds), 3)

    if tds >= 0.80:
        label = "KRITIEK TRAFFIC DRIVER"
    elif tds >= 0.60:
        label = "STERK TRAFFIC DRIVER"
    elif tds >= 0.40:
        label = "MATIG TRAFFIC DRIVER"
    else:
        label = "LAAG TRAFFIC DRIVER"

    return {
        "traffic_driver_score": tds,
        "tds_label": label,
        "seo_factor": round(seo_f, 3),
        "sea_factor": round(sea_f, 3),
        "organic_factor": round(vis_f, 3),
        "volume_factor": round(vol_f, 3),
        "new_customer_factor": round(nc_f, 3),
    }


def calculate_entry_product_score(
    first_product_pct: float,
    new_customer_first_order_pct: float,
    landing_page_conversion_rate: float,
) -> float:
    """EPS: hoe vaak is dit product het startpunt van een aankoop."""
    eps = (
        first_product_pct          * EPS_WEIGHTS["first_product_pct"]
        + new_customer_first_order_pct * EPS_WEIGHTS["new_customer_first_order"]
        + landing_page_conversion_rate * EPS_WEIGHTS["landing_conversions"]
    )
    return round(min(1.0, eps), 3)


def get_traffic_driver_dashboard(db: Session) -> Dict[str, Any]:
    """Traffic Driver overzichtsdashboard."""
    from models import FactTrafficDriverScoreDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactTrafficDriverScoreDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs = (
        db.query(FactTrafficDriverScoreDaily)
        .filter(FactTrafficDriverScoreDaily.date == latest)
        .order_by(FactTrafficDriverScoreDaily.traffic_driver_score.desc())
        .all()
    )

    kritiek = [r for r in recs if r.tds_label and "KRITIEK" in r.tds_label]
    sterk = [r for r in recs if r.tds_label and "STERK" in r.tds_label]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "kritiek_count": len(kritiek),
        "sterk_count": len(sterk),
        "gemiddelde_tds": avg_f("traffic_driver_score"),
        "gemiddelde_eps": avg_f("entry_product_score"),
        "totaal_seo_traffic": sum(r.seo_traffic or 0 for r in recs),
        "totaal_sea_traffic": sum(r.sea_traffic or 0 for r in recs),
        "totaal_nieuwe_klanten": sum(r.new_customer_entries or 0 for r in recs),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "seo_traffic": r.seo_traffic or 0,
                "sea_traffic": r.sea_traffic or 0,
                "totaal_traffic": r.total_traffic or 0,
                "zoekvolume": r.search_volume or 0,
                "nieuwe_klanten": r.new_customer_entries or 0,
                "organic_visibility": float(r.organic_visibility or 0),
                "ctr": float(r.ctr or 0),
                "eerste_product_pct": float(r.first_product_in_session_pct or 0),
                "traffic_driver_score": float(r.traffic_driver_score or 0),
                "entry_product_score": float(r.entry_product_score or 0),
                "tds_label": r.tds_label,
                "toelichting_nl": r.toelichting_nl,
            }
            for r in recs
        ],
    }
