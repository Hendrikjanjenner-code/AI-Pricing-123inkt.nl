"""Cost Intelligence Engine — volledige kostenstructuur per SKU."""
from __future__ import annotations
from datetime import date, datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from models import DimProduct, FactCostDaily, FactSalesDaily, FactPriceDaily


# ── Gewichten voor kostenopbouw ──────────────────────────────────────────────

# Kostenratios als % van verkoopprijs (gemiddeld per categorie)
CATEGORY_COST_PROFILE: Dict[str, Dict[str, float]] = {
    "Ink & Toner": {
        "transport_pct": 0.03, "dropship_pct": 0.0, "fulfilment_pct": 0.05,
        "packaging_pct": 0.02, "labour_pct": 0.04, "marketplace_fee_pct": 0.0,
        "return_rate": 0.03, "overhead_pct": 0.06,
    },
    "Paper & Media": {
        "transport_pct": 0.05, "dropship_pct": 0.0, "fulfilment_pct": 0.06,
        "packaging_pct": 0.03, "labour_pct": 0.03, "marketplace_fee_pct": 0.0,
        "return_rate": 0.02, "overhead_pct": 0.05,
    },
    "Office Supplies": {
        "transport_pct": 0.04, "dropship_pct": 0.0, "fulfilment_pct": 0.05,
        "packaging_pct": 0.02, "labour_pct": 0.04, "marketplace_fee_pct": 0.0,
        "return_rate": 0.04, "overhead_pct": 0.05,
    },
    "Electronics": {
        "transport_pct": 0.02, "dropship_pct": 0.15, "fulfilment_pct": 0.03,
        "packaging_pct": 0.02, "labour_pct": 0.03, "marketplace_fee_pct": 0.08,
        "return_rate": 0.12, "overhead_pct": 0.04,
    },
    "Furniture": {
        "transport_pct": 0.12, "dropship_pct": 0.20, "fulfilment_pct": 0.04,
        "packaging_pct": 0.04, "labour_pct": 0.06, "marketplace_fee_pct": 0.0,
        "return_rate": 0.08, "overhead_pct": 0.07,
    },
}
DEFAULT_COST_PROFILE = {
    "transport_pct": 0.04, "dropship_pct": 0.0, "fulfilment_pct": 0.05,
    "packaging_pct": 0.02, "labour_pct": 0.04, "marketplace_fee_pct": 0.0,
    "return_rate": 0.04, "overhead_pct": 0.05,
}


def _get_profile(category: str) -> Dict[str, float]:
    for k, v in CATEGORY_COST_PROFILE.items():
        if k.lower() in (category or "").lower():
            return v
    return DEFAULT_COST_PROFILE


def compute_cost_record(
    sku_id: str,
    sku_name: str,
    category: str,
    purchase_cost: float,
    selling_price: float,
    ref_date: date | None = None,
) -> Dict[str, Any]:
    """Bereken volledige kostenstructuur voor één SKU."""
    p = _get_profile(category)
    sp = selling_price or 1.0

    transport = round(sp * p["transport_pct"], 4)
    dropship = round(sp * p["dropship_pct"], 4)
    fulfilment = round(sp * p["fulfilment_pct"], 4)
    packaging = round(sp * p["packaging_pct"], 4)
    labour = round(sp * p["labour_pct"], 4)
    marketplace = round(sp * p["marketplace_fee_pct"], 4)
    returns = round(sp * p["return_rate"] * 0.3, 4)    # gemiddeld 30% terugstuurkosten van prijs
    overhead = round(sp * p["overhead_pct"], 4)

    total_direct = round(purchase_cost + transport + dropship + fulfilment + packaging, 4)
    total_indirect = round(labour + marketplace + returns + overhead, 4)
    total_cost = round(total_direct + total_indirect, 4)

    gross_margin = round(sp - total_direct, 4)
    net_margin = round(sp - total_cost, 4)
    net_margin_pct = round((net_margin / sp) * 100, 2) if sp > 0 else 0.0

    # Signaal
    if net_margin_pct < 5:
        signal = "MARGIN_CRITICAL"
        signal_nl = f"Netto marge slechts {net_margin_pct:.1f}% — directe actie vereist"
    elif net_margin_pct < 12:
        signal = "MARGIN_LOW"
        signal_nl = f"Netto marge {net_margin_pct:.1f}% — onder doelstelling van 12%"
    elif total_direct / sp > 0.75:
        signal = "COST_RISING"
        signal_nl = "Directe kosten > 75% van verkoopprijs — kostenreductie overwegen"
    else:
        signal = "HEALTHY"
        signal_nl = f"Gezonde netto marge van {net_margin_pct:.1f}%"

    return {
        "date": ref_date or date.today(),
        "sku_id": sku_id,
        "sku_name": sku_name,
        "category": category,
        "purchase_cost": purchase_cost,
        "transport_cost": transport,
        "dropshipping_cost": dropship,
        "fulfilment_cost": fulfilment,
        "packaging_cost": packaging,
        "labour_cost": labour,
        "marketplace_fee": marketplace,
        "return_cost": returns,
        "overhead_cost": overhead,
        "total_direct_cost": total_direct,
        "total_indirect_cost": total_indirect,
        "total_cost": total_cost,
        "selling_price": selling_price,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "net_margin_pct": net_margin_pct,
        "cost_signal": signal,
        "cost_signal_nl": signal_nl,
    }


def run_cost_engine(db: Session, ref_date: date | None = None) -> int:
    """Bereken kostenstructuur voor alle actieve SKU's."""
    products = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()
    inserted = 0
    d = ref_date or date.today()

    for prod in products:
        cost_price = float(prod.cost_price or 0)
        selling_price = float(prod.current_price or prod.cost_price or 1)
        rec = compute_cost_record(
            sku_id=prod.sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            purchase_cost=cost_price,
            selling_price=selling_price,
            ref_date=d,
        )
        db.add(FactCostDaily(**rec))
        inserted += 1

    db.commit()

    # Publiceer gestandaardiseerde IntelligenceSignals (§7-§8)
    from engine.signal_emitters import emit_for_engine
    emit_for_engine(db, "cost")

    return inserted


def get_cost_dashboard(db: Session) -> Dict[str, Any]:
    """Aggregeer kostendata voor het dashboardoverzicht."""
    from sqlalchemy import func, desc
    today = date.today()

    records = (
        db.query(FactCostDaily)
        .filter(FactCostDaily.date == today)
        .all()
    )
    if not records:
        # gebruik meest recente datum
        latest = db.query(func.max(FactCostDaily.date)).scalar()
        if latest:
            records = db.query(FactCostDaily).filter(FactCostDaily.date == latest).all()

    if not records:
        return {"skus": [], "kpis": {}}

    total_revenue = sum(float(r.selling_price or 0) for r in records)
    total_cost = sum(float(r.total_cost or 0) for r in records)
    avg_net_margin = sum(float(r.net_margin_pct or 0) for r in records) / len(records)
    critical = [r for r in records if r.cost_signal == "MARGIN_CRITICAL"]
    low_margin = [r for r in records if r.cost_signal in ("MARGIN_CRITICAL", "MARGIN_LOW")]

    sku_list = []
    for r in sorted(records, key=lambda x: float(x.net_margin_pct or 0)):
        sku_list.append({
            "sku_id": r.sku_id,
            "naam": r.sku_name,
            "categorie": r.category,
            "verkoopprijs": float(r.selling_price or 0),
            "inkoopkosten": float(r.purchase_cost or 0),
            "totale_kosten": float(r.total_cost or 0),
            "netto_marge_pct": float(r.net_margin_pct or 0),
            "netto_marge_eur": float(r.net_margin or 0),
            "signaal": r.cost_signal,
            "signaal_nl": r.cost_signal_nl,
        })

    # Kostenverdeling (gemiddeld)
    def avg(attr):
        vals = [float(getattr(r, attr) or 0) for r in records]
        return round(sum(vals) / len(vals), 4) if vals else 0

    return {
        "datum": str(today),
        "totaal_skus": len(records),
        "gemiddelde_netto_marge_pct": round(avg_net_margin, 2),
        "kritieke_marge_count": len(critical),
        "lage_marge_count": len(low_margin),
        "kostenverdeling": {
            "inkoop": avg("purchase_cost"),
            "transport": avg("transport_cost"),
            "dropshipping": avg("dropshipping_cost"),
            "fulfilment": avg("fulfilment_cost"),
            "verpakking": avg("packaging_cost"),
            "personeel": avg("labour_cost"),
            "marketplace": avg("marketplace_fee"),
            "retouren": avg("return_cost"),
            "overhead": avg("overhead_cost"),
        },
        "skus": sku_list,
    }
