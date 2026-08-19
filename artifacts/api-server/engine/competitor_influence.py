"""
CIS — Competitor Influence Score.

Bepaalt hoeveel invloed een specifieke concurrent heeft op onze
optimale prijsbeslissing voor een SKU.

Formule:
  CIS = competitor_relevance_score
      * competitor_sustainability_score   (CSS)
      * competitor_stock_reliability_score (CSRS)
      * product_comparability_score
      * price_sensitivity_score

Classificatie:
  > 0.80  = Primaire concurrent
  0.60–0.80 = Sterke concurrent
  0.40–0.60 = Secundaire concurrent
  0.20–0.40 = Zwakke concurrent
  < 0.20  = Negeren

Vier concurrentielagen:
  direct      — exacte SKU-overlap
  functioneel — ander product, zelfde behoefte
  categorie   — alternatief binnen zelfde categorie
  intern      — eigen producten (huismerk vs A-merk)
"""
from __future__ import annotations
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Optional

import models

CIS_CLASSES = [
    (0.80, 1.01, "Primaire concurrent"),
    (0.60, 0.80, "Sterke concurrent"),
    (0.40, 0.60, "Secundaire concurrent"),
    (0.20, 0.40, "Zwakke concurrent"),
    (0.00, 0.20, "Negeren"),
]

COMPETITION_LAYERS = ["direct", "functioneel", "categorie", "intern"]


def calculate_cis(
    competitor_relevance_score: float,
    css_score: float,
    csrs_score: float,
    product_comparability_score: float,
    price_sensitivity_score: float,
) -> float:
    """
    Bereken de CIS score (0.0 – 1.0).
    Multiplicatief model: één lage factor zwakt het totaal sterk af.
    """
    raw = (
        competitor_relevance_score
        * css_score
        * csrs_score
        * product_comparability_score
        * price_sensitivity_score
    )
    return round(min(raw, 1.0), 4)


def get_cis_class(cis: float) -> str:
    """Map CIS score naar classificatielabel."""
    for low, high, cls in CIS_CLASSES:
        if low <= cis < high:
            return cls
    return "Negeren"


def get_cis_status(cis: float, csrs: float, css: float) -> tuple[str, str]:
    """
    Geeft (status, pricing_action) op basis van CIS, CSRS en CSS.

    Returns:
        status: 'Actief' | 'Monitoren' | 'Negeren'
        pricing_action: beschrijving van actie
    """
    if cis >= 0.60 and csrs >= 0.60 and css >= 0.45:
        return "Actief", "INCLUDE_NORMAL_WEIGHT"
    elif cis >= 0.40 or (csrs >= 0.25 and css >= 0.45):
        return "Monitoren", "WATCH_ONLY_LOW_STOCK_RELIABILITY"
    else:
        return "Negeren", "IGNORE_LOW_INFLUENCE"


def calculate_competitor_weight(
    competitor_relevance_score: float,
    competitor_price_reliability_score: float,
    css_score: float,
    csrs_score: float,
) -> float:
    """
    Gewicht voor de gewogen mediane referentieprijs.
    weight = relevance * price_reliability * css * csrs
    """
    return round(
        competitor_relevance_score
        * competitor_price_reliability_score
        * css_score
        * csrs_score,
        4,
    )


def get_layer_label(layer: str) -> str:
    """Nederlandse label voor concurrentielaag."""
    return {
        "direct": "Directe concurrentie",
        "functioneel": "Functionele concurrentie",
        "categorie": "Categorieconcurrentie",
        "intern": "Interne concurrentie",
    }.get(layer, layer)


# ── Profiel-baseline (geen prijshistorie) ───────────────────────────────────

_RELEVANCE_LABEL_SCORE = {"HIGH": 0.9, "MONITOR": 0.6, "LOW": 0.3}


def profile_baseline_influence(profile) -> float:
    """
    Baseline-influence (0..1) voor een concurrent met een profiel maar zónder
    prijshistorie. Gebaseerd op profiel alleen:
      - functional_overlap_score (0..1)
      - relevance_label (HIGH/MONITOR/LOW)
      - in_stock_rate (0..1 of 0..100)

    Zo krijgen pas ontdekte concurrenten (of concurrenten waarvan de feed nog
    niet draait) nooit stilletjes een Influence van 0 in de rankings.
    """
    overlap = float(profile.functional_overlap_score or 0.0)
    if overlap > 1.0:
        overlap = min(1.0, overlap / 100.0)

    label = (profile.relevance_label or "").upper()
    label_score = _RELEVANCE_LABEL_SCORE.get(label, 0.5)

    in_stock = profile.in_stock_rate
    if in_stock is None:
        in_stock = 0.7
    else:
        in_stock = float(in_stock)
        if in_stock > 1.0:
            in_stock = min(1.0, in_stock / 100.0)

    baseline = 0.5 * overlap + 0.3 * label_score + 0.2 * in_stock
    return round(min(1.0, max(0.0, baseline)), 4)


# ── DB-schrijfende engine ────────────────────────────────────────────────────

_WINDOW_DAYS = 30   # aantal dagen prijshistorie om op te baseren


def run_cis_engine(db, ref_date: date | None = None,
                   sku_ids: Optional[list[str]] = None) -> int:
    """
    Bereken CIS-scores per (sku_id, competitor_name) en schrijf ze naar
    competitor_influence_scores.  Retourneert het aantal geschreven rijen.

    sku_ids (optioneel): beperk de berekening tot deze SKU's zodat tests
    snel blijven ook als de DB duizenden producten bevat.

    Databronnen:
    - fact_competitor_price_daily  → beschikbaarheid + prijsvolatiliteit (CSRS/CSS)
    - sku_competition_score        → per-SKU sub-scores (PCIS-afgeleid)
    - competitor_profile           → leverancierseigenschappen (CSRS/CSS)
    - dim_product                  → eigen huidige prijs (prijsafwijking)
    """
    from sqlalchemy.orm import Session  # noqa: F401 – type-hint only
    from services import import_settings as imps

    # Configureerbare levertijd-drempel (import-instellingen). Zelfde
    # referentiepunt als de referentieprijs-uitsluiting: op/boven de drempel
    # scoort leversnelheid 0. Drempel None (geen limiet) → legacy 14d-schaal.
    _settings = imps.get_settings(db)
    _mdd = _settings.get("max_delivery_days")
    delivery_scale = float(_mdd) if _mdd else 14.0

    today = ref_date or date.today()
    since = today - timedelta(days=_WINDOW_DAYS)

    # ── 1. Concurrentprijshistorie per (sku, concurrent) ──────────────────
    price_q = (
        db.query(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date,
            models.FactCompetitorPriceDaily.price,
        )
        .filter(
            models.FactCompetitorPriceDaily.date >= since,
            models.FactCompetitorPriceDaily.date <= today,
            models.FactCompetitorPriceDaily.price.isnot(None),
        )
    )
    if sku_ids is not None:
        price_q = price_q.filter(models.FactCompetitorPriceDaily.sku_id.in_(sku_ids))
    price_rows = price_q.all()

    if not price_rows:
        return 0

    # Groepeer: {(sku_id, competitor_name): [(date, price), ...]}
    pair_prices: dict[tuple[str, str], list[tuple]] = {}
    for sku, comp, d, p in price_rows:
        pair_prices.setdefault((sku, comp), []).append((d, float(p)))

    # ── 2. Hulpdata ───────────────────────────────────────────────────────
    # Eigen huidige prijs per SKU
    own_prices: dict[str, float] = {
        p.sku_id: float(p.current_price)
        for p in db.query(models.DimProduct).filter(
            models.DimProduct.current_price.isnot(None)
        ).all()
    }

    # Meest recente PCIS-sub-scores per SKU
    pcis_by_sku: dict[str, models.SkuCompetitionScore] = {}
    for row in (
        db.query(models.SkuCompetitionScore)
        .order_by(
            models.SkuCompetitionScore.sku_id,
            models.SkuCompetitionScore.run_date.desc(),
        )
        .all()
    ):
        if row.sku_id not in pcis_by_sku:
            pcis_by_sku[row.sku_id] = row

    # Concurrentprofielen — scope tot de shops die de geselecteerde SKU's bezitten
    # zodat een scoped run nooit profielen van andere shops gebruikt (§shop-isolatie)
    profiles_q = db.query(models.CompetitorProfile)
    if sku_ids is not None:
        scoped_shop_ids = list({
            r[0] for r in
            db.query(models.DimProduct.shop_id)
            .filter(models.DimProduct.sku_id.in_(sku_ids))
            .distinct().all()
            if r[0] is not None
        })
        if scoped_shop_ids:
            profiles_q = profiles_q.filter(
                models.CompetitorProfile.shop_id.in_(scoped_shop_ids))
    profiles: dict[str, models.CompetitorProfile] = {
        p.competitor_name: p
        for p in profiles_q.all()
    }

    # ── 3. Verwijder vandaag's bestaande rijen (herrun = delete-then-insert)
    del_cis_q = db.query(models.CompetitorInfluenceScore).filter(
        models.CompetitorInfluenceScore.run_date == today
    )
    if sku_ids is not None:
        del_cis_q = del_cis_q.filter(
            models.CompetitorInfluenceScore.sku_id.in_(sku_ids))
    del_cis_q.delete(synchronize_session=False)

    # ── 4. Bereken per paar en schrijf ────────────────────────────────────
    written = 0
    for (sku_id, competitor_name), entries in pair_prices.items():
        prices = [p for _, p in entries]
        days_with_data = len({d for d, _ in entries})
        avg_price = mean(prices)
        own_price = own_prices.get(sku_id)
        pcis = pcis_by_sku.get(sku_id)
        profile = profiles.get(competitor_name)

        # ── PCIS-gebaseerde sub-scores ────────────────────────────────────
        competitor_relevance = float(pcis.competitor_relevance_score or 0.5) if pcis else 0.5
        product_comparability = float(pcis.product_comparability_score or 0.5) if pcis else 0.5
        price_sensitivity = float(pcis.price_sensitivity_score or 0.5) if pcis else 0.5

        # ── CSRS sub-scores (beschikbaarheid & betrouwbaarheid) ───────────
        availability_rate = round(min(1.0, days_with_data / _WINDOW_DAYS), 4)
        # Leversnelheid: normaliseer avg_delivery_days 0→1 op de configureerbare
        # levertijd-drempel (max_delivery_days); onbekende levertijd (None)
        # behoudt de bestaande default van 3 dagen.
        avg_days = float(profile.avg_delivery_days or 3) if profile else 3.0
        delivery_speed_score = round(max(0.0, 1.0 - avg_days / delivery_scale), 4)
        stock_stability_score = round(min(1.0, availability_rate * 1.1), 4)
        # in_stock_rate uit profiel geeft listing-consistentie
        in_stock = float(profile.in_stock_rate or 0.7) if profile and profile.in_stock_rate else 0.7
        listing_consistency_score = round(float(in_stock), 4)
        csrs_score = round(mean([
            availability_rate,
            delivery_speed_score,
            stock_stability_score,
            listing_consistency_score,
        ]), 4)

        # ── CSS sub-scores (duurzaamheid prijs) ───────────────────────────
        # Prijsafwijking t.o.v. eigen prijs (dichtbij = hoge score)
        if own_price and own_price > 0:
            price_deviation_score = round(
                max(0.0, 1.0 - abs(avg_price - own_price) / own_price), 4
            )
        else:
            price_deviation_score = 0.5

        # Prijsstabiliteit: lage variatiecoëfficiënt = stabiel
        if len(prices) > 1 and avg_price > 0:
            cv = pstdev(prices) / avg_price
            price_volatility_score = round(max(0.0, 1.0 - min(cv, 1.0)), 4)
        else:
            price_volatility_score = 0.7  # één datapunt → neutraal

        # Concurrenttype: bekend profiel scoort hoger
        competitor_type_score = 0.75 if profile else 0.5
        # Leverbetrouwbaarheid: in_stock_rate als proxy
        delivery_reliability_score = listing_consistency_score
        css_score = round(mean([
            price_deviation_score,
            price_volatility_score,
            competitor_type_score,
            delivery_reliability_score,
        ]), 4)

        # ── CIS (multiplicatief) ──────────────────────────────────────────
        cis_score = calculate_cis(
            competitor_relevance_score=competitor_relevance,
            css_score=css_score,
            csrs_score=csrs_score,
            product_comparability_score=product_comparability,
            price_sensitivity_score=price_sensitivity,
        )
        cis_class = get_cis_class(cis_score)
        status, pricing_action = get_cis_status(cis_score, csrs_score, css_score)
        competitor_weight = calculate_competitor_weight(
            competitor_relevance_score=competitor_relevance,
            competitor_price_reliability_score=float(
                pcis.competitor_price_reliability_score or 0.5
            ) if pcis else 0.5,
            css_score=css_score,
            csrs_score=csrs_score,
        )

        # Prijsvergelijking met eigen prijs
        price_vs_own_pct = (
            round((avg_price / own_price - 1.0) * 100.0, 2)
            if own_price and own_price > 0 else None
        )

        db.add(models.CompetitorInfluenceScore(
            sku_id=sku_id,
            competitor_name=competitor_name,
            run_date=today,
            competition_layer="direct",
            competitor_relevance_score=round(competitor_relevance, 4),
            product_comparability_score=round(product_comparability, 4),
            price_sensitivity_score=round(price_sensitivity, 4),
            # CSRS sub-scores
            availability_rate=availability_rate,
            delivery_speed_score=delivery_speed_score,
            stock_stability_score=stock_stability_score,
            listing_consistency_score=listing_consistency_score,
            # CSS sub-scores
            price_deviation_score=price_deviation_score,
            price_volatility_score=price_volatility_score,
            competitor_type_score=round(competitor_type_score, 4),
            delivery_reliability_score=delivery_reliability_score,
            # Samengesteld
            csrs_score=csrs_score,
            css_score=css_score,
            cis_score=cis_score,
            cis_class=cis_class,
            status=status,
            pricing_action=pricing_action,
            competitor_price=round(avg_price, 4),
            price_vs_own_pct=price_vs_own_pct,
            competitor_weight=competitor_weight,
        ))
        written += 1

    db.commit()
    return written
