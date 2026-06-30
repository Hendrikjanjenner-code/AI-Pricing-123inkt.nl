"""
Competitor Discovery Engine.

Gegeven een lijst DRS-categorieën zoekt deze module potentiële concurrenten
op basis van bekende webshop-patronen, merk-/categorie-zoekwoorden en
OEM-codes. Output: lijst {domain, competitor_name, discovery_reason,
discovery_method, categories, confidence} met status PROPOSED.

In productie zou dit worden aangevuld met externe zoek-API's (Bing/Google
Shopping). In de pilotomgeving werkt de engine op basis van een curated
kennisbank van bekende B2B/kantoorartikelen-webshops.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
import models


# ── Kennisbank: bekende concurrenten per categorie ────────────────────────────
# Dit wordt in productie vervangen door een AI-gestuurd discovery-mechanisme.

KENNISBANK: list[dict] = [
    {
        "domain": "staples.nl",
        "competitor_name": "Staples",
        "categories": ["Ink & Toner", "Paper", "Office Supplies", "Printers"],
        "discovery_method": "PATTERN",
        "confidence": 0.95,
        "discovery_reason": "Grote kantoorartikelen-retailer met brede SKU-overlap in inkt, papier en kantoorartikelen.",
    },
    {
        "domain": "bol.com",
        "competitor_name": "Bol.com",
        "categories": ["Ink & Toner", "Paper", "Office Supplies", "Electronics", "Printers"],
        "discovery_method": "KEYWORD",
        "confidence": 0.90,
        "discovery_reason": "Grootste Nederlandse marketplace met uitgebreid kantoorartikelen-assortiment.",
    },
    {
        "domain": "viking.nl",
        "competitor_name": "Viking Direct",
        "categories": ["Ink & Toner", "Paper", "Office Supplies", "Furniture", "Cleaning"],
        "discovery_method": "CATEGORY",
        "confidence": 0.92,
        "discovery_reason": "B2B kantoorartikelen-specialist met directe overlap in ink/toner en kantoorbenodigdheden.",
    },
    {
        "domain": "papierlandschaft.de",
        "competitor_name": "Papierlandschaft",
        "categories": ["Paper", "Office Supplies"],
        "discovery_method": "KEYWORD",
        "confidence": 0.72,
        "discovery_reason": "Gespecialiseerde papier-retailer actief in Benelux-grensregio.",
    },
    {
        "domain": "bechtle.com",
        "competitor_name": "Bechtle",
        "categories": ["Printers", "Electronics", "Ink & Toner"],
        "discovery_method": "OEM",
        "confidence": 0.78,
        "discovery_reason": "IT-retailer met sterk assortiment printers en OEM-cartridges.",
    },
    {
        "domain": "tonerdump.nl",
        "competitor_name": "TonerDump",
        "categories": ["Ink & Toner"],
        "discovery_method": "OEM",
        "confidence": 0.88,
        "discovery_reason": "Gespecialiseerde inkt/toner-retailer met compatible en OEM-assortiment.",
    },
    {
        "domain": "quantore.nl",
        "competitor_name": "Quantore",
        "categories": ["Paper", "Office Supplies", "Cleaning"],
        "discovery_method": "PATTERN",
        "confidence": 0.85,
        "discovery_reason": "Groothandel kantoorartikelen — directe concurrent in papier en kantoorbenodigdheden.",
    },
    {
        "domain": "amazon.nl",
        "competitor_name": "Amazon NL",
        "categories": ["Ink & Toner", "Paper", "Electronics", "Printers"],
        "discovery_method": "PATTERN",
        "confidence": 0.87,
        "discovery_reason": "Groeiende presence van Amazon in NL markt voor kantooartikelen.",
    },
    {
        "domain": "coolblue.nl",
        "competitor_name": "Coolblue",
        "categories": ["Printers", "Electronics"],
        "discovery_method": "KEYWORD",
        "confidence": 0.82,
        "discovery_reason": "Sterk in printers en randapparatuur — directe concurrent in elektronica-segment.",
    },
    {
        "domain": "office1.nl",
        "competitor_name": "Office1",
        "categories": ["Ink & Toner", "Paper", "Office Supplies", "Furniture"],
        "discovery_method": "CATEGORY",
        "confidence": 0.80,
        "discovery_reason": "Mid-size kantoorartikelen-webshop met vergelijkbaar productgamma.",
    },
]


def run_discovery(
    db: Session,
    categories: Optional[list[str]] = None,
    min_confidence: float = 0.60,
) -> dict:
    """
    Voer een discovery-run uit en sla resultaten op in competitor_discovery_queue.

    Returns:
        dict met run_id, candidates_found, candidates_new
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run = models.CompetitorDiscoveryRun(
        run_id=run_id,
        started_at=datetime.utcnow(),
        status="running",
        categories_searched=categories or [],
        parameters={"min_confidence": min_confidence},
    )
    db.add(run)
    db.flush()

    # Filter kennisbank op gewenste categorieën (of alle)
    candidates = KENNISBANK if not categories else [
        c for c in KENNISBANK
        if any(cat in c["categories"] for cat in categories)
    ]
    candidates = [c for c in candidates if c["confidence"] >= min_confidence]

    # Haal bestaande domains op om duplicaten te vermijden
    bestaande = {
        q.domain
        for q in db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain.in_([c["domain"] for c in candidates])
        ).all()
    }

    nieuw = 0
    for candidate in candidates:
        if candidate["domain"] not in bestaande:
            item = models.CompetitorDiscoveryQueue(
                domain=candidate["domain"],
                competitor_name=candidate["competitor_name"],
                discovery_reason=candidate["discovery_reason"],
                discovery_method=candidate["discovery_method"],
                categories=candidate["categories"],
                confidence=candidate["confidence"],
                status="PROPOSED",
                run_id=run_id,
            )
            db.add(item)
            nieuw += 1

    run.completed_at = datetime.utcnow()
    run.status = "completed"
    run.candidates_found = len(candidates)
    run.candidates_new = nieuw
    db.commit()

    return {
        "run_id": run_id,
        "candidates_found": len(candidates),
        "candidates_new": nieuw,
    }
