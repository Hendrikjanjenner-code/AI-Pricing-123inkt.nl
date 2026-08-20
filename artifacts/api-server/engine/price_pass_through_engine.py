"""
Price Pass-through Engine
Berekent PPFS scores voor alle SKU's en slaat resultaten op.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import (
    DimProduct, FactPricePassThroughDaily,
    SkuCompetitionScore, SkuElasticity, FactBcgClassificationDaily,
)
from engine.cost_change_engine import calculate_ppfs


def compute_ppfs_record(
    prod: DimProduct,
    supplier_cost_change_pct: float,
    db: Session,
    ref_date: date | None = None,
) -> Dict[str, Any]:
    """Bereken een volledig PPFS record voor één SKU."""
    if ref_date is None:
        ref_date = date.today()

    ppfs_data = calculate_ppfs(
        sku_id=prod.sku_id,
        category=prod.category or "",
        cost_change_pct=supplier_cost_change_pct,
        db=db,
    )

    # Stel voorgestelde prijswijziging voor op basis van PPFS
    if ppfs_data["ppfs_label"] == "STERK":
        proposed_pct = supplier_cost_change_pct  # volledig doorberekenen
    elif ppfs_data["ppfs_label"] == "GOED":
        proposed_pct = supplier_cost_change_pct * 0.65
    elif ppfs_data["ppfs_label"] == "MATIG":
        proposed_pct = supplier_cost_change_pct * 0.35
    else:
        proposed_pct = 0.0

    pass_through_ratio = round(proposed_pct / supplier_cost_change_pct, 3) if supplier_cost_change_pct else 0.0

    return {
        "date": ref_date,
        "sku_id": prod.sku_id,
        "sku_name": prod.product_name,
        "category": prod.category,
        "supplier_cost_change_pct": supplier_cost_change_pct,
        "proposed_price_change_pct": round(proposed_pct, 2),
        "pass_through_ratio": pass_through_ratio,
        "ppfs_score": ppfs_data["ppfs_score"],
        "ppfs_label": ppfs_data["ppfs_label"],
        "elasticity_score": ppfs_data["elasticity_factor"],
        "pricing_power_score": ppfs_data["pricing_power"],
        "competition_pressure": 1.0 - ppfs_data["competition_factor"],
        "bcg_factor": ppfs_data["bcg_factor"],
        "demand_factor": ppfs_data["demand_factor"],
        "conversion_health": ppfs_data.get("conversion_health", 0.6),
        "recommendation": ppfs_data["recommendation"],
        "reason_code": ppfs_data["ppfs_label"],
        "toelichting_nl": ppfs_data["toelichting_nl"],
    }


def get_ppfs_dashboard(db: Session, sku_q=None) -> Dict[str, Any]:
    """PPFS overzichtsdashboard voor alle SKU's.

    ``sku_q`` (optioneel): een 1-koloms SKU-query (uit sku_filter_query) om de
    resultaten te beperken tot de globale filtercontext. None = geen filter.
    """
    from sqlalchemy import func

    latest = db.query(func.max(FactPricePassThroughDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs_q = (
        db.query(FactPricePassThroughDaily)
        .filter(FactPricePassThroughDaily.date == latest)
    )
    if sku_q is not None:
        recs_q = recs_q.filter(FactPricePassThroughDaily.sku_id.in_(sku_q.scalar_subquery()))
    recs = recs_q.order_by(FactPricePassThroughDaily.ppfs_score.desc()).all()

    sterk = [r for r in recs if r.ppfs_label == "STERK"]
    risicovol = [r for r in recs if r.ppfs_label == "RISICOVOL"]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "sterk_count": len(sterk),
        "risicovol_count": len(risicovol),
        "gemiddelde_ppfs": avg_f("ppfs_score"),
        "gemiddelde_kostwijziging_pct": avg_f("supplier_cost_change_pct"),
        "verdeling": {
            "STERK": len([r for r in recs if r.ppfs_label == "STERK"]),
            "GOED": len([r for r in recs if r.ppfs_label == "GOED"]),
            "MATIG": len([r for r in recs if r.ppfs_label == "MATIG"]),
            "RISICOVOL": len([r for r in recs if r.ppfs_label == "RISICOVOL"]),
        },
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "inkoopwijziging_pct": float(r.supplier_cost_change_pct or 0),
                "voorstel_pct": float(r.proposed_price_change_pct or 0),
                "doorberekening_ratio": float(r.pass_through_ratio or 0),
                "ppfs_score": float(r.ppfs_score or 0),
                "ppfs_label": r.ppfs_label,
                "elasticiteit": float(r.elasticity_score or 0),
                "pricing_power": float(r.pricing_power_score or 0),
                "concurrentiedruk": float(r.competition_pressure or 0),
                "aanbeveling": r.recommendation,
                "toelichting_nl": r.toelichting_nl,
            }
            for r in recs
        ],
    }
