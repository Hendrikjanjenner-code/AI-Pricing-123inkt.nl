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
    min_confidence: Optional[float] = None,
    shop_id: Optional[int] = None,
) -> dict:
    """
    Voer een discovery-run uit op basis van de PriceShape-feed en sla nieuwe
    concurrenten op in competitor_discovery_queue.

    min_confidence: expliciete drempel; None = per-shop instelling
    (competition_setting) van de opgegeven of default shop.

    Returns:
        dict met run_id, candidates_found, candidates_new
    """
    from services import competition_settings as cs

    sid = shop_id if shop_id is not None else cs.default_shop_id(db)
    settings = cs.get_settings(db, sid) if sid is not None else dict(cs.DEFAULTS)
    if min_confidence is None:
        min_confidence = float(settings["min_discovery_confidence"])
    auto_approve_threshold = float(settings["auto_approve_threshold"])

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run = models.CompetitorDiscoveryRun(
        run_id=run_id,
        started_at=datetime.utcnow(),
        status="running",
        categories_searched=categories or [],
        shop_id=sid,
        parameters={"min_confidence": min_confidence, "source": "priceshape_feed",
                    "shop_id": sid},
    )
    db.add(run)
    db.flush()

    # Gebruik de meest recente feed-datum als momentopname van het landschap
    # (shop-scoped zodat winkels elkaar niet beïnvloeden).
    latest = (
        db.query(func.max(models.FactCompetitorPriceDaily.date))
        .filter(models.FactCompetitorPriceDaily.shop_id == sid)
        .scalar()
    )

    candidates: list[dict] = []
    if latest is not None:
        # Eigen catalogus van déze shop: categorie + huidige prijs per SKU.
        products = {
            p.sku_id: (p.category, float(p.current_price) if p.current_price else None)
            for p in db.query(
                models.DimProduct.sku_id,
                models.DimProduct.category,
                models.DimProduct.current_price,
            ).filter(models.DimProduct.shop_id == sid).all()
        }
        total_skus = max(len(products), 1)

        rows = db.query(
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.price,
        ).filter(models.FactCompetitorPriceDaily.date == latest,
                 models.FactCompetitorPriceDaily.shop_id == sid).all()

        # Aggregeer per concurrent-domein (alleen SKU's van deze shop).
        # Domeinnormalisatie: historische factrijen kunnen nog ruwe varianten
        # bevatten; aggregeer altijd op het canonieke domein zodat één
        # concurrent nooit als meerdere kandidaten verschijnt.
        from services.domain_normalize import normalize_domain
        agg: dict[str, dict] = {}
        for naam, sku_id, price in rows:
            naam = normalize_domain(naam)
            if not naam or price is None:
                continue
            if sku_id not in products:
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

    # Dedupliceer tegen reeds bekende domeinen in de queue van déze shop
    # (legacy-rijen zonder shop_id tellen ook mee om dubbelingen te voorkomen).
    # Vergelijk op het CANONIEKE domein: ook een oude queue-rij met een ruwe
    # variant (www./https-schrijfwijze) telt als bestaand.
    from services.domain_normalize import normalize_domain as _nd
    bestaande = {
        _nd(q.domain)
        for q in db.query(models.CompetitorDiscoveryQueue).filter(
            (models.CompetitorDiscoveryQueue.shop_id == sid)
            | (models.CompetitorDiscoveryQueue.shop_id.is_(None)),
        ).all()
    } if candidates else set()

    nieuw = 0
    for candidate in candidates:
        if candidate["domain"] not in bestaande:
            # Boven de auto-goedkeuringsdrempel: direct goedkeuren zonder review.
            auto_approved = candidate["confidence"] >= auto_approve_threshold
            item = models.CompetitorDiscoveryQueue(
                domain=candidate["domain"],
                competitor_name=candidate["competitor_name"],
                discovery_reason=candidate["discovery_reason"],
                discovery_method=candidate["discovery_method"],
                categories=candidate["categories"],
                confidence=candidate["confidence"],
                status="APPROVED" if auto_approved else "PROPOSED",
                run_id=run_id,
                shop_id=sid,
            )
            if auto_approved:
                item.approved_by = "auto-approve"
                item.approved_at = datetime.utcnow()
                # Master synchroon houden (taak #288): een automatische
                # goedkeuring is een echte beslissing en moet in dezelfde
                # transactie op de canonieke master landen.
                from services.competitor_master import sync_master_approval
                sync_master_approval(db, item.domain, "APPROVED",
                                     "auto-approve")
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
