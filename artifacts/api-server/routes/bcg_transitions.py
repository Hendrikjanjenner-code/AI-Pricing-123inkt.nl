"""BCG Transition Intelligence routes — /api/bcg-transities/*"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Any, Optional

from database import get_db
from auth import get_current_user
from models import FactBcgTransition
from engine.bcg_transition_engine import get_bcg_transitions

router = APIRouter(prefix="/api/bcg-transities", tags=["bcg-transities"])


@router.get("")
def list_bcg_transities(
    entity_type: Optional[str] = Query(None, description="SKU of CATEGORY"),
    from_class: Optional[str] = Query(None),
    to_class: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Overzicht van alle BCG classificatiewijzigingen."""
    data = get_bcg_transitions(db, entity_type=entity_type)

    # Filter op classificaties als meegegeven
    if from_class or to_class:
        data["transities"] = [
            t for t in data["transities"]
            if (not from_class or t["van"] == from_class.upper())
            and (not to_class or t["naar"] == to_class.upper())
        ]
        data["totaal"] = len(data["transities"])

    return data


@router.get("/sku/{sku_id}")
def get_bcg_transities_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """BCG transitiehistorie voor één specifieke SKU."""
    transities = (
        db.query(FactBcgTransition)
        .filter(FactBcgTransition.entity_id == sku_id)
        .order_by(FactBcgTransition.date.desc())
        .all()
    )
    if not transities:
        raise HTTPException(404, f"Geen BCG transities gevonden voor: {sku_id}")

    laatste = transities[0]
    return {
        "sku_id": sku_id,
        "naam": laatste.entity_name,
        "categorie": laatste.category,
        "huidige_classificatie": laatste.to_classification,
        "vorige_classificatie": laatste.from_classification,
        "laatste_transitie_datum": str(laatste.date),
        "totaal_transities": len(transities),
        "transities": [
            {
                "datum": str(t.date),
                "van": t.from_classification,
                "naar": t.to_classification,
                "trigger_code": t.trigger_code,
                "oorzaak": t.trigger_reason_nl,
                "impact": t.business_impact_nl,
                "omzet_impact_eur": float(t.revenue_impact_eur or 0),
                "aanbeveling": t.recommended_action_nl,
            }
            for t in transities
        ],
    }


@router.get("/alerts")
def get_bcg_alerts(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Actieve BCG-alerts (laatste 30 dagen)."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=30)
    transities = (
        db.query(FactBcgTransition)
        .filter(FactBcgTransition.date >= cutoff)
        .order_by(FactBcgTransition.date.desc())
        .all()
    )

    # Indelen op impact
    positief = [t for t in transities if t.to_classification in ("STAR",)]
    negatief = [t for t in transities if t.to_classification in ("DOG",)]
    aandacht = [t for t in transities if t.to_classification in ("QUESTION_MARK", "CASH_COW")]

    return {
        "periode": f"Laatste 30 dagen",
        "totaal_alerts": len(transities),
        "positief_count": len(positief),
        "negatief_count": len(negatief),
        "aandacht_count": len(aandacht),
        "totale_omzetimpact_eur": round(
            sum(float(t.revenue_impact_eur or 0) for t in transities), 2
        ),
        "alerts": [
            {
                "datum": str(t.date),
                "entiteit": t.entity_name,
                "entiteit_type": t.entity_type,
                "van": t.from_classification,
                "naar": t.to_classification,
                "trigger_code": t.trigger_code,
                "omzet_impact_eur": float(t.revenue_impact_eur or 0),
                "urgentie": "HOOG" if t.to_classification == "DOG" else (
                    "POSITIEF" if t.to_classification == "STAR" else "MONITOR"
                ),
            }
            for t in transities
        ],
    }
