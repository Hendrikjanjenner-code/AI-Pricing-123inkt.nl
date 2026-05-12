"""
CSRS — Competitor Stock Reliability Score.

Beoordeelt hoe betrouwbaar een concurrent is qua voorraad en levering.
CSRS bepaalt of een concurrent meegewogen wordt in de referentieprijs.

Formule:
  CSRS = 0.40 * availability_rate
       + 0.25 * delivery_speed_score
       + 0.20 * stock_stability_score
       + 0.15 * listing_consistency_score

Regels:
  CSRS < 0.25  → negeren   (COMPETITOR_IGNORED_OUT_OF_STOCK / UNSTABLE)
  0.25–0.60    → monitoren / afzwakken
  >= 0.60      → normaal meenemen
"""
from __future__ import annotations

CSRS_WEIGHT_AVAILABILITY = 0.40
CSRS_WEIGHT_DELIVERY = 0.25
CSRS_WEIGHT_STABILITY = 0.20
CSRS_WEIGHT_CONSISTENCY = 0.15

# Reden codes
RC_IGNORED_OUT_OF_STOCK = "COMPETITOR_IGNORED_OUT_OF_STOCK"
RC_IGNORED_BAD_DELIVERY = "COMPETITOR_IGNORED_BAD_DELIVERY"
RC_IGNORED_UNSTABLE_STOCK = "COMPETITOR_IGNORED_UNSTABLE_STOCK"
RC_IGNORED_UNSTABLE_LISTING = "COMPETITOR_IGNORED_UNSTABLE_LISTING"
RC_DOWNWEIGHTED = "COMPETITOR_DOWNWEIGHTED_UNSTABLE_STOCK"
RC_INCLUDED = "COMPETITOR_INCLUDED_STOCK_RELIABLE"


def calculate_csrs(
    availability_rate: float,
    delivery_speed_score: float,
    stock_stability_score: float,
    listing_consistency_score: float,
) -> float:
    """Bereken de CSRS score (0.0 – 1.0)."""
    return round(
        CSRS_WEIGHT_AVAILABILITY * availability_rate
        + CSRS_WEIGHT_DELIVERY * delivery_speed_score
        + CSRS_WEIGHT_STABILITY * stock_stability_score
        + CSRS_WEIGHT_CONSISTENCY * listing_consistency_score,
        4,
    )


def get_csrs_status(csrs: float) -> tuple[str, str, str]:
    """
    Geeft (status, reason_code, pricing_action) terug op basis van CSRS.

    Returns:
        status: 'Actief' | 'Monitoren' | 'Negeren'
        reason_code: één van de RC_* constanten
        pricing_action: beschrijving van te nemen actie
    """
    if csrs < 0.25:
        # Bepaal specifiekste reden
        return (
            "Negeren",
            RC_IGNORED_OUT_OF_STOCK,
            "IGNORE_LOW_STOCK_RELIABILITY",
        )
    elif csrs < 0.60:
        return (
            "Monitoren",
            RC_DOWNWEIGHTED,
            "WATCH_ONLY_LOW_STOCK_RELIABILITY",
        )
    else:
        return (
            "Actief",
            RC_INCLUDED,
            "INCLUDE_NORMAL_WEIGHT",
        )


def get_csrs_label(csrs: float) -> str:
    """Leesbaar label voor de UI."""
    if csrs >= 0.60:
        return "Betrouwbaar"
    elif csrs >= 0.25:
        return "Matig betrouwbaar"
    else:
        return "Onbetrouwbaar"
