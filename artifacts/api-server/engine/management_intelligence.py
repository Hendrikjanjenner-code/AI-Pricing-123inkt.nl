"""
Management Intelligence Engine.

Aggregeert per categorie:
- Waarom is een concurrent relevant?
- Wat ontbreekt er in ons assortiment?
- Welke categorie heeft het grootste groeipotentieel?
- Welke concurrent moet gemonitord worden?

Output: gestructureerde JSON geschikt voor de management-view.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session
import models


def build_management_insights(db: Session, category: Optional[str] = None) -> list[dict]:
    """
    Genereer management-inzichten per categorie.

    Args:
        category: filter op specifieke categorie (of None voor alle)

    Returns:
        lijst van insight-dicts per categorie
    """
    # Haal alle categoryscores op
    q = db.query(models.CategoryCompetitorRelevance)
    if category:
        q = q.filter(models.CategoryCompetitorRelevance.category == category)
    relevance_rows = q.order_by(
        models.CategoryCompetitorRelevance.category,
        models.CategoryCompetitorRelevance.combined_score.desc(),
    ).all()

    if not relevance_rows:
        return []

    # Groepeer per categorie
    categories: dict[str, list] = {}
    for row in relevance_rows:
        categories.setdefault(row.category, []).append(row)

    insights = []
    for cat, rows in categories.items():
        top_comp = rows[0]  # hoogste combined score
        high = [r for r in rows if r.relevance_label == "HIGH"]
        monitor = [r for r in rows if r.relevance_label == "MONITOR"]

        # Actiepunten bepalen
        actiepunten = []
        if top_comp.coverage_index < 50:
            actiepunten.append({
                "prioriteit": "hoog",
                "actie": f"Uitbreid coverage in '{cat}': {top_comp.competitor_name} "
                         f"heeft {top_comp.coverage_index:.0f}% overlap — versterk assortiment.",
            })
        if top_comp.opportunity_score > 60:
            actiepunten.append({
                "prioriteit": "hoog",
                "actie": f"Hoge kans in '{cat}': opportunity score {top_comp.opportunity_score:.0f}. "
                         "Overweeg assortimentsuitbreiding.",
            })
        if len(high) == 0:
            actiepunten.append({
                "prioriteit": "gemiddeld",
                "actie": f"Geen HIGH-concurrenten in '{cat}' — categorie heeft beperkte externe druk.",
            })

        # Ontbrekende merken aggregeren
        missing_brands = set()
        for r in rows[:3]:
            for b in (r.missing_brands or []):
                missing_brands.add(b)

        # Groeipotentie ranking (op basis van opportunity score van beste concurrent)
        growth_potential = round(top_comp.opportunity_score, 1)

        insights.append({
            "category": cat,
            "top_competitor": top_comp.competitor_name,
            "top_competitor_combined_score": round(top_comp.combined_score, 1),
            "top_competitor_traffic_light": top_comp.traffic_light,
            "high_relevance_count": len(high),
            "monitor_count": len(monitor),
            "total_competitors_analyzed": len(rows),
            "coverage_index": round(top_comp.coverage_index, 1),
            "opportunity_score": round(top_comp.opportunity_score, 1),
            "growth_potential": growth_potential,
            "missing_brands": list(missing_brands)[:5],
            "actiepunten": actiepunten,
            "waarom_relevant": top_comp.relevance_explanation or f"{top_comp.competitor_name} is de meest relevante concurrent in '{cat}'.",
            "wat_ontbreekt": top_comp.opportunity_explanation or "Geen specifieke assortimentsgaten geïdentificeerd.",
            "te_monitoren": [r.competitor_name for r in monitor[:3]],
            "run_date": top_comp.run_date.isoformat() if top_comp.run_date else date.today().isoformat(),
        })

    # Sorteer op groeipotentieel (aflopend)
    insights.sort(key=lambda x: x["growth_potential"], reverse=True)
    return insights
