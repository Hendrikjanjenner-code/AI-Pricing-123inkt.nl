"""Procurement Forecasting Engine — toekomstige margedruk en inkoopkansen."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import DimProduct, FactProcurementForecastDaily, FactInventoryDaily


# SKU-specifieke procurement scenario's voor demo data
SKU_PROCUREMENT_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "INK001": {
        "price_change_30d": 0.08,  "price_change_90d": 0.14,
        "pos": 0.82, "fmr": 0.71, "lead_time": 14,
        "signal": "BUY_NOW",
        "signal_nl": "Inkoopprijs stijgt verwacht +8% in 30 dagen — nu inslaan aanbevolen",
        "action": "Bestelling plaatsen voor 90 dagen voorraad tegen huidige prijs",
        "order_qty": 500,
    },
    "PAP001": {
        "price_change_30d": 0.03, "price_change_90d": 0.06,
        "pos": 0.45, "fmr": 0.38, "lead_time": 7,
        "signal": "MONITOR",
        "signal_nl": "Lichte prijsstijging verwacht — reguliere inkoopstrategie handhaven",
        "action": "Standaard inkoopritme aanhouden",
        "order_qty": 200,
    },
    "ELC001": {
        "price_change_30d": -0.04, "price_change_90d": 0.12,
        "pos": 0.68, "fmr": 0.85,
        "lead_time": 21,
        "signal": "MARGIN_RISK",
        "signal_nl": "Grote margedruk verwacht door stijgende componentprijzen in Q3",
        "action": "Verkoopprijs verhogen of alternatieve leverancier zoeken",
        "order_qty": 50,
    },
    "OFF001": {
        "price_change_30d": 0.05, "price_change_90d": 0.09,
        "pos": 0.72, "fmr": 0.55, "lead_time": 10,
        "signal": "BUY_NOW",
        "signal_nl": "Prijsstijging grondstof papier — extra voorraad inkopen vóór Q2",
        "action": "Extra inkooporder plaatsen — 60 dagen buffer opbouwen",
        "order_qty": 300,
    },
    "FRN001": {
        "price_change_30d": 0.12, "price_change_90d": 0.22,
        "pos": 0.91, "fmr": 0.88, "lead_time": 35,
        "signal": "URGENT_BUY",
        "signal_nl": "Containerprijzen stijgen +22% — kritieke margedruk in 90 dagen",
        "action": "Direct grote order plaatsen — maximale voorraadbuffer opbouwen",
        "order_qty": 30,
    },
}


def _default_scenario(sku_id: str) -> Dict[str, Any]:
    import hashlib
    h = int(hashlib.md5(sku_id.encode()).hexdigest(), 16)
    pos = round(0.15 + (h % 65) / 100, 2)
    fmr = round(0.10 + (h % 55) / 100, 2)
    p30 = round(0.01 + (h % 8) / 100, 3)
    signal = "BUY_NOW" if pos > 0.65 else ("MARGIN_RISK" if fmr > 0.65 else "STABLE")
    nl = {
        "BUY_NOW": "Prijsstijging verwacht — inkoopkans benutten",
        "MARGIN_RISK": "Margedruk verwacht — pricing aanpassen",
        "STABLE": "Stabiele inkoopmarkt — standaard strategie handhaven",
    }[signal]
    return {
        "price_change_30d": p30, "price_change_90d": p30 * 1.8,
        "pos": pos, "fmr": fmr, "lead_time": 10,
        "signal": signal, "signal_nl": nl,
        "action": "Reguliere inkoop-evaluatie uitvoeren",
        "order_qty": 100,
    }


def compute_procurement_record(
    sku_id: str,
    sku_name: str,
    category: str,
    current_purchase_price: float,
    current_stock_days: int,
    ref_date: date | None = None,
) -> Dict[str, Any]:
    sc = SKU_PROCUREMENT_SCENARIOS.get(sku_id) or _default_scenario(sku_id)
    d = ref_date or date.today()

    fp30 = round(current_purchase_price * (1 + sc["price_change_30d"]), 4)
    fp90 = round(current_purchase_price * (1 + sc["price_change_90d"]), 4)
    demand_30 = round(sc["order_qty"] * 0.35)
    demand_90 = sc["order_qty"]

    return {
        "date": d,
        "sku_id": sku_id,
        "sku_name": sku_name,
        "category": category,
        "current_purchase_price": current_purchase_price,
        "current_stock_days": current_stock_days,
        "lead_time_days": sc["lead_time"],
        "forecast_purchase_price_30d": fp30,
        "forecast_purchase_price_90d": fp90,
        "price_change_pct_30d": round(sc["price_change_30d"] * 100, 2),
        "price_change_pct_90d": round(sc["price_change_90d"] * 100, 2),
        "demand_forecast_30d": demand_30,
        "demand_forecast_90d": demand_90,
        "procurement_opportunity_score": sc["pos"],
        "future_margin_risk_score": sc["fmr"],
        "seasonality_factor": 0.55,
        "signal_code": sc["signal"],
        "signal_label_nl": sc["signal_nl"],
        "recommended_order_qty": sc["order_qty"],
        "recommended_action_nl": sc["action"],
    }


def run_procurement_engine(db: Session, ref_date: date | None = None) -> int:
    products = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()
    d = ref_date or date.today()

    for prod in products:
        cp = float(prod.cost_price or 0)
        # Probeer voorraad op te halen
        inv = (
            db.query(FactInventoryDaily)
            .filter(FactInventoryDaily.sku_id == prod.sku_id)
            .order_by(FactInventoryDaily.date.desc())
            .first()
        )
        stock_days = int(inv.days_of_stock) if inv and inv.days_of_stock else 30

        rec = compute_procurement_record(
            sku_id=prod.sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            current_purchase_price=cp,
            current_stock_days=stock_days,
            ref_date=d,
        )
        db.add(FactProcurementForecastDaily(**rec))
    db.commit()

    # Publiceer gestandaardiseerde IntelligenceSignals (§7-§8)
    from engine.signal_emitters import emit_for_engine
    emit_for_engine(db, "procurement")

    return len(products)
