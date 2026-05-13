"""
Cost Change Intelligence Engine
Analyseert inkoopprijswijzigingen en berekent PPFS / MPS scores.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import (
    DimProduct, FactCostDaily, FactMarketingCostDaily,
    SkuCompetitionScore, SkuElasticity, FactBcgClassificationDaily,
)


# ── Constanten ────────────────────────────────────────────────────────────────

# Typische inkoopprijsschokken per type
COST_CHANGE_TYPES = {
    "SUPPLIER":    "Leveranciersprijs",
    "TRANSPORT":   "Transportkosten",
    "CURRENCY":    "Valuta-effect",
    "SURCHARGE":   "Toeslag leverancier",
    "FULFILMENT":  "Fulfilment kosten",
    "MARKETING":   "Marketingkosten",
    "DROPSHIP":    "Dropshipping kosten",
}

# Categoriegevoeligheid voor kostenstijgingen (prijselasticiteit proxy)
CATEGORY_ELASTICITY_PROXY = {
    "Ink & Toner":       0.4,
    "Office Supplies":   0.5,
    "Paper":             0.6,
    "Packaging":         0.5,
    "Cleaning":          0.4,
    "Canteen Supplies":  0.3,
    "Electronics":       0.7,
    "Furniture":         0.6,
    "Printers":          0.65,
}

# BCG klasse → pricing power factor
BCG_PRICING_POWER = {
    "INTERNAL_STAR":      0.85,
    "INTERNAL_CASH_COW":  0.80,
    "INTERNAL_QUESTION":  0.50,
    "INTERNAL_DOG":       0.30,
    "EXTERNAL_STAR":      0.85,
    "EXTERNAL_CASH_COW":  0.75,
    "EXTERNAL_QUESTION":  0.45,
    "EXTERNAL_DOG":       0.25,
}


def _elasticity_score(elasticity: float | None, category: str) -> float:
    """0=hoog elastisch (moeilijk door te berekenen), 1=inelastisch (makkelijk)."""
    if elasticity is None:
        elasticity = -CATEGORY_ELASTICITY_PROXY.get(category, 0.5)
    # Elasticiteit is negatief; -1.5 = zeer elastisch, -0.2 = inelastisch
    # Normaliseer: clamp tussen -2 en 0, draai om
    e = max(-2.0, min(0.0, elasticity))
    return round(1.0 - (abs(e) / 2.0), 3)


def _bcg_factor(sku_id: str, db: Session) -> float:
    rec = (
        db.query(FactBcgClassificationDaily)
        .filter(
            FactBcgClassificationDaily.entity_id == sku_id,
            FactBcgClassificationDaily.entity_type == "SKU",
        )
        .order_by(FactBcgClassificationDaily.date.desc())
        .first()
    )
    if not rec:
        return 0.55
    score = BCG_PRICING_POWER.get(rec.internal_bcg_class, 0.55)
    ext = BCG_PRICING_POWER.get(rec.external_bcg_class, 0.55)
    return round((score * 0.6 + ext * 0.4), 3)


def _competition_factor(sku_id: str, db: Session) -> float:
    """0=lage concurrentiedruk (makkelijk verhogen), 1=hoge druk (moeilijk)."""
    rec = db.query(SkuCompetitionScore).filter(SkuCompetitionScore.sku_id == sku_id).first()
    if not rec:
        return 0.5
    pcis = float(rec.pcis_score or 0.5)
    # Hoge PCIS = zwakke positie = meer druk
    return round(min(1.0, pcis), 3)


def calculate_ppfs(
    sku_id: str,
    category: str,
    cost_change_pct: float,
    db: Session,
) -> Dict[str, Any]:
    """
    Price Pass-through Feasibility Score (PPFS).
    Geeft aan hoe realistisch het is een kostenstijging door te berekenen.
    Returns dict met ppfs_score, sub-factoren, label en aanbeveling.
    """
    # Elasticiteitsfactor
    elast_rec = db.query(SkuElasticity).filter(SkuElasticity.sku_id == sku_id).first()
    elast_val = float(elast_rec.own_price_elasticity) if elast_rec and elast_rec.own_price_elasticity else None
    elasticity_factor = _elasticity_score(elast_val, category)

    # BCG factor
    bcg_factor = _bcg_factor(sku_id, db)

    # Concurrentiefactor (omgekeerd: hoge PCIS = hoge druk = lagere factor)
    comp_rec = db.query(SkuCompetitionScore).filter(SkuCompetitionScore.sku_id == sku_id).first()
    pcis = float(comp_rec.pcis_score) if comp_rec and comp_rec.pcis_score else 0.5
    competition_factor = round(1.0 - min(1.0, pcis), 3)

    # Pricing power
    pricing_power = float(comp_rec.pricing_power_score) if comp_rec and getattr(comp_rec, "pricing_power_score", None) else 0.5

    # Demand factor (hogere kostenstijging = meer risico)
    demand_factor = max(0.2, 1.0 - min(1.0, cost_change_pct / 30.0))

    # PPFS = gewogen gemiddelde
    ppfs = round(
        elasticity_factor * 0.25
        + bcg_factor * 0.20
        + competition_factor * 0.20
        + pricing_power * 0.20
        + demand_factor * 0.15,
        3
    )

    # Label
    if ppfs >= 0.80:
        label = "STERK"
        aanbeveling = "FULL_PASS_THROUGH"
        toelichting = "Pricing power hoog en lage concurrentiedruk — kostenstijging volledig doorberekenen."
    elif ppfs >= 0.60:
        label = "GOED"
        aanbeveling = "PARTIAL_PASS_THROUGH"
        toelichting = "Gedeeltelijke doorberekening mogelijk; test met +50–75% van de kostenstijging."
    elif ppfs >= 0.40:
        label = "MATIG"
        aanbeveling = "TEST_PRICE_INCREASE"
        toelichting = "Voorzichtig verhogen. Monitor conversie en concurrentie nauwlettend."
    else:
        label = "RISICOVOL"
        aanbeveling = "NO_PASS_THROUGH"
        toelichting = "Prijsverhoging te risicovol. Overweeg marketing-push of marge tijdelijk accepteren."

    return {
        "ppfs_score": ppfs,
        "ppfs_label": label,
        "elasticity_factor": elasticity_factor,
        "bcg_factor": bcg_factor,
        "competition_factor": competition_factor,
        "pricing_power": pricing_power,
        "demand_factor": demand_factor,
        "recommendation": aanbeveling,
        "toelichting_nl": toelichting,
    }


def calculate_mps(
    net_margin: float,
    cost_change_pct: float,
    ppfs_score: float,
) -> Dict[str, Any]:
    """
    Margin Protection Score (MPS).
    Hoe goed is de marge beschermd na de kostenstijging?
    """
    # Hoge marge + goede PPFS = hoge bescherming
    margin_factor = min(1.0, max(0.0, net_margin / 40.0))  # 40% marge = perfecte score
    ppfs_factor = ppfs_score

    # Kostenschok impact
    shock_factor = max(0.0, 1.0 - cost_change_pct / 50.0)  # >50% = 0

    mps = round(margin_factor * 0.40 + ppfs_factor * 0.40 + shock_factor * 0.20, 3)

    if mps >= 0.70:
        label = "BESCHERMD"
        severity = "LAAG"
    elif mps >= 0.45:
        label = "MATIG RISICO"
        severity = "MEDIUM"
    elif mps >= 0.25:
        label = "HOOG RISICO"
        severity = "HOOG"
    else:
        label = "KRITIEK"
        severity = "KRITIEK"

    return {"mps_score": mps, "mps_label": label, "severity": severity}


def get_cost_change_dashboard(db: Session) -> Dict[str, Any]:
    """Volledig kostprijswijziging dashboard."""
    from models import FactCostChangeDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactCostChangeDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": [], "samenvatting": {}}

    recs = (
        db.query(FactCostChangeDaily)
        .filter(FactCostChangeDaily.date == latest)
        .order_by(FactCostChangeDaily.ppfs_score.asc())
        .all()
    )

    kritiek = [r for r in recs if r.severity == "KRITIEK"]
    hoog = [r for r in recs if r.severity == "HOOG"]
    vol_doorberekenen = [r for r in recs if r.aanbeveling == "FULL_PASS_THROUGH"]
    geen_doorberekenen = [r for r in recs if r.aanbeveling == "NO_PASS_THROUGH"]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "kritiek_count": len(kritiek),
        "hoog_count": len(hoog),
        "vol_doorberekenen_count": len(vol_doorberekenen),
        "geen_doorberekenen_count": len(geen_doorberekenen),
        "gemiddelde_ppfs": avg_f("ppfs_score"),
        "gemiddelde_kostprijswijziging_pct": avg_f("cost_change_pct"),
        "gemiddelde_mps": avg_f("mps_score"),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "inkoopprijs_oud": float(r.previous_cost_price or 0),
                "inkoopprijs_nieuw": float(r.current_cost_price or 0),
                "wijziging_pct": float(r.cost_change_pct or 0),
                "type": r.cost_change_type,
                "netto_marge": float(r.net_margin or 0),
                "ppfs_score": float(r.ppfs_score or 0),
                "mps_score": float(r.mps_score or 0),
                "severity": r.severity,
                "aanbeveling": r.aanbeveling,
                "reden_nl": r.reason_nl,
            }
            for r in recs
        ],
    }
