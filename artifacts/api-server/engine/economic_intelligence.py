"""Economic Intelligence Engine — externe economische signalen en risico-impact."""
from __future__ import annotations
from datetime import date, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from models import FactEconomicSignalDaily


# Demo economische signalen (realistisch scenario mei 2026)
DEMO_ECONOMIC_SIGNALS: List[Dict[str, Any]] = [
    {
        "signal_type": "RAW_MATERIAL",
        "signal_name": "Cellulose (papier) prijsstijging",
        "region": "EU",
        "severity": "HOOG",
        "severity_score": 0.75,
        "current_value": 1380.0,
        "baseline_value": 1150.0,
        "change_pct": 20.0,
        "unit": "€/ton",
        "affected_categories_json": '["Paper & Media", "Packaging"]',
        "pricing_impact_pct": 8.0,
        "margin_impact_pct": -5.5,
        "procurement_urgency": "BINNEN_MAAND",
        "signal_code": "RAW_MATERIAL_RISK_HIGH",
        "description_nl": "Celluloseprijzen stijgen door verhoogde vraag en beperkte Scandinavische productie. Impact op papier en verpakkingscategorieën.",
        "recommended_action_nl": "Verkoopprijzen papier verhogen met 6–8%. Extra voorraad inslaan voor Q2.",
        "days_valid": 45,
    },
    {
        "signal_type": "TRANSPORT",
        "signal_name": "Containervracht Shanghai–Rotterdam stijging",
        "region": "GLOBAL",
        "severity": "KRITIEK",
        "severity_score": 0.88,
        "current_value": 4850.0,
        "baseline_value": 2100.0,
        "change_pct": 131.0,
        "unit": "$/container (40ft)",
        "affected_categories_json": '["Electronics", "Furniture", "Ink & Toner"]',
        "pricing_impact_pct": 12.0,
        "margin_impact_pct": -8.0,
        "procurement_urgency": "DIRECT",
        "signal_code": "TRANSPORT_COST_RISK",
        "description_nl": "Containervrachttarieven meer dan verdubbeld door Rode Zee-omvaarroutes en capaciteitsschaarste. Kritieke impact op elektronica en meubelen.",
        "recommended_action_nl": "Alle importen via zeevracht dringend herbeoordelen. Prijsverhoging van 10–12% doorvoeren op getroffen categorieën.",
        "days_valid": 60,
    },
    {
        "signal_type": "CURRENCY",
        "signal_name": "USD/EUR wisselkoers stijging",
        "region": "GLOBAL",
        "severity": "GEMIDDELD",
        "severity_score": 0.52,
        "current_value": 1.062,
        "baseline_value": 1.105,
        "change_pct": -3.9,
        "unit": "EUR/USD",
        "affected_categories_json": '["Electronics", "Ink & Toner"]',
        "pricing_impact_pct": 4.0,
        "margin_impact_pct": -3.0,
        "procurement_urgency": "MONITOREN",
        "signal_code": "CURRENCY_RISK",
        "description_nl": "Euro verzwakt t.o.v. dollar. USD-gebaseerde inkopen (elektronica, inkt) worden duurder.",
        "recommended_action_nl": "Valutahedging overwegen voor USD-inkopen > €50k. Marges controleren op dollar-gerelateerde SKU's.",
        "days_valid": 30,
    },
    {
        "signal_type": "GEOPOLITICAL",
        "signal_name": "Handelsrestricties China–EU halfgeleiders",
        "region": "EU",
        "severity": "HOOG",
        "severity_score": 0.70,
        "current_value": 1.0,
        "baseline_value": 0.0,
        "change_pct": 100.0,
        "unit": "risico-index",
        "affected_categories_json": '["Electronics"]',
        "pricing_impact_pct": 15.0,
        "margin_impact_pct": -10.0,
        "procurement_urgency": "DIRECT",
        "signal_code": "GEOPOLITICAL_RISK",
        "description_nl": "Nieuwe EU-importbeperkingen op Chinese chips en elektronica. Levertijden elektronica stijgen met 4–8 weken.",
        "recommended_action_nl": "Elektronica assortiment diversifiëren naar Taiwan/Korea leveranciers. Extra buffer-voorraad inslaan.",
        "days_valid": 90,
    },
    {
        "signal_type": "INFLATION",
        "signal_name": "Nederlandse kerninflatie mei 2026",
        "region": "NL",
        "severity": "GEMIDDELD",
        "severity_score": 0.45,
        "current_value": 3.8,
        "baseline_value": 2.0,
        "change_pct": 90.0,
        "unit": "% (jaar-op-jaar)",
        "affected_categories_json": '["Office Supplies", "Paper & Media", "Packaging"]',
        "pricing_impact_pct": 3.5,
        "margin_impact_pct": -2.0,
        "procurement_urgency": "MONITOREN",
        "signal_code": "INFLATION_PRESSURE",
        "description_nl": "Kerninflatie van 3.8% drukt reële marges. Personeels- en energiekosten stijgen sneller dan verkoopprijzen.",
        "recommended_action_nl": "Jaarlijkse prijsverhoging van 3–4% voorbereiden. Operationele kosten kritisch evalueren.",
        "days_valid": 30,
    },
    {
        "signal_type": "SUPPLY_CHAIN",
        "signal_name": "Inktcartridge component tekort (chip shortage)",
        "region": "GLOBAL",
        "severity": "HOOG",
        "severity_score": 0.68,
        "current_value": 1.0,
        "baseline_value": 0.0,
        "change_pct": 100.0,
        "unit": "verstoringsniveau",
        "affected_categories_json": '["Ink & Toner"]',
        "pricing_impact_pct": 6.0,
        "margin_impact_pct": -4.0,
        "procurement_urgency": "BINNEN_MAAND",
        "signal_code": "SUPPLY_CHAIN_RISK",
        "description_nl": "Tekort aan microchips in printercartridges. HP en Canon melden 6–10 weken vertraging op populaire modellen.",
        "recommended_action_nl": "Bestsellers inkt prioriteit geven in inkoopplanning. Alternatieven en huismerken promoten als buffer.",
        "days_valid": 60,
    },
]


def seed_economic_signals(db: Session) -> int:
    from sqlalchemy import func
    count = db.query(func.count(FactEconomicSignalDaily.id)).scalar()
    if count and count > 0:
        return 0

    today = date.today()
    inserted = 0
    for s in DEMO_ECONOMIC_SIGNALS:
        valid_until = today + timedelta(days=s.pop("days_valid", 30))
        db.add(FactEconomicSignalDaily(
            date=today,
            valid_until=valid_until,
            **s,
        ))
        inserted += 1
    db.commit()
    return inserted


def get_economic_dashboard(db: Session) -> Dict[str, Any]:
    from sqlalchemy import func
    today = date.today()
    signals = (
        db.query(FactEconomicSignalDaily)
        .filter(FactEconomicSignalDaily.valid_until >= today)
        .order_by(FactEconomicSignalDaily.severity_score.desc())
        .all()
    )

    kritiek = [s for s in signals if s.severity == "KRITIEK"]
    hoog = [s for s in signals if s.severity == "HOOG"]
    gemiddeld = [s for s in signals if s.severity == "GEMIDDELD"]
    laag = [s for s in signals if s.severity == "LAAG"]

    max_impact = max((float(s.pricing_impact_pct or 0) for s in signals), default=0)
    avg_margin_impact = (
        sum(float(s.margin_impact_pct or 0) for s in signals) / len(signals)
        if signals else 0
    )

    return {
        "datum": str(today),
        "totaal_actieve_signalen": len(signals),
        "kritiek_count": len(kritiek),
        "hoog_count": len(hoog),
        "gemiddeld_count": len(gemiddeld),
        "laag_count": len(laag),
        "maximale_prijsimpact_pct": round(max_impact, 1),
        "gemiddelde_margeimpact_pct": round(avg_margin_impact, 1),
        "signalen": [
            {
                "id": s.id,
                "type": s.signal_type,
                "naam": s.signal_name,
                "regio": s.region,
                "ernst": s.severity,
                "ernst_score": float(s.severity_score or 0),
                "huidige_waarde": s.current_value,
                "baseline_waarde": s.baseline_value,
                "verandering_pct": float(s.change_pct or 0),
                "eenheid": s.unit,
                "prijsimpact_pct": float(s.pricing_impact_pct or 0),
                "margeimpact_pct": float(s.margin_impact_pct or 0),
                "inkoop_urgentie": s.procurement_urgency,
                "signaal_code": s.signal_code,
                "beschrijving": s.description_nl,
                "aanbeveling": s.recommended_action_nl,
                "geldig_tot": str(s.valid_until) if s.valid_until else None,
            }
            for s in signals
        ],
    }
