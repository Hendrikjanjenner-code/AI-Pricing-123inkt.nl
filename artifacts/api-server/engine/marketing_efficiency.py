"""Marketing Efficiency Engine — CAC, ROAS, SEO/SEA efficiëntie per SKU."""
from __future__ import annotations
from datetime import date
from typing import Dict, Any
from sqlalchemy.orm import Session
from models import DimProduct, FactMarketingCostDaily


# Standaard marketing budgetverdeling als % van omzet
CATEGORY_MARKETING_PROFILE: Dict[str, Dict[str, float]] = {
    "Ink & Toner": {
        "seo_budget_pct": 0.015, "sea_budget_pct": 0.025,
        "seo_conv_rate": 0.045, "sea_conv_rate": 0.038,
        "avg_order_value": 24.0,
    },
    "Electronics": {
        "seo_budget_pct": 0.020, "sea_budget_pct": 0.055,
        "seo_conv_rate": 0.022, "sea_conv_rate": 0.031,
        "avg_order_value": 180.0,
    },
    "Paper & Media": {
        "seo_budget_pct": 0.010, "sea_budget_pct": 0.015,
        "seo_conv_rate": 0.055, "sea_conv_rate": 0.042,
        "avg_order_value": 18.0,
    },
    "Office Supplies": {
        "seo_budget_pct": 0.012, "sea_budget_pct": 0.022,
        "seo_conv_rate": 0.040, "sea_conv_rate": 0.033,
        "avg_order_value": 35.0,
    },
    "Furniture": {
        "seo_budget_pct": 0.018, "sea_budget_pct": 0.040,
        "seo_conv_rate": 0.015, "sea_conv_rate": 0.018,
        "avg_order_value": 320.0,
    },
}
DEFAULT_MARKETING = {
    "seo_budget_pct": 0.014, "sea_budget_pct": 0.028,
    "seo_conv_rate": 0.035, "sea_conv_rate": 0.030,
    "avg_order_value": 45.0,
}


def _get_profile(category: str) -> Dict[str, float]:
    for k, v in CATEGORY_MARKETING_PROFILE.items():
        if k.lower() in (category or "").lower():
            return v
    return DEFAULT_MARKETING


def compute_marketing_record(
    sku_id: str,
    sku_name: str,
    category: str,
    selling_price: float,
    net_margin: float,
    daily_revenue: float,
    ref_date: date | None = None,
) -> Dict[str, Any]:
    p = _get_profile(category)
    sp = selling_price or 1.0

    # Dagelijkse marketing kosten (geschat)
    seo_cost = round(daily_revenue * p["seo_budget_pct"], 4)
    sea_cost = round(daily_revenue * p["sea_budget_pct"], 4)
    total_marketing = round(seo_cost + sea_cost, 4)

    # Volumes
    aov = p["avg_order_value"]
    seo_clicks = max(1, int(daily_revenue / aov * 8))
    seo_conv = max(0, int(seo_clicks * p["seo_conv_rate"]))
    seo_rev = round(seo_conv * sp, 2)
    sea_clicks = max(1, int(daily_revenue / aov * 5))
    sea_conv = max(0, int(sea_clicks * p["sea_conv_rate"]))
    sea_rev = round(sea_conv * sp, 2)

    # CAC
    total_conv = seo_conv + sea_conv
    cac = round(total_marketing / total_conv, 4) if total_conv > 0 else 0

    # ROAS
    total_rev = seo_rev + sea_rev
    roas = round(total_rev / total_marketing, 2) if total_marketing > 0 else 0

    # Efficiëntiescores (0–1)
    seo_eff = min(1.0, round(seo_rev / (seo_cost * 10) if seo_cost > 0 else 0, 4))
    sea_eff = min(1.0, round(sea_rev / (sea_cost * 8) if sea_cost > 0 else 0, 4))

    # Marketing dependency score
    mds = round(min(1.0, total_marketing / max(net_margin, 0.01)), 4)

    # Marge na marketing
    mam = round(net_margin - total_marketing / max(daily_revenue / sp, 1), 4)
    cm_pct = round((mam / sp) * 100, 2) if sp > 0 else 0

    # Signaal
    if roas < 2.0:
        signal = "LOW_ROAS"
        signal_nl = f"ROAS van {roas:.1f}× is onder de minimumdrempel van 2.0×"
    elif cac > sp * 0.3:
        signal = "HIGH_CAC"
        signal_nl = f"CAC €{cac:.2f} = {round(cac/sp*100)}% van verkoopprijs — te hoog"
    elif mds > 0.6:
        signal = "MARKETING_DEPENDENT"
        signal_nl = "Marge sterk afhankelijk van marketing — organisch verkeer vergroten"
    elif roas > 5.0:
        signal = "EFFICIENT"
        signal_nl = f"Uitstekende ROAS van {roas:.1f}× — marketingbudget uitbreiden overwegen"
    else:
        signal = "NORMAAL"
        signal_nl = f"ROAS {roas:.1f}× — marketing presteert binnen verwachting"

    return {
        "date": ref_date or date.today(),
        "sku_id": sku_id,
        "sku_name": sku_name,
        "category": category,
        "seo_cost": seo_cost,
        "seo_impressions": seo_clicks * 20,
        "seo_clicks": seo_clicks,
        "seo_conversions": seo_conv,
        "seo_revenue": seo_rev,
        "sea_cost": sea_cost,
        "sea_impressions": sea_clicks * 35,
        "sea_clicks": sea_clicks,
        "sea_conversions": sea_conv,
        "sea_revenue": sea_rev,
        "cac": cac,
        "roas": roas,
        "seo_efficiency": seo_eff,
        "sea_efficiency": sea_eff,
        "marketing_dependency_score": mds,
        "total_marketing_cost": total_marketing,
        "margin_after_marketing": mam,
        "contribution_margin_pct": cm_pct,
        "marketing_signal": signal,
        "marketing_signal_nl": signal_nl,
    }


def run_marketing_engine(db: Session, ref_date: date | None = None) -> int:
    products = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()
    d = ref_date or date.today()
    for prod in products:
        sp = float(prod.current_price or prod.cost_price or 1)
        cp = float(prod.cost_price or sp * 0.6)
        net_margin = round(sp - cp, 4)
        daily_rev = round(sp * 8, 2)   # ~8 verkopen per dag als basis
        rec = compute_marketing_record(
            sku_id=prod.sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            selling_price=sp,
            net_margin=net_margin,
            daily_revenue=daily_rev,
            ref_date=d,
        )
        db.add(FactMarketingCostDaily(**rec))
    db.commit()
    return len(products)
