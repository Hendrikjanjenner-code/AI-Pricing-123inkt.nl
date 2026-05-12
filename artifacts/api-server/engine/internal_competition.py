"""
Interne Concurrentiemodule — A-merk vs Huismerk.

ISV = Internal Substitution Value
    = internal_switch_probability * internal_margin_gap

Doel:
  Bepalen of externe prijsdruk op een A-merk gereageerd moet worden,
  of dat het beter is om klanten naar het huismerk te sturen.

Nieuwe strategie-typen:
  PRIVATE_LABEL_PUSH        — huismerk actief positioneren
  PORTFOLIO_MARGIN_OPTIMIZATION — balanceer marge over het portfolio
  TRAFFIC_TO_MARGIN_SWITCH  — stuur traffic van A-merk naar huismerk

Aanbevolen acties:
  - ISV > 0.50 én externe druk: PRIVATE_LABEL_PUSH
  - ISV > 0.30 én kleine marge kloof: PORTFOLIO_MARGIN_OPTIMIZATION
  - ISV < 0.20: pas A-merkprijs aan op concurrentie
"""
from __future__ import annotations
from typing import Optional

# Drempelwaarden
ISV_HIGH = 0.50
ISV_MEDIUM = 0.30
ISV_LOW = 0.10

# Aanbevolen acties
ACTION_PRIVATE_LABEL_PUSH = "PRIVATE_LABEL_PUSH"
ACTION_PORTFOLIO_MARGIN = "PORTFOLIO_MARGIN_OPTIMIZATION"
ACTION_TRAFFIC_SWITCH = "TRAFFIC_TO_MARGIN_SWITCH"
ACTION_PRICE_A_BRAND = "PRICE_A_BRAND_COMPETITIVELY"
ACTION_HOLD = "HOLD_PRICE_MONITOR"

# Reason codes
RC_PRIVATE_LABEL_OPPORTUNITY = "PRIVATE_LABEL_MARGIN_OPPORTUNITY"
RC_INTERNAL_SUBSTITUTION_HIGH = "INTERNAL_SUBSTITUTION_HIGH"
RC_PORTFOLIO_PROTECTION = "PORTFOLIO_MARGIN_PROTECTION"


def calculate_isv(
    internal_switch_probability: float,
    internal_margin_gap: float,
) -> float:
    """ISV = schakelkans × margekloof per eenheid."""
    return round(internal_switch_probability * internal_margin_gap, 4)


def get_recommended_action(
    isv: float,
    external_price_pressure: float,
    a_brand_margin_pct: float,
    private_label_margin_pct: float,
) -> tuple[str, str, str]:
    """
    Bepaal aanbevolen actie op basis van ISV en externe druk.

    Args:
        isv: Internal Substitution Value
        external_price_pressure: hoeveel goedkoper de concurrent is (0.0 – 1.0, positief = druk)
        a_brand_margin_pct: huidige marge A-merk
        private_label_margin_pct: marge huismerk

    Returns:
        (action, reason_code, uitleg_nl)
    """
    margin_advantage = private_label_margin_pct - a_brand_margin_pct

    if isv >= ISV_HIGH and external_price_pressure > 0.05:
        return (
            ACTION_PRIVATE_LABEL_PUSH,
            RC_PRIVATE_LABEL_OPPORTUNITY,
            "Hoge substitutiekans + externe druk: stuur actief naar huismerk"
        )
    elif isv >= ISV_MEDIUM and margin_advantage > 0.05:
        return (
            ACTION_PORTFOLIO_MARGIN,
            RC_PORTFOLIO_PROTECTION,
            "Optimaliseer portfolio-marge: huismerk stimuleren zonder A-merkprijs te verlagen"
        )
    elif isv >= ISV_MEDIUM and external_price_pressure > 0.10:
        return (
            ACTION_TRAFFIC_SWITCH,
            RC_INTERNAL_SUBSTITUTION_HIGH,
            "Hoge concurrentiedruk op A-merk: traffic naar huismerk sturen"
        )
    elif external_price_pressure > 0.08 and isv < ISV_LOW:
        return (
            ACTION_PRICE_A_BRAND,
            "PRIMARY_COMPETITOR_PRESSURE",
            "Lage substitutiekans: volg concurrentieprijs voor A-merk"
        )
    else:
        return (
            ACTION_HOLD,
            "COMPETITION_SIGNAL_WEAK",
            "Zwak concurrentiesignaal of lage ISV: prijsbehoud aanbevolen"
        )


def estimate_switch_probability(
    price_gap_pct: float,
    substitution_strength: float,
    is_repeat_buyer: bool = False,
    basket_affinity: float = 0.0,
) -> float:
    """
    Schat de kans dat een klant overstapt van A-merk naar huismerk.

    Args:
        price_gap_pct: prijsverschil huismerk vs A-merk (negatief = huismerk goedkoper)
        substitution_strength: bekende substitutie-sterkte (0–1)
        is_repeat_buyer: vaste klanten schakelen minder makkelijk over
        basket_affinity: hoe sterk het product in basketcombinaties zit
    """
    # Basis op prijskloof: grotere kloof = hogere overstapkans
    base_prob = min(abs(price_gap_pct) * 2.5, 0.85) if price_gap_pct < 0 else 0.10

    # Substitutiesterkte verhoogt kans
    prob = base_prob * (0.5 + 0.5 * substitution_strength)

    # Vaste klanten schakelen minder makkelijk
    if is_repeat_buyer:
        prob *= 0.70

    # Sterke basket-binding vermindert schakelkans
    if basket_affinity > 0.60:
        prob *= 0.80

    return round(min(prob, 0.95), 3)
