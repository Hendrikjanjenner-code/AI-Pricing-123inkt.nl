"""
Break-even Engine
Berekent hoeveel extra afzet, traffic en conversie nodig is bij prijsverlaging/promotie.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import DimProduct, FactSalesDaily, FactMarketingCostDaily, SkuElasticity


# ── Formules ──────────────────────────────────────────────────────────────────

def calculate_margin_per_unit(price: float, cost: float, variable_cost_pct: float = 0.15) -> float:
    """Marge per eenheid na variabele kosten."""
    variable_costs = price * variable_cost_pct
    return price - cost - variable_costs


def calculate_break_even_units(
    old_margin_per_unit: float,
    new_margin_per_unit: float,
    current_units: int,
) -> float:
    """
    break_even_extra_units = margin_loss / new_unit_margin
    """
    if new_margin_per_unit <= 0:
        return float("inf")
    margin_loss = (old_margin_per_unit - new_margin_per_unit) * current_units
    if margin_loss <= 0:
        return 0.0
    return round(margin_loss / new_margin_per_unit, 1)


def calculate_break_even_traffic(
    break_even_extra_units: float,
    conversion_rate: float,
) -> float:
    """Extra bezoekers nodig = extra eenheden / conversieratio."""
    if conversion_rate <= 0 or break_even_extra_units == float("inf"):
        return float("inf")
    return round(break_even_extra_units / conversion_rate, 0)


def calculate_required_conversion_uplift(
    break_even_extra_units: float,
    current_traffic: int,
) -> float:
    """Benodigde conversie uplift = extra eenheden / huidige traffic."""
    if current_traffic <= 0 or break_even_extra_units == float("inf"):
        return float("inf")
    return round(break_even_extra_units / current_traffic, 4)


def calculate_beds(
    break_even_pct: float,
    current_units: int,
    new_margin_per_unit: float,
) -> Dict[str, Any]:
    """
    Break-even Difficulty Score (BEDS) 0–1.
    Hoe moeilijk is het de break-even te bereiken?
    """
    # Normaliseer: >100% = score 1.0 (onmogelijk), 0% = 0.0
    beds = min(1.0, break_even_pct / 100.0)

    if new_margin_per_unit <= 0:
        beds = 1.0

    if beds <= 0.20:
        label = "HAALBAAR"
        waarschuwing = None
    elif beds <= 0.45:
        label = "UITDAGEND"
        waarschuwing = "HIGH_VOLUME_REQUIRED_FOR_BREAK_EVEN"
    elif beds <= 0.70:
        label = "MOEILIJK"
        waarschuwing = "DISCOUNT_NOT_RECOVERABLE"
    else:
        label = "ONMOGELIJK"
        waarschuwing = "PROMOTION_MARGIN_RISK"

    return {"beds_score": round(beds, 3), "beds_label": label, "waarschuwing": waarschuwing}


def generate_break_even_explanation_nl(
    scenario_type: str,
    price_change_pct: float,
    break_even_extra_units_pct: float,
    beds_label: str,
    aanbeveling: str,
) -> str:
    """Genereer Nederlandstalige toelichting voor break-even scenario."""
    toelichting = (
        f"Bij een {scenario_type.lower().replace('_', ' ')} van {abs(price_change_pct):.1f}% "
        f"is {break_even_extra_units_pct:.0f}% meer afzet nodig om break-even te blijven. "
    )
    if beds_label == "HAALBAAR":
        toelichting += "Dit is haalbaar met gerichte marketingactie."
    elif beds_label == "UITDAGEND":
        toelichting += "Dit vereist een aanzienlijke traffic- of conversietoename."
    elif beds_label == "MOEILIJK":
        toelichting += "Overweeg een kleinere prijsverlaging of gerichte marketingpush."
    else:
        toelichting += "De vereiste extra afzet is commercieel niet haalbaar. Prijsverlaging wordt afgeraden."
    return toelichting


def simulate_price_reduction(
    sku_id: str,
    proposed_price: float,
    db: Session,
) -> Dict[str, Any]:
    """Simuleer een prijsverlaging en bereken break-even voor een SKU."""
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        return {"error": "SKU niet gevonden"}

    current_price = float(prod.current_price or 0)
    cost_price = float(prod.cost_price or current_price * 0.6)

    if current_price <= 0:
        return {"error": "Ongeldige huidige prijs"}

    # Recente verkoop
    from sqlalchemy import func
    avg_units_q = (
        db.query(func.avg(FactSalesDaily.units_sold))
        .filter(FactSalesDaily.sku_id == sku_id)
        .scalar()
    )
    current_units = int(avg_units_q or 10)

    # Conversieratio (schatting)
    mkt = db.query(FactMarketingCostDaily).filter(FactMarketingCostDaily.sku_id == sku_id).first()
    conversion_rate = 0.025  # standaard 2.5%
    if mkt:
        # proxy: cac geeft indicatie van traffic
        pass

    # Marges
    old_margin = calculate_margin_per_unit(current_price, cost_price)
    new_margin = calculate_margin_per_unit(proposed_price, cost_price)
    price_change_pct = ((proposed_price - current_price) / current_price) * 100

    be_units = calculate_break_even_units(old_margin, new_margin, current_units)
    be_units_pct = (be_units / current_units * 100) if current_units > 0 and be_units != float("inf") else 999
    be_traffic = calculate_break_even_traffic(be_units, conversion_rate)
    be_conversion = calculate_required_conversion_uplift(be_units, current_units * 40)  # schat 40x traffic

    beds = calculate_beds(be_units_pct, current_units, new_margin)

    # Aanbeveling
    if beds["beds_label"] == "HAALBAAR":
        aanbeveling = "REDUCE_PRICE"
    elif beds["beds_label"] == "UITDAGEND":
        aanbeveling = "TEST_PRICE_INCREASE"
    elif beds["beds_label"] == "MOEILIJK":
        aanbeveling = "MAINTAIN_PRICE"
    else:
        aanbeveling = "MAINTAIN_PRICE"

    toelichting = generate_break_even_explanation_nl(
        "PRICE_REDUCTION", price_change_pct, be_units_pct, beds["beds_label"], aanbeveling
    )

    return {
        "sku_id": sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "huidige_prijs": current_price,
        "nieuwe_prijs": proposed_price,
        "prijswijziging_pct": round(price_change_pct, 2),
        "huidige_marge_per_unit": round(old_margin, 4),
        "nieuwe_marge_per_unit": round(new_margin, 4),
        "margeverlies_per_unit": round(old_margin - new_margin, 4),
        "huidige_afzet": current_units,
        "break_even_extra_units": be_units if be_units != float("inf") else None,
        "break_even_extra_units_pct": round(be_units_pct, 1) if be_units_pct < 999 else None,
        "break_even_extra_traffic": be_traffic if be_traffic != float("inf") else None,
        "break_even_conversie_uplift": round(be_conversion * 100, 2) if be_conversion != float("inf") else None,
        "beds_score": beds["beds_score"],
        "beds_label": beds["beds_label"],
        "waarschuwing": beds["waarschuwing"],
        "aanbeveling": aanbeveling,
        "toelichting_nl": toelichting,
    }


def get_break_even_dashboard(db: Session, sku_q=None) -> Dict[str, Any]:
    """Overzicht van alle break-even analyses.

    ``sku_q`` (optioneel): een 1-koloms SKU-query (uit sku_filter_query) om de
    resultaten te beperken tot de globale filtercontext. None = geen filter.
    """
    from models import FactBreakEvenAnalysisDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactBreakEvenAnalysisDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs_q = (
        db.query(FactBreakEvenAnalysisDaily)
        .filter(FactBreakEvenAnalysisDaily.date == latest)
    )
    if sku_q is not None:
        recs_q = recs_q.filter(FactBreakEvenAnalysisDaily.sku_id.in_(sku_q.scalar_subquery()))
    recs = recs_q.order_by(FactBreakEvenAnalysisDaily.break_even_difficulty_score.desc()).all()

    haalbaar = [r for r in recs if r.beds_label == "HAALBAAR"]
    onmogelijk = [r for r in recs if r.beds_label == "ONMOGELIJK"]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "haalbaar_count": len(haalbaar),
        "onmogelijk_count": len(onmogelijk),
        "gemiddelde_beds": avg_f("break_even_difficulty_score"),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "scenario_type": r.scenario_type,
                "huidige_prijs": float(r.current_price or 0),
                "nieuwe_prijs": float(r.proposed_price or 0),
                "prijswijziging_pct": float(r.price_change_pct or 0),
                "break_even_extra_units": float(r.break_even_extra_units or 0),
                "break_even_extra_units_pct": float(r.break_even_extra_units_pct or 0),
                "break_even_extra_traffic": float(r.break_even_extra_traffic or 0),
                "beds_score": float(r.break_even_difficulty_score or 0),
                "beds_label": r.beds_label,
                "waarschuwing": r.waarschuwing,
                "aanbeveling": r.aanbeveling,
            }
            for r in recs
        ],
    }
