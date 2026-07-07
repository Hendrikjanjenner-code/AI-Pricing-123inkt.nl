"""
Competitor Discovery Engine.

Ontdekt concurrenten uit de PriceShape-feed: elke vendor-domein dat in
`fact_competitor_price_daily` voorkomt is een echte concurrent die op minstens
één van onze SKU's een prijs voert. Per domein worden berekend:

- op hoeveel eigen SKU's de concurrent een aanbod heeft (SKU-overlap),
- in welke categorieën die overlap zit (categoriedekking),
- de gemiddelde prijsindex (onze prijs / concurrentprijs).

Er wordt GEEN vaste kennisbank meer gebruikt; alle kandidaten komen uit de
echte feed-data. Nieuwe domeinen worden als PROPOSED in
`competitor_discovery_queue` gezet zodat een analist ze kan goedkeuren.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
import models


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def run_discovery(
    db: Session,
    categories: Optional[list[str]] = None,
    min_confidence: float = 0.60,
) -> dict:
    """
    Voer een discovery-run uit op basis van de PriceShape-feed en sla nieuwe
    concurrenten op in competitor_discovery_queue.

    Returns:
        dict met run_id, candidates_found, candidates_new
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run = models.CompetitorDiscoveryRun(
        run_id=run_id,
        started_at=datetime.utcnow(),
        status="running",
        categories_searched=categories or [],
        parameters={"min_confidence": min_confidence, "source": "priceshape_feed"},
    )
    db.add(run)
    db.flush()

    # Gebruik de meest recente feed-datum als momentopname van het landschap.
    latest = db.query(func.max(models.FactCompetitorPriceDaily.date)).scalar()

    candidates: list[dict] = []
    if latest is not None:
        # Eigen catalogus: categorie + huidige prijs per SKU.
        products = {
            p.sku_id: (p.category, float(p.current_price) if p.current_price else None)
            for p in db.query(
                models.DimProduct.sku_id,
                models.DimProduct.category,
                models.DimProduct.current_price,
            ).all()
        }
        total_skus = max(len(products), 1)

        rows = db.query(
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.price,
        ).filter(models.FactCompetitorPriceDaily.date == latest).all()

        # Aggregeer per concurrent-domein.
        agg: dict[str, dict] = {}
        for naam, sku_id, price in rows:
            if not naam or price is None:
                continue
            cat, own_price = products.get(sku_id, (None, None))
            entry = agg.setdefault(naam, {"skus": set(), "cats": {}, "indices": []})
            entry["skus"].add(sku_id)
            if cat:
                entry["cats"][cat] = entry["cats"].get(cat, 0) + 1
            if own_price and float(price) > 0:
                entry["indices"].append(own_price / float(price))

        for naam, entry in agg.items():
            cats = sorted(entry["cats"], key=lambda c: entry["cats"][c], reverse=True)
            if categories and not any(c in cats for c in categories):
                continue
            sku_count = len(entry["skus"])
            coverage_ratio = sku_count / total_skus
            # Volledige zekerheid bij ≥50% catalogusdekking; lineair daaronder.
            confidence = round(_clamp(coverage_ratio / 0.5), 2)
            avg_index = (
                round(sum(entry["indices"]) / len(entry["indices"]), 3)
                if entry["indices"] else None
            )
            positie = ""
            if avg_index is not None:
                positie = (
                    f" gem. prijsindex {avg_index} "
                    f"({'wij goedkoper' if avg_index < 1 else 'wij duurder'})"
                )
            reason = (
                f"Uit PriceShape-feed: concurreert op {sku_count} SKU's "
                f"in {len(cats)} categorie(ën).{positie}"
            )
            candidates.append({
                "domain": naam,
                "competitor_name": naam,
                "categories": cats,
                "discovery_method": "FEED",
                "confidence": confidence,
                "discovery_reason": reason,
            })

    candidates = [c for c in candidates if c["confidence"] >= min_confidence]

    # Dedupliceer tegen reeds bekende domeinen in de queue.
    bestaande = {
        q.domain
        for q in db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain.in_([c["domain"] for c in candidates])
        ).all()
    } if candidates else set()

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
