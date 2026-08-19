"""
Competition Intelligence Engine (taak: concurrentiebeeld compleet).

Onderdelen:
- run_coverage:         echte assortimentsdekking per concurrent (uit AI-matches,
                        REJECTED uitgesloten), per categorie + totaal, met historie.
- detect_price_events:  concurrent-prijswijzigingen persisteren + signalen boven
                        configureerbare drempel.
- detect_promo_events:  promotiedetectie (dip + herstel) per concurrent/SKU,
                        gepersisteerd als PROMO_START/PROMO_END events + signalen.
- update_availability:  dagelijkse voorraad/levertijd-aggregatie per concurrent
                        + out-of-stock-kanssignalen.
- run_elasticity:       competitieve/kruiselasticiteit uit eigen verkoop +
                        concurrentprijshistorie (log-log regressie, met
                        heuristische fallback), gepersisteerd in SkuElasticity.
- run_all:              orchestratie van alle bovenstaande stappen + profiling.

Alle drempels komen uit de actieve modelconfiguratie (model_governance,
model 'competition_intelligence') zodat rollback het gedrag echt herstelt.
Signalen gaan uitsluitend via engine.signal_publisher.publish_signal
(explanation/evidence/sources verplicht).
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Optional

from sqlalchemy.orm import Session

import models
from engine.model_governance import get_active_config
from engine.signal_publisher import publish_signal

logger = logging.getLogger("uvicorn.error")

MODEL_NAME = "competition_intelligence"
MODEL_VERSION = "competition-intel-v1.0.0"
MAX_SIGNALS_PER_TYPE = 25

DEFAULTS = {
    # Prijswijzigingssignalen: minimale |%| verandering voor een signaal
    "price_change_alert_pct": 5.0,
    # Promotiedetectie: minimale dipdiepte t.o.v. referentie (fractie)
    "promo_dip_pct": 0.05,
    # Promotiedetectie: lookback-venster in dagen
    "promo_lookback_days": 30,
    # Beschikbaarheid: lookback voor profielstatistieken (dagen)
    "availability_lookback_days": 30,
    # OOS-kans: minimaal aantal concurrenten dat uit voorraad moet zijn
    "oos_min_competitors": 1,
    # Elasticiteit: minimale gezamenlijke dagen voor regressie
    "elasticity_min_days": 14,
    # Elasticiteit: minimale R² voor regressieresultaat om geaccepteerd te worden
    "elasticity_min_r2": 0.10,
    # Elasticiteit: minimaal aantal unieke eigen prijspunten voor regressie
    "elasticity_min_unique_prices": 5,
    # Elasticiteit: lookback-venster in dagen
    "elasticity_lookback_days": 90,
    # Dekking: match-statussen die meetellen (REJECTED nooit)
    "coverage_min_confidence": 0.0,
    # Verdachte matches: |prijsverschil| boven deze drempel (%) is verdacht
    "suspicious_match_price_diff_pct": 40.0,
    # Verdachte matches: minimaal aantal verdachte matches voor een signaal
    "suspicious_match_min_count": 5,
    # Trage runs: maximale totale wandkloktijd (seconden) van een volledige
    # run_all voordat een engine_slow_run-signaal wordt gepubliceerd.
    # Shop-gescopeerde runs (tests) zijn uitgezonderd van deze drempel.
    "slow_run_threshold_seconds": 60.0,
}


def _cfg(db: Session) -> dict:
    return get_active_config(db, MODEL_NAME, DEFAULTS)


def _already_signaled(db: Session, signal_type: str, entity_id: str,
                      shop_id: Optional[int], evidence_key: str,
                      evidence_val) -> bool:
    """True als er al een actief signaal van dit type voor deze entity bestaat
    met dezelfde waarneming (voorkomt supersede-churn bij idempotente reruns)."""
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.signal_type == signal_type,
        models.IntelligenceSignal.entity_id == entity_id,
        models.IntelligenceSignal.status == "active",
    )
    if shop_id is not None:
        q = q.filter(models.IntelligenceSignal.shop_id == shop_id)
    for sig in q.all():
        ev = sig.evidence or {}
        if ev.get(evidence_key) == evidence_val:
            return True
    return False


def rejected_pairs(db: Session) -> set[tuple[str, str]]:
    """(own_sku_id, competitor_name)-paren die door een analist zijn afgekeurd.

    Afgekeurde matches worden downstream uitgesloten (dekking, profielen,
    prijsindex, elasticiteit)."""
    rows = (
        db.query(models.AiMatchResult.own_sku_id, models.AiMatchResult.competitor_name)
        .filter(models.AiMatchResult.status == "REJECTED")
        .distinct()
        .all()
    )
    return {(r[0], r[1]) for r in rows}


# ── 1. Assortimentsdekking ───────────────────────────────────────────────────

def run_coverage(db: Session, run_date: Optional[date] = None,
                 shop_id: Optional[int] = None) -> int:
    """Bereken dekking per concurrent per categorie + totaal uit AI-matches."""
    rd = run_date or date.today()
    cfg = _cfg(db)

    prod_q = db.query(
        models.DimProduct.sku_id, models.DimProduct.category, models.DimProduct.shop_id,
    )
    if shop_id is not None:
        prod_q = prod_q.filter(models.DimProduct.shop_id == shop_id)
    products = prod_q.all()
    if not products:
        return 0
    cat_by_sku = {p.sku_id: (p.category or "Onbekend") for p in products}
    shop_by_sku = {p.sku_id: (p.shop_id or 1) for p in products}
    # Per shop tellen: dekking van shop A mag niet vervuild worden door
    # producten of matches van shop B.
    own_per_shop: dict[int, int] = {}
    own_per_shop_cat: dict[tuple[int, str], int] = {}
    for p in products:
        sid = p.shop_id or 1
        c = p.category or "Onbekend"
        own_per_shop[sid] = own_per_shop.get(sid, 0) + 1
        own_per_shop_cat[(sid, c)] = own_per_shop_cat.get((sid, c), 0) + 1

    # Gebruik per-shop de meest recente match-datum zodat een shop die al langer
    # niet is ververst niet leegtrekt door de globale maximumdatum van een andere shop.
    shop_skus: dict[int, list[str]] = {}
    for p in products:
        shop_skus.setdefault(p.shop_id or 1, []).append(p.sku_id)

    matches = []
    for _sid, sku_ids in shop_skus.items():
        latest_for_shop = (
            db.query(models.AiMatchResult.run_date)
            .filter(models.AiMatchResult.own_sku_id.in_(sku_ids))
            .order_by(models.AiMatchResult.run_date.desc())
            .first()
        )
        if not latest_for_shop:
            continue
        shop_matches = (
            db.query(
                models.AiMatchResult.own_sku_id,
                models.AiMatchResult.competitor_name,
            )
            .filter(
                models.AiMatchResult.run_date == latest_for_shop[0],
                models.AiMatchResult.status != "REJECTED",
                models.AiMatchResult.confidence >= float(cfg["coverage_min_confidence"]),
                models.AiMatchResult.own_sku_id.in_(sku_ids),
            )
            .distinct()
            .all()
        )
        matches.extend(shop_matches)

    # matched sku's per (shop, concurrent) — totaal en per categorie
    per_comp_total: dict[tuple[int, str], set[str]] = {}
    per_comp_cat: dict[tuple[int, str, str], set[str]] = {}
    for sku_id, comp in matches:
        if sku_id not in cat_by_sku:
            continue
        sid = shop_by_sku[sku_id]
        per_comp_total.setdefault((sid, comp), set()).add(sku_id)
        per_comp_cat.setdefault((sid, comp, cat_by_sku[sku_id]), set()).add(sku_id)

    del_q = db.query(models.CompetitorCoverageResult).filter(
        models.CompetitorCoverageResult.run_date == rd
    )
    if shop_id is not None:
        del_q = del_q.filter(models.CompetitorCoverageResult.shop_id == shop_id)
    del_q.delete(synchronize_session=False)
    db.flush()

    n = 0
    for (sid, comp), skus in per_comp_total.items():
        own_total = own_per_shop.get(sid, 0)
        db.add(models.CompetitorCoverageResult(
            shop_id=sid, run_date=rd, competitor_name=comp, category=None,
            own_products=own_total, matched_products=len(skus),
            coverage_pct=round(len(skus) / own_total * 100, 2) if own_total else None,
        ))
        n += 1
    for (sid, comp, cat), skus in per_comp_cat.items():
        own_n = own_per_shop_cat.get((sid, cat), 0)
        db.add(models.CompetitorCoverageResult(
            shop_id=sid, run_date=rd, competitor_name=comp, category=cat,
            own_products=own_n, matched_products=len(skus),
            coverage_pct=round(len(skus) / own_n * 100, 2) if own_n else None,
        ))
        n += 1

    # Coverage-index in categoriescores actualiseren (0–100), per shop
    db.flush()
    rel_rows = db.query(models.CategoryCompetitorRelevance).all()
    for r in rel_rows:
        r_sid = getattr(r, "shop_id", None) or 1
        skus = per_comp_cat.get((r_sid, r.competitor_name, r.category))
        own_n = own_per_shop_cat.get((r_sid, r.category), 0)
        if own_n and skus is not None:
            r.coverage_index = round(len(skus) / own_n * 100, 2)

    db.commit()
    return n


# ── 2. Prijswijzigings-events ────────────────────────────────────────────────

def detect_price_events(db: Session, run_date: Optional[date] = None,
                        shop_id: Optional[int] = None) -> int:
    """Vergelijk de laatste twee waarnemingsdagen per (SKU, concurrent) en
    persisteer prijswijzigingen; signalen boven de drempel."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    threshold = float(cfg["price_change_alert_pct"])
    since = rd - timedelta(days=14)
    rejected = rejected_pairs(db)

    price_q = (
        db.query(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date,
            models.FactCompetitorPriceDaily.price,
            models.FactCompetitorPriceDaily.shop_id,
        )
        .filter(models.FactCompetitorPriceDaily.date >= since,
                models.FactCompetitorPriceDaily.date <= rd,
                models.FactCompetitorPriceDaily.price.isnot(None))
    )
    if shop_id is not None:
        price_q = price_q.filter(models.FactCompetitorPriceDaily.shop_id == shop_id)
    rows = price_q.order_by(models.FactCompetitorPriceDaily.date).all()

    # SKU-eigenaar per shop: cross-shop fact-rijen worden genegeerd
    prod_q = db.query(models.DimProduct.sku_id, models.DimProduct.shop_id)
    if shop_id is not None:
        prod_q = prod_q.filter(models.DimProduct.shop_id == shop_id)
    prod_shops: dict[str, int] = {
        p.sku_id: (p.shop_id or 1) for p in prod_q.all()
    }
    series: dict[tuple[str, str], list] = {}
    shop_of: dict[tuple[str, str], int] = {}
    for sku, comp, d, price, row_shop_id in rows:
        if (sku, comp) in rejected:
            continue
        owner_shop = prod_shops.get(sku)
        # Gooi rijen weg waarvan de feed-shop niet overeenkomt met de SKU-eigenaar
        if owner_shop and (row_shop_id or 1) != owner_shop:
            continue
        series.setdefault((sku, comp), []).append((d, float(price)))
        shop_of[(sku, comp)] = owner_shop or row_shop_id or 1

    # bestaande events van vandaag verwijderen (idempotente rerun)
    ev_del_q = db.query(models.CompetitorPriceEvent).filter(
        models.CompetitorPriceEvent.event_date == rd,
        models.CompetitorPriceEvent.event_type == "PRICE_CHANGE",
    )
    if shop_id is not None:
        ev_del_q = ev_del_q.filter(models.CompetitorPriceEvent.shop_id == shop_id)
    ev_del_q.delete(synchronize_session=False)
    db.flush()

    events = []
    for (sku, comp), pts in series.items():
        if len(pts) < 2:
            continue
        (d_prev, p_prev), (d_new, p_new) = pts[-2], pts[-1]
        if d_new != rd or p_prev <= 0:
            continue
        change_pct = round((p_new - p_prev) / p_prev * 100, 2)
        if abs(change_pct) < 0.01:
            continue
        events.append(models.CompetitorPriceEvent(
            shop_id=shop_of[(sku, comp)], event_date=rd, sku_id=sku,
            competitor_name=comp, event_type="PRICE_CHANGE",
            old_price=p_prev, new_price=p_new, change_pct=change_pct,
            direction="up" if change_pct > 0 else "down",
        ))
    db.add_all(events)
    db.flush()

    # Signalen: grootste wijzigingen boven de drempel
    products = {p.sku_id: p.product_name for p in db.query(
        models.DimProduct.sku_id, models.DimProduct.product_name).all()}
    big = sorted([e for e in events if abs(e.change_pct or 0) >= threshold],
                 key=lambda e: abs(e.change_pct), reverse=True)[:MAX_SIGNALS_PER_TYPE]
    for e in big:
        if _already_signaled(db, "competitor_price_change", e.sku_id, e.shop_id,
                             "event_date", str(e.event_date)):
            continue
        publish_signal(
            db, engine="competition", signal_type="competitor_price_change",
            entity_type="sku", entity_id=e.sku_id,
            entity_name=products.get(e.sku_id, e.sku_id),
            severity="high" if abs(e.change_pct) >= 2 * threshold else "medium",
            direction="negative" if e.change_pct < 0 else "positive",
            metric="competitor_price", current_value=float(e.new_price),
            previous_value=float(e.old_price), change_pct=e.change_pct,
            confidence=0.9,
            explanation=(
                f"{e.competitor_name} wijzigde de prijs van dit product met "
                f"{e.change_pct:+.1f}% (van €{float(e.old_price):.2f} naar "
                f"€{float(e.new_price):.2f}); dat overschrijdt de alertdrempel "
                f"van {threshold:.1f}%."),
            evidence={
                "competitor": e.competitor_name,
                "old_price": float(e.old_price), "new_price": float(e.new_price),
                "change_pct": e.change_pct, "threshold_pct": threshold,
                "event_date": str(e.event_date),
            },
            sources=["competitor_price_event", "fact_competitor_price_daily"],
            suggested_action="Beoordeel of de eigen prijspositie moet meebewegen",
            model_version=MODEL_VERSION, shop_id=e.shop_id,
        )

    db.commit()
    return len(events)


# ── 3. Promotiedetectie ──────────────────────────────────────────────────────

def detect_promo_events(db: Session, run_date: Optional[date] = None,
                        shop_id: Optional[int] = None) -> int:
    """Detecteer promo-dips (prijs zakt >= promo_dip_pct onder de mediaan en
    herstelt daarna) en persisteer PROMO_START/PROMO_END events."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    dip_pct = float(cfg["promo_dip_pct"])
    lookback = int(cfg["promo_lookback_days"])
    since = rd - timedelta(days=lookback)
    rejected = rejected_pairs(db)

    promo_price_q = (
        db.query(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date,
            models.FactCompetitorPriceDaily.price,
            models.FactCompetitorPriceDaily.shop_id,
        )
        .filter(models.FactCompetitorPriceDaily.date >= since,
                models.FactCompetitorPriceDaily.price.isnot(None))
    )
    if shop_id is not None:
        promo_price_q = promo_price_q.filter(
            models.FactCompetitorPriceDaily.shop_id == shop_id)
    rows = promo_price_q.order_by(models.FactCompetitorPriceDaily.date).all()

    # SKU-eigenaar per shop: cross-shop fact-rijen worden genegeerd
    promo_prod_q = db.query(models.DimProduct.sku_id, models.DimProduct.shop_id)
    if shop_id is not None:
        promo_prod_q = promo_prod_q.filter(models.DimProduct.shop_id == shop_id)
    prod_shops_promo: dict[str, int] = {
        p.sku_id: (p.shop_id or 1) for p in promo_prod_q.all()
    }
    series: dict[tuple[str, str], list] = {}
    shop_of: dict[tuple[str, str], int] = {}
    for sku, comp, d, price, row_shop_id in rows:
        if (sku, comp) in rejected:
            continue
        owner_shop = prod_shops_promo.get(sku)
        if owner_shop and (row_shop_id or 1) != owner_shop:
            continue
        series.setdefault((sku, comp), []).append((d, float(price)))
        shop_of[(sku, comp)] = owner_shop or row_shop_id or 1

    # herberekenbaar: promo-events in het venster vervangen
    promo_del_q = db.query(models.CompetitorPriceEvent).filter(
        models.CompetitorPriceEvent.event_date >= since,
        models.CompetitorPriceEvent.event_type.in_(["PROMO_START", "PROMO_END"]),
    )
    if shop_id is not None:
        promo_del_q = promo_del_q.filter(
            models.CompetitorPriceEvent.shop_id == shop_id)
    promo_del_q.delete(synchronize_session=False)
    db.flush()

    def _median(vals: list[float]) -> float:
        s = sorted(vals)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    events: list[models.CompetitorPriceEvent] = []
    active_promos: list[models.CompetitorPriceEvent] = []
    for (sku, comp), pts in series.items():
        if len(pts) < 5:
            continue
        prices = [p for _, p in pts]
        ref = _median(prices)
        if ref <= 0:
            continue
        in_dip = False
        dip_start: Optional[date] = None
        dip_depth = 0.0
        for d, p in pts:
            below = (ref - p) / ref
            if not in_dip and below >= dip_pct:
                in_dip, dip_start, dip_depth = True, d, below
                events.append(models.CompetitorPriceEvent(
                    shop_id=shop_of[(sku, comp)], event_date=d, sku_id=sku,
                    competitor_name=comp, event_type="PROMO_START",
                    old_price=ref, new_price=p,
                    change_pct=round(-below * 100, 2), direction="down",
                    promo_depth_pct=round(below * 100, 2),
                ))
            elif in_dip:
                dip_depth = max(dip_depth, below)
                if below < dip_pct / 2:  # hersteld
                    ev = models.CompetitorPriceEvent(
                        shop_id=shop_of[(sku, comp)], event_date=d, sku_id=sku,
                        competitor_name=comp, event_type="PROMO_END",
                        old_price=ref, new_price=p,
                        change_pct=round((p - ref) / ref * 100, 2), direction="up",
                        promo_depth_pct=round(dip_depth * 100, 2),
                        promo_duration_days=(d - dip_start).days if dip_start else None,
                    )
                    events.append(ev)
                    in_dip = False
        if in_dip and dip_start is not None:
            # nog lopende promo → signaal-kandidaat
            last_ev = next((e for e in reversed(events)
                            if e.sku_id == sku and e.competitor_name == comp
                            and e.event_type == "PROMO_START"), None)
            if last_ev:
                active_promos.append(last_ev)

    db.add_all(events)
    db.flush()

    products = {p.sku_id: p.product_name for p in db.query(
        models.DimProduct.sku_id, models.DimProduct.product_name).all()}
    top = sorted(active_promos, key=lambda e: e.promo_depth_pct or 0,
                 reverse=True)[:MAX_SIGNALS_PER_TYPE]
    for e in top:
        if _already_signaled(db, "competitor_promo_detected", e.sku_id, e.shop_id,
                             "promo_start", str(e.event_date)):
            continue
        publish_signal(
            db, engine="competition", signal_type="competitor_promo_detected",
            entity_type="sku", entity_id=e.sku_id,
            entity_name=products.get(e.sku_id, e.sku_id),
            severity="medium", direction="negative",
            metric="promo_depth_pct", current_value=e.promo_depth_pct,
            confidence=0.7,
            explanation=(
                f"{e.competitor_name} voert vermoedelijk een promotie op dit product: "
                f"de prijs ligt {e.promo_depth_pct:.1f}% onder de mediaanprijs van de "
                f"afgelopen {lookback} dagen (sinds {e.event_date})."),
            evidence={
                "competitor": e.competitor_name,
                "reference_price": float(e.old_price),
                "promo_price": float(e.new_price),
                "promo_depth_pct": e.promo_depth_pct,
                "promo_start": str(e.event_date),
                "lookback_days": lookback,
            },
            sources=["competitor_price_event", "fact_competitor_price_daily"],
            suggested_action="Monitor de promotiecyclus; vermijd structurele prijsverlaging",
            model_version=MODEL_VERSION, shop_id=e.shop_id,
        )

    db.commit()
    return len(events)


# ── 4. Beschikbaarheid / voorraad ────────────────────────────────────────────

def update_availability(db: Session, run_date: Optional[date] = None,
                        shop_id: Optional[int] = None) -> int:
    """Aggregateer fact_competitor_offer_daily naar dagelijkse
    beschikbaarheidsstatistiek per concurrent + OOS-kanssignalen."""
    rd = run_date or date.today()
    cfg = _cfg(db)

    comp_names = {c.competitor_id: c.competitor_name
                  for c in db.query(models.DimCompetitor).all()}

    prod_q = db.query(models.DimProduct.sku_id, models.DimProduct.shop_id)
    if shop_id is not None:
        prod_q = prod_q.filter(models.DimProduct.shop_id == shop_id)
    shop_by_sku = {p.sku_id: (p.shop_id or 1) for p in prod_q.all()}

    # Filter aanbiedingen tot de relevante SKU's (scope-safe: OOS-scan en
    # aggregate gebruiken dezelfde set zodat geen cross-shop signalen lekken)
    offers_q = (
        db.query(models.FactCompetitorOfferDaily)
        .filter(models.FactCompetitorOfferDaily.date == rd)
    )
    if shop_id is not None and shop_by_sku:
        offers_q = offers_q.filter(
            models.FactCompetitorOfferDaily.own_sku_id.in_(list(shop_by_sku)))
    offers = offers_q.all()

    per_comp: dict[tuple[int, str], list] = {}
    for o in offers:
        if o.own_sku_id not in shop_by_sku:
            continue  # SKU hoort bij een andere shop; sla over
        name = comp_names.get(o.competitor_id, f"competitor_{o.competitor_id}")
        sid = shop_by_sku[o.own_sku_id]
        per_comp.setdefault((sid, name), []).append(o)

    av_del_q = db.query(models.CompetitorAvailabilityDaily).filter(
        models.CompetitorAvailabilityDaily.date == rd
    )
    if shop_id is not None:
        av_del_q = av_del_q.filter(
            models.CompetitorAvailabilityDaily.shop_id == shop_id)
    av_del_q.delete(synchronize_session=False)
    db.flush()

    for (sid, name), rows in per_comp.items():
        total = len(rows)
        in_stock = sum(1 for r in rows if r.in_stock)
        delivery = [float(r.delivery_days) for r in rows if r.delivery_days is not None]
        db.add(models.CompetitorAvailabilityDaily(
            shop_id=sid, date=rd, competitor_name=name, offers_total=total,
            offers_in_stock=in_stock,
            in_stock_rate=round(in_stock / total, 4) if total else None,
            avg_delivery_days=round(mean(delivery), 2) if delivery else None,
        ))
    db.flush()

    # OOS-kans: concurrenten uit voorraad terwijl wij voorraad hebben
    oos_by_sku: dict[str, list[str]] = {}
    seen_by_sku: dict[str, int] = {}
    for o in offers:
        seen_by_sku[o.own_sku_id] = seen_by_sku.get(o.own_sku_id, 0) + 1
        if not o.in_stock:
            oos_by_sku.setdefault(o.own_sku_id, []).append(
                comp_names.get(o.competitor_id, f"competitor_{o.competitor_id}"))

    min_oos = int(cfg["oos_min_competitors"])
    candidates = [(sku, comps) for sku, comps in oos_by_sku.items()
                  if len(comps) >= min_oos and len(comps) == seen_by_sku.get(sku, 0)]
    products = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_([s for s, _ in candidates])).all()}
    n_sig = 0
    for sku, comps in sorted(candidates, key=lambda x: len(x[1]), reverse=True):
        prod = products.get(sku)
        if not prod or not (prod.stock_quantity or 0) > 0:
            continue
        if n_sig >= MAX_SIGNALS_PER_TYPE:
            break
        prod_shop = prod.shop_id or 1
        if _already_signaled(db, "competitor_oos_opportunity", sku, prod_shop,
                             "date", str(rd)):
            continue
        publish_signal(
            db, engine="competition", signal_type="competitor_oos_opportunity",
            entity_type="sku", entity_id=sku, entity_name=prod.product_name,
            severity="medium", direction="positive",
            metric="competitors_out_of_stock", current_value=float(len(comps)),
            confidence=0.75,
            explanation=(
                f"Alle {len(comps)} gevolgde concurrent(en) voor dit product zijn "
                f"vandaag uit voorraad ({', '.join(comps[:5])}), terwijl wij "
                f"{prod.stock_quantity} stuks op voorraad hebben. Tijdelijke "
                f"prijs-/zichtbaarheidskans."),
            evidence={
                "competitors_oos": comps, "own_stock": prod.stock_quantity,
                "date": str(rd),
            },
            sources=["fact_competitor_offer_daily", "dim_product"],
            suggested_action="Overweeg tijdelijke prijsverhoging of extra zichtbaarheid",
            model_version=MODEL_VERSION, shop_id=prod_shop,
        )
        n_sig += 1

    db.commit()
    return len(per_comp)


# ── 5. Elasticiteit ──────────────────────────────────────────────────────────

def _ols_two_vars(y: list[float], x1: list[float], x2: list[float]):
    """OLS met intercept: y = a + b*x1 + c*x2.
    Retourneert (b, c, r2) of None bij een singulair stelsel.
    r2 = R² van de fit (0..1); negatieve waarden worden op 0.0 geclampt."""
    n = len(y)
    if n < 3:
        return None
    X = [[1.0, x1[i], x2[i]] for i in range(n)]
    XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(3)] for i in range(3)]
    Xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(3)]
    # Gauss-eliminatie
    M = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(3):
            if r != col:
                f = M[r][col] / M[col][col]
                for cc in range(4):
                    M[r][cc] -= f * M[col][cc]
    coefs = [M[i][3] / M[i][i] for i in range(3)]
    a, b, c = coefs[0], coefs[1], coefs[2]
    # R² = 1 − SS_res / SS_tot
    y_mean = sum(y) / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    if ss_tot < 1e-14:
        r2 = 0.0
    else:
        ss_res = sum((y[i] - (a + b * x1[i] + c * x2[i])) ** 2 for i in range(n))
        r2 = max(0.0, 1.0 - ss_res / ss_tot)
    return b, c, r2


def run_elasticity(db: Session, run_date: Optional[date] = None,
                   shop_id: Optional[int] = None) -> int:
    """Schat eigen + competitieve elasticiteit per SKU uit verkoop- en
    concurrentprijshistorie; heuristische fallback bij te weinig data."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    lookback = int(cfg["elasticity_lookback_days"])
    min_days = int(cfg["elasticity_min_days"])
    since = rd - timedelta(days=lookback)
    rejected = rejected_pairs(db)

    from engine.elasticity_engine import calculate_elasticity

    # Shop van elk product: factrijen tellen alleen mee als hun shop_id
    # overeenkomt met de shop van het product (datascheiding per shop).
    prod_q = db.query(models.DimProduct.sku_id, models.DimProduct.shop_id)
    if shop_id is not None:
        prod_q = prod_q.filter(models.DimProduct.shop_id == shop_id)
    prod_shop = {p.sku_id: p.shop_id for p in prod_q.all()}

    # Scope fact queries to specific SKUs when a shop filter is active
    scoped_skus = list(prod_shop.keys()) if shop_id is not None else None

    sales = {}
    sales_q = db.query(models.FactSalesDaily.sku_id, models.FactSalesDaily.date,
                       models.FactSalesDaily.units_sold,
                       models.FactSalesDaily.shop_id).filter(
            models.FactSalesDaily.date >= since)
    if scoped_skus is not None:
        sales_q = sales_q.filter(models.FactSalesDaily.sku_id.in_(scoped_skus))
    for r in sales_q.all():
        if r.units_sold and r.units_sold > 0 and r.shop_id == prod_shop.get(r.sku_id):
            sales.setdefault(r.sku_id, {})[r.date] = float(r.units_sold)

    own_prices = {}
    op_q = db.query(models.FactPriceDaily.sku_id, models.FactPriceDaily.date,
                    models.FactPriceDaily.price,
                    models.FactPriceDaily.shop_id).filter(
            models.FactPriceDaily.date >= since)
    if scoped_skus is not None:
        op_q = op_q.filter(models.FactPriceDaily.sku_id.in_(scoped_skus))
    for r in op_q.all():
        if r.price and float(r.price) > 0 and r.shop_id == prod_shop.get(r.sku_id):
            own_prices.setdefault(r.sku_id, {})[r.date] = float(r.price)

    comp_prices: dict[str, dict[date, list[float]]] = {}
    cp_q = db.query(models.FactCompetitorPriceDaily.sku_id,
                    models.FactCompetitorPriceDaily.competitor_name,
                    models.FactCompetitorPriceDaily.date,
                    models.FactCompetitorPriceDaily.price,
                    models.FactCompetitorPriceDaily.shop_id).filter(
            models.FactCompetitorPriceDaily.date >= since)
    if scoped_skus is not None:
        cp_q = cp_q.filter(models.FactCompetitorPriceDaily.sku_id.in_(scoped_skus))
    for r in cp_q.all():
        if r.price is None or float(r.price) <= 0:
            continue
        if (r.sku_id, r.competitor_name) in rejected:
            continue
        if r.shop_id != prod_shop.get(r.sku_id):
            continue
        comp_prices.setdefault(r.sku_id, {}).setdefault(r.date, []).append(float(r.price))

    # Context voor heuristische fallback
    scores_q = db.query(models.SkuCompetitionScore)
    if scoped_skus is not None:
        scores_q = scores_q.filter(models.SkuCompetitionScore.sku_id.in_(scoped_skus))
    scores = {s.sku_id: s for s in scores_q.all()}

    products_q = db.query(models.DimProduct)
    if shop_id is not None:
        products_q = products_q.filter(models.DimProduct.shop_id == shop_id)
    products = {p.sku_id: p for p in products_q.all()}

    elast_del_q = db.query(models.SkuElasticity).filter(
        models.SkuElasticity.run_date == rd)
    if scoped_skus is not None:
        elast_del_q = elast_del_q.filter(
            models.SkuElasticity.sku_id.in_(scoped_skus))
    elast_del_q.delete(synchronize_session=False)
    db.flush()

    n = 0
    for sku_id, prod in products.items():
        s_days = sales.get(sku_id, {})
        p_days = own_prices.get(sku_id, {})
        c_days = comp_prices.get(sku_id, {})
        common = sorted(set(s_days) & set(p_days) & set(c_days))

        score = scores.get(sku_id)
        pcis = float(score.pcis_score) if score and score.pcis_score else 0.5
        vol_30 = sum(v for d, v in s_days.items() if d >= rd - timedelta(days=30))
        own_series = [p_days[d] for d in sorted(p_days)]
        price_var = (max(own_series) - min(own_series)) / mean(own_series) * 100 \
            if len(own_series) > 1 and mean(own_series) > 0 else 0.0

        heur = calculate_elasticity(
            category=prod.category or "default", pcis_score=pcis, csrs_score=0.5,
            sales_volume_30d=vol_30, price_variation_pct=price_var,
            is_private_label=bool(prod.is_private_label),
            is_a_brand=bool(prod.is_a_brand),
        )

        own_e = heur["own_price_elasticity"]
        comp_e = heur["competitive_elasticity"]
        cross_e = heur["cross_elasticity"]
        conf = float(heur["elasticity_confidence_score"])
        conf_class = heur["confidence_class"]
        method = "heuristiek"
        reg_r2: Optional[float] = None

        min_r2 = float(cfg.get("elasticity_min_r2", 0.10))
        min_unique = int(cfg.get("elasticity_min_unique_prices", 5))

        if len(common) >= min_days:
            y_log = [math.log(s_days[d]) for d in common]
            x1_log = [math.log(p_days[d]) for d in common]
            x2_log = [math.log(min(c_days[d])) for d in common]
            # Tel unieke eigen prijspunten (afgerond op cent)
            unique_prices = len({round(p_days[d], 2) for d in common})
            # Regressie vereist echte variatie in beide prijsreeksen
            if (unique_prices >= min_unique
                    and pstdev(x1_log) > 1e-6
                    and pstdev(x2_log) > 1e-6):
                res = _ols_two_vars(y_log, x1_log, x2_log)
                if res is not None:
                    b, c, r2 = res
                    # Alleen accepteren bij correct teken én voldoende fit-kwaliteit
                    if -6.0 < float(b) < 0 and r2 >= min_r2:
                        own_est = max(-6.0, min(-0.1, float(b)))
                        comp_est = max(0.0, min(4.0, float(c)))
                        own_e = round(own_est, 3)
                        comp_e = round(comp_est, 3)
                        conf = min(0.95, 0.5 + len(common) / 100)
                        conf_class = "hoog_betrouwbaar" if conf >= 0.75 else "bruikbaar"
                        method = "regressie"
                        reg_r2 = round(r2, 4)
                    else:
                        logger.debug(
                            "Elasticiteit SKU %s: regressie verworpen "
                            "(b=%.3f, R²=%.3f < %.2f) → heuristiek",
                            sku_id, float(b) if res else float("nan"), r2, min_r2,
                        )

        db.add(models.SkuElasticity(
            sku_id=sku_id, run_date=rd,
            own_price_elasticity=float(own_e),
            cross_elasticity=float(cross_e),
            competitive_elasticity=float(comp_e),
            internal_substitution_elasticity=float(
                heur["internal_substitution_elasticity"]),
            elasticity_confidence_score=round(float(conf), 3),
            confidence_class=conf_class,
            method_label=method,
            regression_r2=reg_r2,
            category=prod.category,
            pcis_score_used=pcis, csrs_score_used=0.5,
            sales_volume_30d=float(vol_30),
            price_variation_30d=round(float(price_var), 2),
        ))
        n += 1
        if n % 500 == 0:
            db.flush()

    db.commit()
    logger.info("Elasticiteit: %d SKU's berekend (methode per SKU: regressie waar mogelijk).", n)
    return n

def warn_suspicious_matches(db: Session, run_date: Optional[date] = None,
                             shop_id: Optional[int] = None) -> int:
    """Publiceer een waarschuwingssignaal per shop als het aantal verdachte
    AI-matches (|price_diff_pct| > drempel bij status PENDING) boven de
    configureerbare min_count drempel uitkomt.

    Idempotent bij reruns: een tweede aanroep op dezelfde run_date maakt géén
    extra signaal aan zolang het vorige nog actief is.
    Linkt naar de AI Matching-pagina zodat analisten direct kunnen reviewen.
    """
    from sqlalchemy import func as _f

    rd = run_date or date.today()
    cfg = _cfg(db)
    price_diff_threshold = float(cfg["suspicious_match_price_diff_pct"])
    min_count = int(cfg["suspicious_match_min_count"])

    # Tel verdachte PENDING-matches per shop
    susp_q = (
        db.query(
            models.DimProduct.shop_id,
            _f.count(models.AiMatchResult.id).label("cnt"),
        )
        .join(models.AiMatchResult,
              models.AiMatchResult.own_sku_id == models.DimProduct.sku_id)
        .filter(
            models.AiMatchResult.status == "PENDING",
            models.AiMatchResult.price_diff_pct.isnot(None),
            (models.AiMatchResult.price_diff_pct > price_diff_threshold)
            | (models.AiMatchResult.price_diff_pct < -price_diff_threshold),
        )
        .group_by(models.DimProduct.shop_id)
    )
    if shop_id is not None:
        susp_q = susp_q.filter(models.DimProduct.shop_id == shop_id)
    rows = susp_q.all()

    n_signals = 0
    for shop_id, cnt in rows:
        if cnt < min_count:
            continue
        sid = shop_id or 1
        # Idempotentie: één signaal per shop per run_date
        if _already_signaled(db, "suspicious_ai_matches", "ai-matching", sid,
                             "run_date", str(rd)):
            continue
        publish_signal(
            db, engine="competition", signal_type="suspicious_ai_matches",
            entity_type="system", entity_id="ai-matching",
            entity_name="AI Matching",
            severity="high", direction="negative",
            metric="suspicious_match_count", current_value=float(cnt),
            confidence=0.95,
            explanation=(
                f"Er zijn {cnt} verdachte AI-matches met een |prijsverschil| "
                f"> {price_diff_threshold:.0f}% bij status PENDING. "
                f"Foute matches vervuilen dekking, prijsindex en elasticiteit. "
                f"Beoordeel de AI Matching-pagina en keur matches goed of af."),
            evidence={
                "suspicious_count": cnt,
                "price_diff_threshold_pct": price_diff_threshold,
                "min_count_threshold": min_count,
                "run_date": str(rd),
                "link": "/competition/ai-matching",
            },
            sources=["ai_match_result"],
            suggested_action=(
                "Open de AI Matching-pagina en keur verdachte matches goed of af"),
            model_version=MODEL_VERSION, shop_id=sid,
        )
        n_signals += 1

    db.commit()
    return n_signals


# ── Orchestratie ─────────────────────────────────────────────────────────────

def comparable_price_series(rows) -> dict[str, list]:
    """Bouw per concurrent een vergelijkbare dagreeks uit ruwe (sku, datum,
    prijs)-waarnemingen: elke SKU wordt genormaliseerd op zijn eigen eerste
    waarneming (relatieve prijs), en per datum wordt het gemiddelde van die
    relatieve prijzen genomen — precies één deterministische waarde per datum.
    Zo worden assortiments-prijsniveauverschillen niet als prijsbewegingen
    gezien. Rows: iterable met .competitor_name, .sku_id, .date, .price."""
    per_comp: dict[str, dict] = {}
    for r in rows:
        if r.price is None or float(r.price) <= 0:
            continue
        naam = r.competitor_name or "Onbekend"
        c = per_comp.setdefault(naam, {})
        c.setdefault(r.sku_id, {})[r.date] = float(r.price)
    out: dict[str, list] = {}
    for naam, skus in per_comp.items():
        rel_per_date: dict = {}
        for sku, by_date in skus.items():
            dates = sorted(by_date)
            base = by_date[dates[0]]
            if base <= 0:
                continue
            for d in dates:
                rel_per_date.setdefault(d, []).append(by_date[d] / base)
        serie = [(d, round(sum(v) / len(v), 6))
                 for d, v in sorted(rel_per_date.items())]
        if serie:
            out[naam] = serie
    return out


def run_strategies(db: Session, run_date: Optional[date] = None,
                   lookback_days: int = 30,
                   shop_id: Optional[int] = None) -> int:
    """Herken en persisteer per shop de prijsstrategie per concurrent uit de
    shop-gefilterde concurrentprijshistorie (upsert per shop/concurrent/run)."""
    from engine.competitor_strategy_engine import analyseer_alle_concurrenten
    rd = run_date or date.today()
    since = rd - timedelta(days=lookback_days)
    n = 0
    if shop_id is not None:
        shop_ids = [shop_id]
    else:
        shop_ids = [s for (s,) in db.query(models.DimProduct.shop_id).distinct().all()
                    if s is not None]
    for sid in shop_ids:
        rows = (db.query(models.FactCompetitorPriceDaily)
                .join(models.DimProduct,
                      models.DimProduct.sku_id == models.FactCompetitorPriceDaily.sku_id)
                .filter(models.FactCompetitorPriceDaily.date >= since,
                        models.FactCompetitorPriceDaily.shop_id == sid,
                        models.DimProduct.shop_id == sid,  # eigenaar-shop-validatie
                        models.FactCompetitorPriceDaily.price.isnot(None))
                .all())
        prijsdata = comparable_price_series(rows)
        if not prijsdata:
            continue
        for res in analyseer_alle_concurrenten(prijsdata):
            naam = res.get("concurrent")
            if not naam:
                continue
            prev = (db.query(models.CompetitorStrategyResult)
                    .filter(models.CompetitorStrategyResult.competitor_name == naam,
                            models.CompetitorStrategyResult.shop_id == sid)
                    .order_by(models.CompetitorStrategyResult.run_date.desc())
                    .first())
            stype = res.get("strategy_type")
            if prev and prev.run_date == rd:
                row = prev
                prev_type = row.previous_strategy_type
            else:
                row = models.CompetitorStrategyResult(
                    competitor_name=naam, run_date=rd, shop_id=sid)
                prev_type = prev.strategy_type if prev else None
                db.add(row)
            row.strategy_type = stype
            row.strategy_label_nl = res.get("label_nl")
            row.confidence = res.get("confidence")
            row.explanation_nl = res.get("reden")
            row.recommended_action_nl = res.get("aanbevolen_reactie")
            row.period_days = lookback_days
            row.data_points = res.get("datapunten")
            row.previous_strategy_type = prev_type
            row.strategy_changed = bool(prev_type and stype and prev_type != stype)
            n += 1
    db.commit()
    return n


def run_all(db: Session, run_date: Optional[date] = None,
            shop_id: Optional[int] = None) -> dict:
    """Draai alle competition-intelligence stappen; retourneer samenvatting.

    shop_id (optioneel): beperk de run tot één shop zodat tests/scheduled
    runs snel blijven ook als de DB duizenden producten bevat.
    """
    rd = run_date or date.today()
    from engine import competitor_profiling

    timings: dict[str, float] = {}
    run_start = time.monotonic()

    def _timed(step: str, fn):
        t0 = time.monotonic()
        out = fn()
        timings[step] = round(time.monotonic() - t0, 3)
        logger.info("Competition intelligence stap '%s' duurde %.3fs",
                    step, timings[step])
        return out

    def _profiles() -> int:
        if shop_id is not None:
            return len(competitor_profiling.build_all_profiles(db, shop_id=shop_id))
        return sum(
            len(competitor_profiling.build_all_profiles(db, shop_id=sid))
            for (sid,) in db.query(models.DimProduct.shop_id).distinct().all()
            if sid is not None
        )

    profiles_count = _timed("profiles", _profiles)

    result = {
        "run_date": str(rd),
        "coverage_rows": _timed("coverage", lambda: run_coverage(db, rd, shop_id=shop_id)),
        "price_events": _timed("price_events", lambda: detect_price_events(db, rd, shop_id=shop_id)),
        "promo_events": _timed("promo_events", lambda: detect_promo_events(db, rd, shop_id=shop_id)),
        "availability_competitors": _timed("availability", lambda: update_availability(db, rd, shop_id=shop_id)),
        "elasticity_skus": _timed("elasticity", lambda: run_elasticity(db, rd, shop_id=shop_id)),
        "strategy_results": _timed("strategies", lambda: run_strategies(db, rd, shop_id=shop_id)),
        "profiles": profiles_count,
        "suspicious_match_signals": _timed("suspicious_matches", lambda: warn_suspicious_matches(db, rd, shop_id=shop_id)),
        "model_version": MODEL_VERSION,
    }

    total_seconds = round(time.monotonic() - run_start, 3)
    result["timings_seconds"] = timings
    result["total_seconds"] = total_seconds
    logger.info("Competition intelligence run (%.3fs totaal): %s",
                total_seconds, result)

    # Trage-run-bewaking: alleen voor volledige (niet shop-gescopeerde) runs,
    # zodat gescopeerde test-runs nooit signalen genereren of vertragen.
    if shop_id is None:
        threshold = float(_cfg(db).get("slow_run_threshold_seconds",
                                       DEFAULTS["slow_run_threshold_seconds"]))
        if threshold > 0 and total_seconds > threshold:
            slowest = max(timings, key=timings.get) if timings else None
            publish_signal(
                db, engine="competition", signal_type="engine_slow_run",
                entity_type="shop", entity_id="all",
                entity_name="Competition Intelligence Engine",
                severity="medium", direction="negative",
                metric="engine_run_seconds",
                current_value=total_seconds, expected_value=threshold,
                confidence=1.0,
                explanation=(
                    f"De volledige competition-intelligence-run van {rd} duurde "
                    f"{total_seconds:.1f}s; dat overschrijdt de drempel van "
                    f"{threshold:.0f}s. Langzaamste stap: "
                    f"{slowest or 'onbekend'} "
                    f"({timings.get(slowest, 0):.1f}s)."
                    if slowest else
                    f"De volledige competition-intelligence-run van {rd} duurde "
                    f"{total_seconds:.1f}s; dat overschrijdt de drempel van "
                    f"{threshold:.0f}s."),
                evidence={
                    "run_date": str(rd),
                    "total_seconds": total_seconds,
                    "threshold_seconds": threshold,
                    "timings_seconds": timings,
                    "slowest_step": slowest,
                },
                sources=["engine_run_profiling"],
                suggested_action=(
                    "Onderzoek de langzaamste stap; controleer datavolume en "
                    "query-plannen voordat de vertraging gebruikers raakt"),
                model_version=MODEL_VERSION,
            )
            db.commit()
            result["slow_run_signal"] = True
    return result
