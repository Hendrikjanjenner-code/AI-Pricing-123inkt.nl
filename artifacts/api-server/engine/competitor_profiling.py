"""
Competitor Profiling Engine.

Bouwt automatisch een profiel per concurrent op basis van
fact_competitor_price_daily en fact_competitor_offer_daily.
Berekent: assortimentsgrootte, merken, categoriebreedte, prijssegment,
premium/budget-aandeel, prijsactiviteit, functionele overlap.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

import models


RELEVANCE_THRESHOLDS = {
    "HIGH": 0.65,
    "MONITOR": 0.35,
}


def _relevance_label(score: float) -> tuple[str, str]:
    """Retourneer (relevance_label, traffic_light) op basis van gecombineerde score."""
    if score >= RELEVANCE_THRESHOLDS["HIGH"]:
        return "HIGH", "green"
    elif score >= RELEVANCE_THRESHOLDS["MONITOR"]:
        return "MONITOR", "orange"
    else:
        return "LOW", "red"


def _resolve_shop(db: Session, shop_id: Optional[int]) -> int:
    if shop_id is not None:
        return shop_id
    from engine.signal_publisher import _default_shop_id
    return _default_shop_id(db)


def build_or_update_profile(
    db: Session,
    competitor_name: str,
    domain: Optional[str] = None,
    lookback_days: int = 30,
    shop_id: Optional[int] = None,
) -> models.CompetitorProfile:
    """
    Bouw of update het profiel voor één concurrent.
    Gebruikt bestaande prijs- en aanboddata uit de database,
    shop-scoped (default: de default shop) zodat data van test-/andere
    shops het profiel niet vervuilt.
    """
    since = date.today() - timedelta(days=lookback_days)
    sid = _resolve_shop(db, shop_id)

    # Haal alle prijs-rijen op voor deze concurrent (binnen de shop-scope)
    price_rows = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(
            models.FactCompetitorPriceDaily.competitor_name == competitor_name,
            models.FactCompetitorPriceDaily.date >= since,
            models.FactCompetitorPriceDaily.shop_id == sid,
        )
        .all()
    )

    # Afgekeurde matches uitsluiten uit alle profielstatistieken
    from engine.competition_intelligence import rejected_pairs
    rejected = rejected_pairs(db)
    price_rows = [r for r in price_rows if (r.sku_id, competitor_name) not in rejected]

    # SKU's met bekende producten
    sku_ids = list({r.sku_id for r in price_rows})
    products = {}
    if sku_ids:
        prods = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_(sku_ids)
        ).all()
        products = {p.sku_id: p for p in prods}

    # Berekeningen
    assortment_size = len(sku_ids)

    # Categorieën
    categories: dict[str, int] = {}
    brands: dict[str, int] = {}
    for sku_id in sku_ids:
        p = products.get(sku_id)
        if p:
            if p.category:
                categories[p.category] = categories.get(p.category, 0) + 1
            if p.brand:
                brands[p.brand] = brands.get(p.brand, 0) + 1

    top_brands = sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]

    # Prijssegment bepalen op basis van beschikbare data
    all_prices = [float(r.price) for r in price_rows if r.price]
    if all_prices:
        avg_price = sum(all_prices) / len(all_prices)
        if avg_price < 10:
            price_segment = "BUDGET"
            premium_share = 0.10
            budget_share = 0.60
        elif avg_price < 50:
            price_segment = "MIDDEN"
            premium_share = 0.25
            budget_share = 0.30
        else:
            price_segment = "PREMIUM"
            premium_share = 0.50
            budget_share = 0.10
    else:
        price_segment = "MIDDEN"
        premium_share = 0.25
        budget_share = 0.30
        avg_price = 0.0

    # Prijsactiviteit
    dates_seen = sorted({r.date for r in price_rows})
    price_changes = 0
    if len(dates_seen) > 1:
        for row_a, row_b in zip(price_rows[:-1], price_rows[1:]):
            if row_a.price and row_b.price and abs(float(row_b.price) - float(row_a.price)) > 0.01:
                price_changes += 1
    changes_per_week = (price_changes / max(lookback_days, 1)) * 7

    last_price_change = dates_seen[-1] if dates_seen else None

    # Functionele overlap: echt aandeel van ons assortiment dat deze
    # concurrent (via niet-afgekeurde matches) ook voert.
    own_total = db.query(models.DimProduct.sku_id).filter(
        models.DimProduct.shop_id == sid).count()
    overlap = round(len(sku_ids) / own_total, 3) if own_total else 0.0

    # Gemiddelde prijsindex: eigen prijs / concurrentprijs per gematchte SKU
    # (meest recente waarneming per SKU binnen het venster).
    latest_price: dict[str, float] = {}
    latest_date: dict[str, date] = {}
    for r in price_rows:
        if r.price is None:
            continue
        if r.sku_id not in latest_date or r.date > latest_date[r.sku_id]:
            latest_date[r.sku_id] = r.date
            latest_price[r.sku_id] = float(r.price)
    indices = []
    for sku_id, comp_price in latest_price.items():
        p = products.get(sku_id)
        if p is not None and p.current_price and comp_price > 0:
            indices.append(float(p.current_price) / comp_price)
    avg_price_index = round(sum(indices) / len(indices), 4) if indices else None

    # Beschikbaarheid en levertijd uit het dagelijkse aanbod (offers)
    competitor = (
        db.query(models.DimCompetitor)
        .filter(models.DimCompetitor.competitor_name == competitor_name)
        .first()
    )
    in_stock_rate = None
    avg_delivery_days = None
    if competitor:
        offers = (
            db.query(models.FactCompetitorOfferDaily)
            .filter(
                models.FactCompetitorOfferDaily.competitor_id == competitor.competitor_id,
                models.FactCompetitorOfferDaily.date >= since,
            )
            .all()
        )
        shop_skus = {s[0] for s in db.query(models.DimProduct.sku_id).filter(
            models.DimProduct.shop_id == sid).all()}
        offers = [o for o in offers
                  if (o.own_sku_id, competitor_name) not in rejected
                  and o.own_sku_id in shop_skus]
        if offers:
            in_stock_rate = round(
                sum(1 for o in offers if o.in_stock) / len(offers), 4)
            delivery = [float(o.delivery_days) for o in offers
                        if o.delivery_days is not None]
            avg_delivery_days = round(sum(delivery) / len(delivery), 2) if delivery else None

    # Gecombineerde relevantiescore
    coverage_score = min(1.0, assortment_size / 30) * 0.4
    breadth_score = min(1.0, len(categories) / 5) * 0.3
    activity_score = min(1.0, changes_per_week / 3) * 0.3
    combined = coverage_score + breadth_score + activity_score

    relevance_label, traffic_light = _relevance_label(combined)

    # Upsert profiel — altijd per (shop_id, competitor_name) om cross-shop
    # overschrijving te voorkomen (CompetitorProfile heeft een UNIQUE-constraint
    # op (shop_id, competitor_name)).
    profile = (
        db.query(models.CompetitorProfile)
        .filter(models.CompetitorProfile.competitor_name == competitor_name,
                models.CompetitorProfile.shop_id == sid)
        .first()
    )
    if not profile:
        profile = models.CompetitorProfile(competitor_name=competitor_name, shop_id=sid)
        db.add(profile)

    profile.domain = domain
    profile.assortment_size = assortment_size
    profile.category_breadth = len(categories)
    profile.top_brands = [b[0] for b in top_brands]
    profile.top_categories = [c[0] for c in top_categories]
    profile.price_segment = price_segment
    profile.premium_share_pct = premium_share
    profile.budget_share_pct = budget_share
    profile.avg_price_index = avg_price_index
    profile.price_change_frequency = round(changes_per_week, 2)
    profile.last_price_change_date = last_price_change
    profile.avg_delivery_days = avg_delivery_days
    profile.in_stock_rate = in_stock_rate
    profile.functional_overlap_score = round(overlap, 3)
    profile.relevance_label = relevance_label
    profile.traffic_light = traffic_light
    profile.run_date = date.today()

    db.commit()
    return profile


def build_all_profiles(db: Session, lookback_days: int = 30,
                       shop_id: Optional[int] = None) -> list[str]:
    """Bouw/update profielen voor alle bekende concurrenten in de prijsdata
    (shop-scoped; default de default shop)."""
    sid = _resolve_shop(db, shop_id)
    namen = [
        r[0]
        for r in db.query(models.FactCompetitorPriceDaily.competitor_name)
        .filter(models.FactCompetitorPriceDaily.shop_id == sid)
        .distinct().all()
    ]
    for naam in namen:
        build_or_update_profile(db, naam, lookback_days=lookback_days, shop_id=sid)
    return namen
