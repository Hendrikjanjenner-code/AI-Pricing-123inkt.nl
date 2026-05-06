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
    outlier_threshold: float = 0.30,
) -> tuple[Optional[float], int, int, dict]:
    """
    Filter outliers from competitor prices and return the weighted median
    reference price plus exclusion statistics.
    """
    if not raw_prices:
        return None, 0, 0, {}

    excluded_reasons: dict[str, int] = {}
    median_raw = float(np.median(raw_prices))
    included: list[float] = []

    for price in raw_prices:
        deviation = abs(price - median_raw) / (median_raw + 0.001)
        if deviation > outlier_threshold:
            excluded_reasons[EXCLUSION_OUTLIER] = excluded_reasons.get(EXCLUSION_OUTLIER, 0) + 1
        else:
            included.append(price)

    ref_price = weighted_median(included)
    return ref_price, len(included), len(raw_prices) - len(included), excluded_reasons
