"""BCG Transition Intelligence Engine — BCG classificatiewijzigingen tracken."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import FactBcgTransition, DimProduct


# Demo BCG transities (5 realistische scenario's)
DEMO_BCG_TRANSITIONS: List[Dict[str, Any]] = [
    {
        "entity_type": "SKU",
        "entity_id": "INK001",
        "entity_name": "HP 364 Black Ink Cartridge",
        "category": "Ink & Toner",
        "from_classification": "STAR",
        "to_classification": "CASH_COW",
        "from_growth_score": 0.72,
        "to_growth_score": 0.41,
        "from_market_score": 0.81,
        "to_market_score": 0.78,
        "trigger_code": "DEMAND_SHIFT_DETECTED",
        "trigger_reason_nl": "Marktvraag vertraagt door toenemende adopitie van refill-inkt en tanksystemen. HP 364 verliest groeimomentum.",
        "business_impact_nl": "Stabiele cashflow maar groei stagneert — marge-extractie prioriteren",
        "revenue_impact_eur": -12400.0,
        "recommended_action_nl": "Prijsverhoging van 4% doorvoeren. Marketing budget verlagen. Marge-optimalisatie als primaire strategie.",
        "days_ago": 8,
    },
    {
        "entity_type": "SKU",
        "entity_id": "ELC001",
        "entity_name": "Dell UltraSharp 27\" Monitor",
        "category": "Electronics",
        "from_classification": "QUESTION_MARK",
        "to_classification": "STAR",
        "from_growth_score": 0.45,
        "to_growth_score": 0.78,
        "from_market_score": 0.38,
        "to_market_score": 0.61,
        "trigger_code": "SKU_MOVED_TO_STAR",
        "trigger_reason_nl": "Thuiswerk-trend en hybride werkmodel drijft monitor-vraag. ELC001 marktaandeel gestegen door competitieve pricing actie.",
        "business_impact_nl": "Hoge groeipotentie — investeren in voorraad en marketing om marktaandeel vast te houden",
        "revenue_impact_eur": 28600.0,
        "recommended_action_nl": "Marketingbudget verhogen met 25%. Voorraad uitbreiden. Competitief prijsniveau handhaven om STAR-positie te verdedigen.",
        "days_ago": 14,
    },
    {
        "entity_type": "SKU",
        "entity_id": "FRN002",
        "entity_name": "Ergonomische Bureaustoel Pro",
        "category": "Furniture",
        "from_classification": "CASH_COW",
        "to_classification": "DOG",
        "from_growth_score": 0.32,
        "to_growth_score": 0.18,
        "from_market_score": 0.65,
        "to_market_score": 0.28,
        "trigger_code": "SKU_MOVED_TO_DOG",
        "trigger_reason_nl": "Marktaandeel verloren aan goedkopere Chinese alternatieven. Prijspremie niet meer houdbaar na containerkostenstijging.",
        "business_impact_nl": "Negatieve contributie marge — assortimentsafstoting overwegen",
        "revenue_impact_eur": -8900.0,
        "recommended_action_nl": "Product faseren uit assortiment. Resterende voorraad uitverkopen via markdowns. Vervanger identificeren.",
        "days_ago": 5,
    },
    {
        "entity_type": "SKU",
        "entity_id": "PAP003",
        "entity_name": "123inkt Huismerk Kopieerpapier A4",
        "category": "Paper & Media",
        "from_classification": "QUESTION_MARK",
        "to_classification": "STAR",
        "from_growth_score": 0.51,
        "to_growth_score": 0.74,
        "from_market_score": 0.42,
        "to_market_score": 0.68,
        "trigger_code": "PRIVATE_LABEL_BECAME_STAR",
        "trigger_reason_nl": "Huismerk kopieerpapier profiteert van A-merk prijsstijgingen. Consumenten schakelen over naar private label.",
        "business_impact_nl": "Sterke groei private label — hogere marges en klantloyaliteit",
        "revenue_impact_eur": 19200.0,
        "recommended_action_nl": "Private label assortiment uitbreiden. Proactief A-merk klanten converteren. Productkwaliteit investering verhogen.",
        "days_ago": 21,
    },
    {
        "entity_type": "CATEGORY",
        "entity_id": "Ink & Toner",
        "entity_name": "Ink & Toner categorie",
        "category": "Ink & Toner",
        "from_classification": "STAR",
        "to_classification": "CASH_COW",
        "from_growth_score": 0.65,
        "to_growth_score": 0.38,
        "from_market_score": 0.79,
        "to_market_score": 0.77,
        "trigger_code": "PRICING_POWER_DECLINING",
        "trigger_reason_nl": "Gehele inktcategorie groeit langzamer door structurele verschuiving naar digitale documenten en tankprintersystemen.",
        "business_impact_nl": "Categorie genereert stabiele kasstroom maar vraagt minder investeringen — harvest strategy",
        "revenue_impact_eur": -45000.0,
        "recommended_action_nl": "Marge-extractie strategie activeren voor gehele categorie. Private label versterken. Nieuwere categorieën investeren.",
        "days_ago": 30,
    },
]


def seed_bcg_transitions(db: Session) -> int:
    from sqlalchemy import func
    count = db.query(func.count(FactBcgTransition.id)).scalar()
    if count and count > 0:
        return 0

    today = date.today()
    for t in DEMO_BCG_TRANSITIONS:
        days = t.pop("days_ago", 0)
        transition_date = today - timedelta(days=days)
        db.add(FactBcgTransition(date=transition_date, **t))

    db.commit()
    return len(DEMO_BCG_TRANSITIONS)


def get_bcg_transitions(db: Session, entity_type: str | None = None) -> Dict[str, Any]:
    q = db.query(FactBcgTransition).order_by(FactBcgTransition.date.desc())
    if entity_type:
        q = q.filter(FactBcgTransition.entity_type == entity_type.upper())
    transitions = q.all()

    # Samenvattingsstatistieken
    to_star = [t for t in transitions if t.to_classification == "STAR"]
    to_dog = [t for t in transitions if t.to_classification == "DOG"]
    to_cow = [t for t in transitions if t.to_classification == "CASH_COW"]
    to_qm = [t for t in transitions if t.to_classification == "QUESTION_MARK"]

    return {
        "totaal": len(transitions),
        "naar_star": len(to_star),
        "naar_dog": len(to_dog),
        "naar_cash_cow": len(to_cow),
        "naar_question_mark": len(to_qm),
        "totale_omzetimpact_eur": round(
            sum(float(t.revenue_impact_eur or 0) for t in transitions), 2
        ),
        "transities": [
            {
                "id": t.id,
                "datum": str(t.date),
                "entiteit_type": t.entity_type,
                "entiteit_id": t.entity_id,
                "naam": t.entity_name,
                "categorie": t.category,
                "van": t.from_classification,
                "naar": t.to_classification,
                "van_groei": t.from_growth_score,
                "naar_groei": t.to_growth_score,
                "van_markt": t.from_market_score,
                "naar_markt": t.to_market_score,
                "trigger_code": t.trigger_code,
                "oorzaak": t.trigger_reason_nl,
                "impact": t.business_impact_nl,
                "omzet_impact_eur": float(t.revenue_impact_eur or 0),
                "aanbeveling": t.recommended_action_nl,
            }
            for t in transitions
        ],
    }
