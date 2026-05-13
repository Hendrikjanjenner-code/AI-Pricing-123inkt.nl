"""Operational Complexity Engine — Activity-Based Costing (ABC) per SKU."""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import DimProduct, FactOperationalComplexityDaily


# ── ABC factor gewichten ─────────────────────────────────────────────────────
FACTOR_WEIGHTS = {
    "pick_time_score": 0.15,
    "packaging_time_score": 0.12,
    "return_pressure": 0.20,
    "customer_service_load": 0.15,
    "handling_complexity": 0.12,
    "dropship_management": 0.10,
    "supplier_management": 0.08,
    "error_sensitivity": 0.08,
}

# Basisprofiel per categorie
CATEGORY_OCS_PROFILE: Dict[str, Dict[str, float]] = {
    "Ink & Toner": {
        "pick_time_score": 0.30, "packaging_time_score": 0.25,
        "return_pressure": 0.20, "customer_service_load": 0.30,
        "handling_complexity": 0.20, "dropship_management": 0.10,
        "supplier_management": 0.40, "error_sensitivity": 0.35,
    },
    "Electronics": {
        "pick_time_score": 0.40, "packaging_time_score": 0.55,
        "return_pressure": 0.70, "customer_service_load": 0.65,
        "handling_complexity": 0.60, "dropship_management": 0.70,
        "supplier_management": 0.50, "error_sensitivity": 0.65,
    },
    "Furniture": {
        "pick_time_score": 0.80, "packaging_time_score": 0.85,
        "return_pressure": 0.60, "customer_service_load": 0.55,
        "handling_complexity": 0.85, "dropship_management": 0.80,
        "supplier_management": 0.60, "error_sensitivity": 0.45,
    },
    "Paper & Media": {
        "pick_time_score": 0.35, "packaging_time_score": 0.30,
        "return_pressure": 0.10, "customer_service_load": 0.15,
        "handling_complexity": 0.25, "dropship_management": 0.05,
        "supplier_management": 0.20, "error_sensitivity": 0.15,
    },
    "Office Supplies": {
        "pick_time_score": 0.30, "packaging_time_score": 0.28,
        "return_pressure": 0.25, "customer_service_load": 0.25,
        "handling_complexity": 0.22, "dropship_management": 0.10,
        "supplier_management": 0.25, "error_sensitivity": 0.20,
    },
}
DEFAULT_OCS = {
    "pick_time_score": 0.35, "packaging_time_score": 0.30,
    "return_pressure": 0.25, "customer_service_load": 0.25,
    "handling_complexity": 0.25, "dropship_management": 0.15,
    "supplier_management": 0.25, "error_sensitivity": 0.25,
}

HOURLY_LABOUR_RATE = 18.50   # €/uur gemiddeld NL magazijn


def _get_profile(category: str) -> Dict[str, float]:
    for k, v in CATEGORY_OCS_PROFILE.items():
        if k.lower() in (category or "").lower():
            return v
    return DEFAULT_OCS


def _ocs_label(score: float) -> str:
    if score < 0.25:
        return "LAAG"
    elif score < 0.50:
        return "GEMIDDELD"
    elif score < 0.75:
        return "HOOG"
    return "KRITIEK"


def _action(ocs: float, category: str) -> str:
    if ocs >= 0.75:
        return "Direct operationeel vereenvoudigen — overweeg assortimentsafstoting"
    elif ocs >= 0.50:
        return "Procesoptimalisatie prioriteit — ABC-kosten herijken in pricing"
    elif ocs >= 0.25:
        return "Monitoren — operationele kosten opnemen in margeberekening"
    return "Laag risico — standaard operationele aanpak"


def compute_ocs_record(
    sku_id: str,
    sku_name: str,
    category: str,
    selling_price: float,
    ref_date: date | None = None,
) -> Dict[str, Any]:
    profile = _get_profile(category)

    # OCS = gewogen gemiddelde van factoren
    ocs = sum(profile[k] * w for k, w in FACTOR_WEIGHTS.items())
    ocs = round(min(max(ocs, 0.0), 1.0), 4)

    # Personeelskosten: OCS × gemiddelde handelingstijd × uurloon
    handling_minutes = 2 + ocs * 18   # 2–20 minuten
    labour_cost = round((handling_minutes / 60) * HOURLY_LABOUR_RATE, 4)
    operational_cost = round(labour_cost * 1.3, 4)   # + 30% overhead

    return {
        "date": ref_date or date.today(),
        "sku_id": sku_id,
        "sku_name": sku_name,
        "category": category,
        **profile,
        "operational_complexity_score": ocs,
        "ocs_label": _ocs_label(ocs),
        "labour_cost_per_unit": labour_cost,
        "total_operational_cost": operational_cost,
        "recommended_action": _action(ocs, category),
    }


def run_operational_complexity_engine(db: Session, ref_date: date | None = None) -> int:
    products = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()
    d = ref_date or date.today()
    for prod in products:
        rec = compute_ocs_record(
            sku_id=prod.sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            selling_price=float(prod.current_price or 1),
            ref_date=d,
        )
        db.add(FactOperationalComplexityDaily(**rec))
    db.commit()
    return len(products)
