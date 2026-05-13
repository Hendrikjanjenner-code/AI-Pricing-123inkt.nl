"""Economic Intelligence routes — /api/economie/*"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import Any

from database import get_db
from auth import get_current_user
from models import FactEconomicSignalDaily
from engine.economic_intelligence import get_economic_dashboard

router = APIRouter(prefix="/api/economie", tags=["economie"])


@router.get("")
def get_economie_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Economisch intelligence dashboard — alle actieve signalen."""
    return get_economic_dashboard(db)


@router.get("/signaal/{signal_id}")
def get_economie_signaal(
    signal_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Detail van één economisch signaal."""
    sig = db.query(FactEconomicSignalDaily).filter(FactEconomicSignalDaily.id == signal_id).first()
    if not sig:
        raise HTTPException(404, "Signaal niet gevonden")

    return {
        "id": sig.id,
        "datum": str(sig.date),
        "type": sig.signal_type,
        "naam": sig.signal_name,
        "regio": sig.region,
        "ernst": sig.severity,
        "ernst_score": float(sig.severity_score or 0),
        "huidige_waarde": sig.current_value,
        "baseline_waarde": sig.baseline_value,
        "verandering_pct": float(sig.change_pct or 0),
        "eenheid": sig.unit,
        "getroffen_categorieen": sig.affected_categories_json,
        "prijsimpact_pct": float(sig.pricing_impact_pct or 0),
        "margeimpact_pct": float(sig.margin_impact_pct or 0),
        "inkoop_urgentie": sig.procurement_urgency,
        "signaal_code": sig.signal_code,
        "beschrijving": sig.description_nl,
        "aanbeveling": sig.recommended_action_nl,
        "geldig_tot": str(sig.valid_until) if sig.valid_until else None,
    }


@router.get("/impact")
def get_economie_impact(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Geaggregeerde impact van alle actieve economische signalen."""
    today = date.today()
    signals = (
        db.query(FactEconomicSignalDaily)
        .filter(FactEconomicSignalDaily.valid_until >= today)
        .all()
    )

    impact_by_type = {}
    for s in signals:
        t = s.signal_type
        if t not in impact_by_type:
            impact_by_type[t] = {
                "type": t,
                "signalen": 0,
                "max_ernst_score": 0.0,
                "totale_prijsimpact_pct": 0.0,
                "totale_margeimpact_pct": 0.0,
            }
        impact_by_type[t]["signalen"] += 1
        impact_by_type[t]["max_ernst_score"] = max(
            impact_by_type[t]["max_ernst_score"], float(s.severity_score or 0)
        )
        impact_by_type[t]["totale_prijsimpact_pct"] += float(s.pricing_impact_pct or 0)
        impact_by_type[t]["totale_margeimpact_pct"] += float(s.margin_impact_pct or 0)

    return {
        "datum": str(today),
        "totale_prijsimpact_pct": round(
            sum(float(s.pricing_impact_pct or 0) for s in signals), 1
        ),
        "totale_margeimpact_pct": round(
            sum(float(s.margin_impact_pct or 0) for s in signals), 1
        ),
        "impact_per_type": list(impact_by_type.values()),
        "direct_actie_vereist": [
            {
                "signaal": s.signal_name,
                "urgentie": s.procurement_urgency,
                "aanbeveling": s.recommended_action_nl,
            }
            for s in signals
            if s.procurement_urgency == "DIRECT"
        ],
    }
