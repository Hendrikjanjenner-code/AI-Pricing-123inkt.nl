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
    # Elasticiteit: lookback-venster in dagen
    "elasticity_lookback_days": 90,
    # Dekking: match-statussen die meetellen (REJECTED nooit)
    "coverage_min_confidence": 0.0,
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

def run_coverage(db: Session, run_date: Optional[date] = None) -> int:
    """Bereken dekking per concurrent per categorie + totaal uit AI-matches."""
    rd = run_date or date.today()
    cfg = _cfg(db)

    products = db.query(
        models.DimProduct.sku_id, models.DimProduct.category, models.DimProduct.shop_id,
    ).all()
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

    latest_match_date = db.query(models.AiMatchResult.run_date).order_by(
        models.AiMatchResult.run_date.desc()).first()
    matches = []
    if latest_match_date:
        matches = (
            db.query(
                models.AiMatchResult.own_sku_id,
                models.AiMatchResult.competitor_name,
            )
            .filter(
                models.AiMatchResult.run_date == latest_match_date[0],
                models.AiMatchResult.status != "REJECTED",
                models.AiMatchResult.confidence >= float(cfg["coverage_min_confidence"]),
            )
            .distinct()
            .all()
        )

    # matched sku's per (shop, concurrent) — totaal en per categorie
    per_comp_total: dict[tuple[int, str], set[str]] = {}
    per_comp_cat: dict[tuple[int, str, str], set[str]] = {}
    for sku_id, comp in matches:
        if sku_id not in cat_by_sku:
            continue
        sid = shop_by_sku[sku_id]
        per_comp_total.setdefault((sid, comp), set()).add(sku_id)
        per_comp_cat.setdefault((sid, comp, cat_by_sku[sku_id]), set()).add(sku_id)

    db.query(models.CompetitorCoverageResult).filter(
        models.CompetitorCoverageResult.run_date == rd
    ).delete(synchronize_session=False)
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

def detect_price_events(db: Session, run_date: Optional[date] = None) -> int:
    """Vergelijk de laatste twee waarnemingsdagen per (SKU, concurrent) en
    persisteer prijswijzigingen; signalen boven de drempel."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    threshold = float(cfg["price_change_alert_pct"])
    since = rd - timedelta(days=14)
    rejected = rejected_pairs(db)

    rows = (
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
        .order_by(models.FactCompetitorPriceDaily.date)
        .all()
    )

    series: dict[tuple[str, str], list] = {}
    shop_of: dict[tuple[str, str], int] = {}
    for sku, comp, d, price, shop_id in rows:
        if (sku, comp) in rejected:
            continue
        series.setdefault((sku, comp), []).append((d, float(price)))
        shop_of[(sku, comp)] = shop_id or 1

    # bestaande events van vandaag verwijderen (idempotente rerun)
    db.query(models.CompetitorPriceEvent).filter(
        models.CompetitorPriceEvent.event_date == rd,
        models.CompetitorPriceEvent.event_type == "PRICE_CHANGE",
    ).delete(synchronize_session=False)
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

def detect_promo_events(db: Session, run_date: Optional[date] = None) -> int:
    """Detecteer promo-dips (prijs zakt >= promo_dip_pct onder de mediaan en
    herstelt daarna) en persisteer PROMO_START/PROMO_END events."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    dip_pct = float(cfg["promo_dip_pct"])
    lookback = int(cfg["promo_lookback_days"])
    since = rd - timedelta(days=lookback)
    rejected = rejected_pairs(db)

    rows = (
        db.query(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date,
            models.FactCompetitorPriceDaily.price,
            models.FactCompetitorPriceDaily.shop_id,
        )
        .filter(models.FactCompetitorPriceDaily.date >= since,
                models.FactCompetitorPriceDaily.price.isnot(None))
        .order_by(models.FactCompetitorPriceDaily.date)
        .all()
    )
    series: dict[tuple[str, str], list] = {}
    shop_of: dict[tuple[str, str], int] = {}
    for sku, comp, d, price, shop_id in rows:
        if (sku, comp) in rejected:
            continue
        series.setdefault((sku, comp), []).append((d, float(price)))
        shop_of[(sku, comp)] = shop_id or 1

    # herberekenbaar: promo-events in het venster vervangen
    db.query(models.CompetitorPriceEvent).filter(
        models.CompetitorPriceEvent.event_date >= since,
        models.CompetitorPriceEvent.event_type.in_(["PROMO_START", "PROMO_END"]),
    ).delete(synchronize_session=False)
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

def update_availability(db: Session, run_date: Optional[date] = None) -> int:
    """Aggregateer fact_competitor_offer_daily naar dagelijkse
    beschikbaarheidsstatistiek per concurrent + OOS-kanssignalen."""
    rd = run_date or date.today()
    cfg = _cfg(db)

    comp_names = {c.competitor_id: c.competitor_name
                  for c in db.query(models.DimCompetitor).all()}

    offers = (
        db.query(models.FactCompetitorOfferDaily)
        .filter(models.FactCompetitorOfferDaily.date == rd)
        .all()
    )
    shop_by_sku = {p.sku_id: (p.shop_id or 1) for p in db.query(
        models.DimProduct.sku_id, models.DimProduct.shop_id).all()}

    per_comp: dict[tuple[int, str], list] = {}
    for o in offers:
        name = comp_names.get(o.competitor_id, f"competitor_{o.competitor_id}")
        sid = shop_by_sku.get(o.own_sku_id, 1)
        per_comp.setdefault((sid, name), []).append(o)

    db.query(models.CompetitorAvailabilityDaily).filter(
        models.CompetitorAvailabilityDaily.date == rd
    ).delete(synchronize_session=False)
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
    """OLS met intercept: y = a + b*x1 + c*x2. Retourneert (b, c) of None."""
    n = len(y)
    if n < 3:
        return None
    # Normal equations (3x3), pure Python
    import itertools
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
    return coefs[1], coefs[2]


def run_elasticity(db: Session, run_date: Optional[date] = None) -> int:
    """Schat eigen + competitieve elasticiteit per SKU uit verkoop- en
    concurrentprijshistorie; heuristische fallback bij te weinig data."""
    rd = run_date or date.today()
    cfg = _cfg(db)
    lookback = int(cfg["elasticity_lookback_days"])
    min_days = int(cfg["elasticity_min_days"])
    since = rd - timedelta(days=lookback)
    rejected = rejected_pairs(db)

    from engine.elasticity_engine import calculate_elasticity

    sales = {}
    for r in db.query(models.FactSalesDaily.sku_id, models.FactSalesDaily.date,
                      models.FactSalesDaily.units_sold).filter(
            models.FactSalesDaily.date >= since).all():
        if r.units_sold and r.units_sold > 0:
            sales.setdefault(r.sku_id, {})[r.date] = float(r.units_sold)

    own_prices = {}
    for r in db.query(models.FactPriceDaily.sku_id, models.FactPriceDaily.date,
                      models.FactPriceDaily.price).filter(
            models.FactPriceDaily.date >= since).all():
        if r.price and float(r.price) > 0:
            own_prices.setdefault(r.sku_id, {})[r.date] = float(r.price)

    comp_prices: dict[str, dict[date, list[float]]] = {}
    for r in db.query(models.FactCompetitorPriceDaily.sku_id,
                      models.FactCompetitorPriceDaily.competitor_name,
                      models.FactCompetitorPriceDaily.date,
                      models.FactCompetitorPriceDaily.price).filter(
            models.FactCompetitorPriceDaily.date >= since).all():
        if r.price is None or float(r.price) <= 0:
            continue
        if (r.sku_id, r.competitor_name) in rejected:
            continue
        comp_prices.setdefault(r.sku_id, {}).setdefault(r.date, []).append(float(r.price))

    # Context voor heuristische fallback
    scores = {s.sku_id: s for s in db.query(models.SkuCompetitionScore).all()}
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}

    db.query(models.SkuElasticity).filter(
        models.SkuElasticity.run_date == rd).delete(synchronize_session=False)
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

        if len(common) >= min_days:
            y = [math.log(s_days[d]) for d in common]
            x1 = [math.log(p_days[d]) for d in common]
            x2 = [math.log(min(c_days[d])) for d in common]
            # regressie vereist echte variatie in beide prijsreeksen
            if pstdev(x1) > 1e-6 and pstdev(x2) > 1e-6:
                res = _ols_two_vars(y, x1, x2)
                if res is not None:
                    b, c = res
                    # clamp naar plausibele economische ranges
                    own_est = max(-6.0, min(-0.1, float(b)))
                    comp_est = max(0.0, min(4.0, float(c)))
                    if -6.0 < float(b) < 0:  # alleen accepteren bij correct teken
                        own_e = round(own_est, 3)
                        comp_e = round(comp_est, 3)
                        conf = min(0.95, 0.5 + len(common) / 100)
                        conf_class = "hoog_betrouwbaar" if conf >= 0.75 else "bruikbaar"
                        method = "regressie"

        db.add(models.SkuElasticity(
            sku_id=sku_id, run_date=rd,
            own_price_elasticity=float(own_e),
            cross_elasticity=float(cross_e),
            competitive_elasticity=float(comp_e),
            internal_substitution_elasticity=float(
                heur["internal_substitution_elasticity"]),
            elasticity_confidence_score=round(float(conf), 3),
            confidence_class=conf_class,
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


# ── Orchestratie ─────────────────────────────────────────────────────────────

def run_all(db: Session, run_date: Optional[date] = None) -> dict:
    """Draai alle competition-intelligence stappen; retourneer samenvatting."""
    rd = run_date or date.today()
    from engine import competitor_profiling

    result = {
        "run_date": str(rd),
        "coverage_rows": run_coverage(db, rd),
        "price_events": detect_price_events(db, rd),
        "promo_events": detect_promo_events(db, rd),
        "availability_competitors": update_availability(db, rd),
        "elasticity_skus": run_elasticity(db, rd),
        "profiles": len(competitor_profiling.build_all_profiles(db)),
        "model_version": MODEL_VERSION,
    }
    logger.info("Competition intelligence run: %s", result)
    return result
