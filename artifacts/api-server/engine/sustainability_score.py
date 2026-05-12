"""
CSS — Competitor Sustainability Score (Duurzaamheid Concurrentieprijs).

Bepaalt of een lage concurrentieprijs duurzaam en geloofwaardig is.
Een lage prijs met lage CSS mag NIET automatisch tot prijsverlaging leiden.

Factoren:
  - Prijsafwijking t.o.v. de markt (grote outliers = laag)
  - Prijsvolatiliteit (instabiele prijs = laag)
  - Voorraadgedrag (veel out-of-stock = lage duurzaamheid)
  - Type concurrent (marketplace seller vs. gevestigd retailer)
  - Leverbetrouwbaarheid

Gewichten:
  CSS = 0.30 * price_deviation_score   (hoe dichter bij markt, hoe beter)
      + 0.25 * price_volatility_score  (laag = stabiel = goed)
      + 0.20 * stock_behavior_score    (consistent op voorraad = goed)
      + 0.15 * competitor_type_score   (gevestigd retailer = hoog)
      + 0.10 * delivery_reliability    (betrouwbare levering = goed)
"""
from __future__ import annotations

CSS_WEIGHT_DEVIATION = 0.30
CSS_WEIGHT_VOLATILITY = 0.25
CSS_WEIGHT_STOCK_BEHAVIOR = 0.20
CSS_WEIGHT_TYPE = 0.15
CSS_WEIGHT_DELIVERY = 0.10

# Reden codes voor lage CSS
RC_IGNORED_LOW_CSS = "IGNORED_LOW_CSS"
RC_WATCH_ONLY = "WATCH_ONLY_LOW_STOCK_RELIABILITY"
RC_LOW_PRICE_LOW_STOCK = "LOW_PRICE_LOW_STOCK_RELIABILITY"

# Drempelwaarden
CSS_STRONG = 0.70
CSS_MODERATE = 0.45


def calculate_css(
    price_deviation_score: float,
    price_volatility_score: float,
    stock_behavior_score: float,
    competitor_type_score: float,
    delivery_reliability: float,
) -> float:
    """Bereken de CSS score (0.0 – 1.0). Hogere score = duurzamere prijs."""
    return round(
        CSS_WEIGHT_DEVIATION * price_deviation_score
        + CSS_WEIGHT_VOLATILITY * price_volatility_score
        + CSS_WEIGHT_STOCK_BEHAVIOR * stock_behavior_score
        + CSS_WEIGHT_TYPE * competitor_type_score
        + CSS_WEIGHT_DELIVERY * delivery_reliability,
        4,
    )


def get_css_label(css: float) -> str:
    """Leesbaar label voor de UI."""
    if css >= CSS_STRONG:
        return "Duurzaam"
    elif css >= CSS_MODERATE:
        return "Twijfelachtig"
    else:
        return "Niet duurzaam"


def should_follow_price(css: float, csrs: float, price_gap_pct: float) -> tuple[bool, str]:
    """
    Bepaal of we de concurrentieprijs moeten volgen.

    Args:
        css: Competitor Sustainability Score
        csrs: Competitor Stock Reliability Score
        price_gap_pct: prijsverschil als percentage (negatief = concurrent goedkoper)

    Returns:
        (follow_price: bool, reason_code: str)
    """
    if css < CSS_MODERATE and csrs < 0.50 and price_gap_pct < -0.10:
        # Lage CSS + lage CSRS + significant goedkoper → niet volgen
        return False, RC_LOW_PRICE_LOW_STOCK
    elif css < CSS_MODERATE:
        return False, RC_IGNORED_LOW_CSS
    elif csrs < 0.25:
        return False, RC_WATCH_ONLY
    else:
        return True, "INCLUDE_NORMAL_WEIGHT"
