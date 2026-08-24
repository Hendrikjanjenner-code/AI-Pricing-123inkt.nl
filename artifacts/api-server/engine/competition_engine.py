"""
Competition Intelligence Engine.

Calculates the PCIS (Pricing Competition Impact Score) per SKU using 7
weighted sub-scores.  Category-specific weight tables ensure the score
reflects business reality (e.g. substitution matters most for ink/toner,
basket dependency for canteen, strategic importance for furniture).
"""
from __future__ import annotations

from typing import Optional
import numpy as np

# ── Competition class thresholds ────────────────────────────────────────────
COMPETITION_CLASSES = [
    (0.85, 1.01, "Critical"),
    (0.70, 0.85, "Strong"),
    (0.45, 0.70, "Influence"),
    (0.20, 0.45, "Monitor"),
    (0.00, 0.20, "Ignore"),
]

# ── Category-specific weight tables ─────────────────────────────────────────
# Weights must sum to 1.0 per category.
CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "Ink & Toner": {
        "product_comparability": 0.25,
        "substitution": 0.25,
        "price_sensitivity": 0.15,
        "competitor_relevance": 0.15,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.05,
        "strategic_importance": 0.05,
    },
    "Paper": {
        "price_sensitivity": 0.30,
        "competitor_relevance": 0.25,
        "product_comparability": 0.20,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.05,
        "substitution": 0.05,
        "strategic_importance": 0.05,
    },
    "Office Supplies": {
        "product_comparability": 0.25,
        "price_sensitivity": 0.20,
        "competitor_relevance": 0.20,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.10,
        "strategic_importance": 0.10,
        "substitution": 0.05,
    },
    "Electronics": {
        "product_comparability": 0.30,
        "price_sensitivity": 0.25,
        "competitor_relevance": 0.20,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.05,
        "substitution": 0.05,
        "strategic_importance": 0.05,
    },
    "Packaging": {
        "price_sensitivity": 0.25,
        "competitor_relevance": 0.25,
        "product_comparability": 0.20,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.10,
        "substitution": 0.05,
        "strategic_importance": 0.05,
    },
    "Cleaning": {
        "basket_dependency": 0.25,
        "strategic_importance": 0.20,
        "competitor_relevance": 0.20,
        "price_sensitivity": 0.15,
        "product_comparability": 0.10,
        "competitor_price_reliability": 0.05,
        "substitution": 0.05,
    },
    "Canteen Supplies": {
        "basket_dependency": 0.30,
        "strategic_importance": 0.20,
        "competitor_relevance": 0.15,
        "price_sensitivity": 0.15,
        "product_comparability": 0.10,
        "competitor_price_reliability": 0.05,
        "substitution": 0.05,
    },
    "Furniture": {
        "strategic_importance": 0.30,
        "product_comparability": 0.20,
        "competitor_relevance": 0.20,
        "competitor_price_reliability": 0.10,
        "price_sensitivity": 0.10,
        "basket_dependency": 0.05,
        "substitution": 0.05,
    },
    "Printers": {
        "product_comparability": 0.25,
        "price_sensitivity": 0.25,
        "competitor_relevance": 0.20,
        "strategic_importance": 0.10,
        "competitor_price_reliability": 0.10,
        "basket_dependency": 0.05,
        "substitution": 0.05,
    },
    "default": {
        "product_comparability": 0.20,
        "price_sensitivity": 0.20,
        "competitor_relevance": 0.20,
        "competitor_price_reliability": 0.15,
        "basket_dependency": 0.10,
        "substitution": 0.10,
        "strategic_importance": 0.05,
    },
}

# ── Competitor exclusion reason codes ───────────────────────────────────────
EXCLUSION_OUT_OF_STOCK = "COMPETITOR_IGNORED_OUT_OF_STOCK"
EXCLUSION_BAD_MATCH = "COMPETITOR_IGNORED_BAD_MATCH"
EXCLUSION_OUTLIER = "COMPETITOR_IGNORED_OUTLIER"
EXCLUSION_LOW_RELEVANCE = "COMPETITOR_IGNORED_LOW_RELEVANCE"
EXCLUSION_PACK_SIZE = "COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE"
EXCLUSION_BAD_DELIVERY = "COMPETITOR_IGNORED_BAD_DELIVERY"

# ── Vermoedelijke oorzaak-codes voor prijsuitbijters ────────────────────────
# Een uitbijter wordt nooit stilzwijgend weggegooid: elke uitgesloten prijs
# krijgt naast de reden (EXCLUSION_OUTLIER) ook een vermoedelijke oorzaak,
# afgeleid uit de verhouding prijs/mediaan. Dit maakt de reconciliatie in het
# datakwaliteitscentrum mogelijk (taak: uitbijters verklaarbaar maken).
CAUSE_PACK_MULTIPLE = "PACK_SIZE_MULTIPLE"     # prijs ≈ n× mediaan (grotere verpakking)
CAUSE_PACK_FRACTION = "PACK_SIZE_FRACTION"     # prijs ≈ mediaan/n (kleinere verpakking)
CAUSE_DECIMAL_SHIFT = "DECIMAL_SHIFT"          # prijs ≈ 100×/0,01× (decimaal-/centenfout)
CAUSE_VAT = "VAT_DIFFERENCE"                   # prijs ≈ ±21% (incl./excl. BTW)
CAUSE_EXTREME = "EXTREME_DEVIATION"            # zeer grote afwijking zonder patroon
CAUSE_ABOVE_THRESHOLD = "ABOVE_THRESHOLD"      # boven drempel, geen herkenbaar patroon

# Standaard uitbijterdrempel (fractie van de mediaan). Configureerbaar via de
# import-instellingen (services/import_settings.py, key "outlier_threshold").
DEFAULT_OUTLIER_THRESHOLD = 0.30

_PACK_MULTIPLES = (2, 3, 4, 5, 6, 8, 10, 12, 20, 24)

# Prijs-per-eenheid-normalisatie (taak #269): alleen bij hoge zekerheid.
# Een concurrentprijs die vrijwel exact (±2% van n× de mediaan) een geheel
# n-voud of 1/n van de mediaan is, wordt — mits de eigen pakgrootte bekend is —
# genormaliseerd meegeteld (prijs/n resp. prijs×n) in plaats van uitgesloten.
# Ruimere afwijkingen (tot de 10%-band van classify_outlier_cause) blijven
# twijfelgevallen en dus gemarkeerd uitgesloten.
PACK_NORMALIZE_TOLERANCE = 0.02


def detect_pack_factor(price: float, median: float) -> Optional[tuple[int, str]]:
    """Detecteer met hoge zekerheid een verpakkingsfactor t.o.v. de mediaan.

    Retourneert ``(n, "multiple")`` als prijs ≈ n× mediaan, ``(n, "fraction")``
    als prijs ≈ mediaan/n (binnen ``PACK_NORMALIZE_TOLERANCE``), anders None.
    """
    if median is None or median <= 0 or price is None or price <= 0:
        return None
    r = price / median
    for m in _PACK_MULTIPLES:
        if abs(r - m) <= PACK_NORMALIZE_TOLERANCE * m:
            return m, "multiple"
        if abs(r - 1.0 / m) <= PACK_NORMALIZE_TOLERANCE / m:
            return m, "fraction"
    return None


def classify_outlier_cause(price: float, median: float) -> str:
    """Vermoedelijke oorzaak van een uitbijter op basis van prijs/mediaan.

    Heuristiek, geordend van sterk naar zwak signaal:
    1. factor ~100 of ~0,01 → decimaal-/centenfout in de feed;
    2. bijna exact geheel veelvoud (of 1/n) van de mediaan → verpakkingsmaat;
    3. ±21% → BTW incl./excl.-verschil (alleen relevant bij lage drempels);
    4. > 3× of < 1/3 → extreme afwijking (vermoedelijk verkeerde match);
    5. anders → boven drempel zonder herkenbaar patroon.
    """
    if median is None or median <= 0 or price is None or price <= 0:
        return CAUSE_ABOVE_THRESHOLD
    r = price / median
    if r >= 50 or r <= 0.02:
        return CAUSE_DECIMAL_SHIFT
    for m in _PACK_MULTIPLES:
        if abs(r - m) <= 0.10 * m:
            return CAUSE_PACK_MULTIPLE
        if abs(r - 1.0 / m) <= 0.10 / m:
            return CAUSE_PACK_FRACTION
    if 1.15 <= r <= 1.27 or 0.79 <= r <= 0.87:
        return CAUSE_VAT
    if r >= 3.0 or r <= (1.0 / 3.0):
        return CAUSE_EXTREME
    return CAUSE_ABOVE_THRESHOLD


def get_competition_class(pcis: float) -> str:
    """Map a PCIS score to its named competition class."""
    for low, high, cls in COMPETITION_CLASSES:
        if low <= pcis < high:
            return cls
    return "Ignore"


def weighted_median(prices: list[float], weights: Optional[list[float]] = None) -> Optional[float]:
    """Return weighted median of prices list."""
    if not prices:
        return None
    if weights is None:
        weights = [1.0] * len(prices)
    sorted_pairs = sorted(zip(prices, weights), key=lambda x: x[0])
    sorted_prices = [p for p, _ in sorted_pairs]
    sorted_weights = [w for _, w in sorted_pairs]
    total_weight = sum(sorted_weights)
    cumulative = 0.0
    for price, weight in zip(sorted_prices, sorted_weights):
        cumulative += weight
        if cumulative >= total_weight / 2:
            return price
    return sorted_prices[-1] if sorted_prices else None


def calculate_reference_price(
    raw_prices: list[float],
    outlier_threshold: float = DEFAULT_OUTLIER_THRESHOLD,
    pack_size_known: bool = False,
) -> tuple[Optional[float], int, int, dict, list[dict], list[dict]]:
    """
    Filter outliers from competitor prices and return the weighted median
    reference price plus exclusion statistics.

    Returns ``(ref_price, used, excluded, excluded_reasons, excluded_details,
    normalized_details)``.
    ``excluded_details`` bevat per uitgesloten prijs een dict met de index in
    ``raw_prices``, de prijs, mediaan, afwijking, ratio en vermoedelijke
    oorzaak — zodat de aanroeper de uitsluiting per observatie kan vastleggen
    (nooit stilzwijgend verwijderen, alleen markeren).

    ``pack_size_known=True`` (taak #269) activeert prijs-per-eenheid-
    normalisatie: een prijs die vrijwel exact (±PACK_NORMALIZE_TOLERANCE)
    een n-voud of 1/n van de mediaan is, wordt genormaliseerd (prijs/n resp.
    prijs×n) meegeteld in de referentieprijs in plaats van uitgesloten.
    ``normalized_details`` bevat per genormaliseerde prijs index, originele en
    genormaliseerde prijs, factor en label ("genormaliseerd (n×)").
    Twijfelgevallen (buiten de strakke tolerantie) blijven uitgesloten.
    """
    if not raw_prices:
        return None, 0, 0, {}, [], []

    excluded_reasons: dict[str, int] = {}
    excluded_details: list[dict] = []
    normalized_details: list[dict] = []
    median_raw = float(np.median(raw_prices))
    included: list[float] = []

    for idx, price in enumerate(raw_prices):
        # Normalisatie staat lós van de (configureerbare) uitbijterdrempel:
        # een vrijwel exact n-voud/1-op-n van de mediaan is bij bekende
        # pakgrootte per definitie een verpakkingsverschil en moet per eenheid
        # meetellen — ook als een ruime drempel de prijs anders rauw zou
        # includeren (dat zou de referentieprijs stil vervuilen).
        if pack_size_known:
            factor = detect_pack_factor(price, median_raw)
            if factor is not None:
                n, kind = factor
                normalized = price / n if kind == "multiple" else price * n
                label = f"genormaliseerd ({n}\u00d7)" if kind == "multiple" \
                    else f"genormaliseerd (1/{n}\u00d7)"
                included.append(float(normalized))
                normalized_details.append({
                    "index": idx,
                    "price": round(float(price), 4),
                    "normalized_price": round(float(normalized), 4),
                    "median": round(median_raw, 4),
                    "pack_factor": n,
                    "pack_kind": kind,
                    "label": label,
                })
                continue
        deviation = abs(price - median_raw) / (median_raw + 0.001)
        if deviation > outlier_threshold:
            excluded_reasons[EXCLUSION_OUTLIER] = excluded_reasons.get(EXCLUSION_OUTLIER, 0) + 1
            excluded_details.append({
                "index": idx,
                "price": round(float(price), 4),
                "median": round(median_raw, 4),
                "deviation_pct": round(deviation * 100, 1),
                "ratio": round(price / median_raw, 4) if median_raw > 0 else None,
                "threshold_pct": round(outlier_threshold * 100, 1),
                "suspected_cause": classify_outlier_cause(price, median_raw),
            })
        else:
            included.append(price)

    ref_price = weighted_median(included)
    return (ref_price, len(included), len(raw_prices) - len(included),
            excluded_reasons, excluded_details, normalized_details)
