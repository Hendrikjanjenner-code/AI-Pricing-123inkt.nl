"""
Break-even & Cost Change Intelligence routes.
Endpoints voor kostprijswijziging, PPFS, break-even en marketing-vs-korting analyse.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Any, Optional
from pydantic import BaseModel

from database import get_db
from auth import get_current_user
from models import (
    DimProduct, FactCostChangeDaily, FactBreakEvenAnalysisDaily,
    FactPricePassThroughDaily, FactMarketingVsDiscountDaily,
    FactSalesDaily, FactMarketingCostDaily,
)
from engine.cost_change_engine import get_cost_change_dashboard, calculate_ppfs, calculate_mps
from engine.break_even_engine import get_break_even_dashboard, simulate_price_reduction
from engine.price_pass_through_engine import get_ppfs_dashboard, compute_ppfs_record
from engine.marketing_margin_engine import (
    get_meds_dashboard, calculate_meds,
    simulate_price_reduction_scenario, simulate_seo_scenario, simulate_sea_scenario,
)

router = APIRouter(prefix="/api", tags=["break-even"])


# ── Kostprijswijziging ────────────────────────────────────────────────────────

@router.get("/kostprijswijziging")
def get_kostprijswijziging_dashboard(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Kostprijswijziging dashboard: alle SKU's met cost-change scores."""
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    return get_cost_change_dashboard(db, sku_q=sku_q)


@router.get("/kostprijswijziging/sku/{sku_id}")
def get_kostprijswijziging_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Kostprijswijziging detail voor één SKU."""
    rec = (
        db.query(FactCostChangeDaily)
        .filter(FactCostChangeDaily.sku_id == sku_id)
        .order_by(FactCostChangeDaily.date.desc())
        .first()
    )
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        raise HTTPException(404, "SKU niet gevonden")

    if not rec:
        raise HTTPException(404, "Geen kostprijswijziging data voor dit SKU")

    return {
        "sku_id": sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "datum": str(rec.date),
        "inkoopprijs_oud": float(rec.previous_cost_price or 0),
        "inkoopprijs_nieuw": float(rec.current_cost_price or 0),
        "wijziging_pct": float(rec.cost_change_pct or 0),
        "wijziging_type": rec.cost_change_type,
        "transportkosten": float(rec.transport_cost or 0),
        "fulfillment": float(rec.fulfillment_cost or 0),
        "marketingkosten": float(rec.marketing_cost or 0),
        "operationeel": float(rec.operational_cost or 0),
        "totale_eenheidskosten": float(rec.total_unit_cost or 0),
        "verkoopprijs": float(rec.current_selling_price or 0),
        "bruto_marge_pct": float(rec.gross_margin or 0),
        "netto_marge_pct": float(rec.net_margin or 0),
        "contributiemarge": float(rec.contribution_margin or 0),
        "ppfs_score": float(rec.ppfs_score or 0),
        "mps_score": float(rec.mps_score or 0),
        "severity": rec.severity,
        "aanbeveling": rec.aanbeveling,
        "reden_nl": rec.reason_nl,
    }


# ── PPFS — Price Pass-through ─────────────────────────────────────────────────

@router.get("/ppfs")
def get_ppfs_overzicht(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Price Pass-through Feasibility Score dashboard voor alle SKU's."""
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    return get_ppfs_dashboard(db, sku_q=sku_q)


@router.get("/ppfs/sku/{sku_id}")
def get_ppfs_sku(
    sku_id: str,
    cost_change_pct: float = Query(10.0, description="Inkoopprijswijziging in %"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Bereken live PPFS voor één SKU bij opgegeven inkoopprijswijziging."""
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        raise HTTPException(404, "SKU niet gevonden")

    result = compute_ppfs_record(prod, cost_change_pct, db)
    result["sku_naam"] = prod.product_name
    return result


# ── Break-even analyse ────────────────────────────────────────────────────────

@router.get("/break-even")
def get_break_even_overzicht(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Break-even dashboard voor alle SKU's."""
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    return get_break_even_dashboard(db, sku_q=sku_q)


@router.get("/break-even/sku/{sku_id}")
def get_break_even_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Break-even detail voor één SKU (meest recente analyse)."""
    rec = (
        db.query(FactBreakEvenAnalysisDaily)
        .filter(FactBreakEvenAnalysisDaily.sku_id == sku_id)
        .order_by(FactBreakEvenAnalysisDaily.date.desc())
        .first()
    )
    if not rec:
        raise HTTPException(404, "Geen break-even data voor dit SKU")

    return {
        "sku_id": sku_id,
        "naam": rec.sku_name,
        "categorie": rec.category,
        "datum": str(rec.date),
        "scenario_type": rec.scenario_type,
        "huidige_prijs": float(rec.current_price or 0),
        "nieuwe_prijs": float(rec.proposed_price or 0),
        "prijswijziging_pct": float(rec.price_change_pct or 0),
        "huidige_marge_per_unit": float(rec.current_margin_per_unit or 0),
        "nieuwe_marge_per_unit": float(rec.new_margin_per_unit or 0),
        "margeverlies_per_unit": float(rec.margin_loss_per_unit or 0),
        "break_even_extra_units": float(rec.break_even_extra_units or 0),
        "break_even_extra_units_pct": float(rec.break_even_extra_units_pct or 0),
        "break_even_extra_omzet": float(rec.break_even_extra_revenue or 0),
        "break_even_extra_traffic": float(rec.break_even_extra_traffic or 0),
        "break_even_conversie_uplift": float(rec.required_conversion_uplift or 0),
        "beds_score": float(rec.break_even_difficulty_score or 0),
        "beds_label": rec.beds_label,
        "waarschuwing": rec.waarschuwing,
        "aanbeveling": rec.aanbeveling,
        "toelichting_nl": rec.toelichting_nl,
    }


class SimulatiePrijsverlagingRequest(BaseModel):
    sku_id: str
    nieuwe_prijs: float


@router.post("/break-even/simuleer")
def simuleer_prijsverlaging(
    req: SimulatiePrijsverlagingRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Simuleer een prijsverlaging en bereken live break-even voor een SKU."""
    return simulate_price_reduction(req.sku_id, req.nieuwe_prijs, db)


# ── Marketing vs Korting ──────────────────────────────────────────────────────

@router.get("/marketing-vs-korting")
def get_meds_overzicht(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """MEDS dashboard: marketing vs korting vergelijking voor alle SKU's."""
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    return get_meds_dashboard(db, sku_q=sku_q)


class MarketingVsKortingRequest(BaseModel):
    sku_id: str
    prijsverlaging_pct: float = -10.0          # negatief
    extra_seo_budget: float = 500.0
    extra_sea_budget: float = 500.0


@router.post("/marketing-vs-korting/simuleer")
def simuleer_marketing_vs_korting(
    req: MarketingVsKortingRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Vergelijk prijsverlaging vs SEO vs SEA scenario's voor één SKU."""
    prod = db.query(DimProduct).filter(DimProduct.sku_id == req.sku_id).first()
    if not prod:
        raise HTTPException(404, "SKU niet gevonden")

    # Basisgegevens
    from sqlalchemy import func as sqlfunc
    avg_units = db.query(sqlfunc.avg(FactSalesDaily.units_sold)).filter(
        FactSalesDaily.sku_id == req.sku_id
    ).scalar() or 10
    current_units = int(avg_units)

    mkt_rec = db.query(FactMarketingCostDaily).filter(
        FactMarketingCostDaily.sku_id == req.sku_id
    ).order_by(FactMarketingCostDaily.date.desc()).first()

    current_price = float(prod.current_price or 0)
    cost_price = float(prod.cost_price or current_price * 0.6)
    current_revenue = current_price * current_units
    current_margin_pct = ((current_price - cost_price) / current_price * 100) if current_price > 0 else 30.0
    roas = float(mkt_rec.roas) if mkt_rec and mkt_rec.roas else 3.0
    conversion_rate = 0.025
    current_traffic = int(current_units / conversion_rate) if conversion_rate > 0 else 400

    # Scenario's
    scenario_a = simulate_price_reduction_scenario(
        prod, req.prijsverlaging_pct, current_units, current_revenue, current_margin_pct, roas
    )
    scenario_b = simulate_seo_scenario(
        prod, req.extra_seo_budget, current_units, current_revenue, current_margin_pct, current_traffic, conversion_rate
    )
    scenario_c = simulate_sea_scenario(
        prod, req.extra_sea_budget, current_units, current_revenue, current_margin_pct, current_traffic, conversion_rate
    )

    # MEDS score
    meds = calculate_meds(
        margin_after_marketing=scenario_b["expected_margin_eur"],
        margin_after_discount=scenario_a["expected_margin_eur"],
        roas=scenario_b["expected_roas"],
        elasticity=None,
    )

    return {
        "sku_id": req.sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "huidig": {
            "prijs": current_price,
            "afzet": current_units,
            "omzet": round(current_revenue, 2),
            "marge_pct": round(current_margin_pct, 2),
        },
        "scenario_a_prijsverlaging": scenario_a,
        "scenario_b_seo": scenario_b,
        "scenario_c_sea": scenario_c,
        "meds_score": meds["meds_score"],
        "meds_label": meds["meds_label"],
        "aanbeveling": meds["recommendation"],
        "toelichting_nl": meds["toelichting_nl"],
    }


# ── Margebescherming ──────────────────────────────────────────────────────────

@router.get("/margebescherming")
def get_margebescherming(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> Any:
    """Overzicht van alle SKU's met MPS en PPFS scores voor margebescherming."""
    latest = db.query(func.max(FactCostChangeDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs_q = (
        db.query(FactCostChangeDaily)
        .filter(FactCostChangeDaily.date == latest)
    )
    # Globale filtercontext (hiërarchie + merk). Lege selectie ≠ geen filter.
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    if sku_q is not None:
        recs_q = recs_q.filter(FactCostChangeDaily.sku_id.in_(sku_q.scalar_subquery()))
    recs = recs_q.order_by(FactCostChangeDaily.mps_score.asc()).all()

    kritiek = [r for r in recs if r.severity == "KRITIEK"]
    beschermd = [r for r in recs if r.mps_score and r.mps_score >= 0.70]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    aanbeveling_verdeling: dict = {}
    for r in recs:
        k = r.aanbeveling or "ONBEKEND"
        aanbeveling_verdeling[k] = aanbeveling_verdeling.get(k, 0) + 1

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "kritiek_count": len(kritiek),
        "beschermd_count": len(beschermd),
        "gemiddelde_mps": avg_f("mps_score"),
        "gemiddelde_ppfs": avg_f("ppfs_score"),
        "gemiddelde_netto_marge": avg_f("net_margin"),
        "aanbeveling_verdeling": aanbeveling_verdeling,
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "inkoopwijziging_pct": float(r.cost_change_pct or 0),
                "netto_marge_pct": float(r.net_margin or 0),
                "ppfs_score": float(r.ppfs_score or 0),
                "mps_score": float(r.mps_score or 0),
                "severity": r.severity,
                "aanbeveling": r.aanbeveling,
                "reden_nl": r.reason_nl,
            }
            for r in recs
        ],
    }
