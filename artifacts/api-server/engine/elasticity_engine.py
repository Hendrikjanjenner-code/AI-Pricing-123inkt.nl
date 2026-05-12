"""
Elasticiteitsengine — prijsgevoeligheid per SKU.

Berekent vier elasticiteitstypen:
  1. Eigen prijselasticiteit       — eigen prijs ↑ → volume ↓
  2. Kruiselasticiteit             — marktprijs ↑ → eigen volume ↑
  3. Competitieve elasticiteit     — gevoeligheid voor concurrentieprijs
  4. Interne substitutie-elast.   — overstap naar huismerk

Betrouwbaarheidsclassificatie:
  > 0.80  = hoog betrouwbaar
  0.50–0.80 = bruikbaar
  < 0.50  = laag betrouwbaar

Context-factoren:
  - categorie
  - prijsvariatie laatste 30 dagen
  - salesvolume
  - PCIS (concurrentiedruk)
  - CSRS (voorraadbetrouwbaarheid concurrent)
  - huismerk/A-merk substitutie
  - basket-impact
"""
from __future__ import annotations
from typing import Optional

# Baseline elasticiteitswaarden per categorie
# (negatief = vraag daalt bij prijsstijging, positief bij kruiselasticiteit)
CATEGORY_BASE_ELASTICITY: dict[str, dict] = {
    "Ink & Toner": {
        "own": -1.8,
        "cross": 0.6,
        "competitive": 1.2,
        "internal_sub": -2.1,
        "confidence_base": 0.72,
    },
    "Paper": {
        "own": -2.5,
        "cross": 0.8,
        "competitive": 1.8,
        "internal_sub": -0.3,
        "confidence_base": 0.80,
    },
    "Office Supplies": {
        "own": -1.2,
        "cross": 0.4,
        "competitive": 0.8,
        "internal_sub": -0.5,
        "confidence_base": 0.65,
    },
    "Electronics": {
        "own": -2.8,
        "cross": 1.2,
        "competitive": 2.1,
        "internal_sub": -0.2,
        "confidence_base": 0.75,
    },
    "Packaging": {
        "own": -1.5,
        "cross": 0.5,
        "competitive": 1.0,
        "internal_sub": -0.4,
        "confidence_base": 0.68,
    },
    "Cleaning": {
        "own": -0.8,
        "cross": 0.2,
        "competitive": 0.5,
        "internal_sub": -0.6,
        "confidence_base": 0.58,
    },
    "Canteen Supplies": {
        "own": -0.9,
        "cross": 0.3,
        "competitive": 0.6,
        "internal_sub": -0.8,
        "confidence_base": 0.60,
    },
    "Furniture": {
        "own": -0.5,
        "cross": 0.1,
        "competitive": 0.3,
        "internal_sub": -0.1,
        "confidence_base": 0.42,
    },
    "Printers": {
        "own": -2.2,
        "cross": 0.9,
        "competitive": 1.6,
        "internal_sub": -0.3,
        "confidence_base": 0.70,
    },
    "default": {
        "own": -1.5,
        "cross": 0.5,
        "competitive": 1.0,
        "internal_sub": -0.5,
        "confidence_base": 0.60,
    },
}


def calculate_elasticity(
    category: str,
    pcis_score: float,
    csrs_score: float,
    sales_volume_30d: float,
    price_variation_pct: float,
    is_private_label: bool = False,
    is_a_brand: bool = False,
    has_internal_substitute: bool = False,
    basket_affinity_score: float = 0.0,
) -> dict:
    """
    Bereken alle elasticiteitsscores voor een SKU.

    Returns dict met:
      own_price_elasticity, cross_elasticity, competitive_elasticity,
      internal_substitution_elasticity, elasticity_confidence_score,
      confidence_class
    """
    base = CATEGORY_BASE_ELASTICITY.get(category, CATEGORY_BASE_ELASTICITY["default"])

    # Aanpassen op basis van context
    pcis_factor = 0.8 + 0.4 * pcis_score  # Hogere PCIS → hogere elasticiteit
    csrs_factor = 0.9 + 0.2 * csrs_score  # Hogere CSRS → betere datakwaliteit

    own_elast = round(base["own"] * pcis_factor, 3)
    cross_elast = round(base["cross"] * pcis_factor, 3)
    competitive_elast = round(base["competitive"] * csrs_factor, 3)

    # Interne substitutie alleen relevant als er een huismerk-alternatief is
    if has_internal_substitute:
        internal_elast = round(base["internal_sub"] * (1.2 if is_a_brand else 0.8), 3)
    else:
        internal_elast = 0.0

    # Betrouwbaarheidsberekening
    confidence = base["confidence_base"]

    # Correcties op betrouwbaarheid
    if sales_volume_30d < 5:
        confidence -= 0.20   # Weinig data
    elif sales_volume_30d > 50:
        confidence += 0.10   # Veel data

    if price_variation_pct < 0.01:
        confidence -= 0.15   # Geen prijsvariatie → slechte schatting

    if pcis_score > 0.70:
        confidence += 0.08   # Sterke concurrentie = betere signalen

    confidence = round(min(max(confidence, 0.10), 0.98), 3)

    confidence_class = (
        "hoog_betrouwbaar" if confidence > 0.80
        else "bruikbaar" if confidence >= 0.50
        else "laag_betrouwbaar"
    )

    return {
        "own_price_elasticity": own_elast,
        "cross_elasticity": cross_elast,
        "competitive_elasticity": competitive_elast,
        "internal_substitution_elasticity": internal_elast,
        "elasticity_confidence_score": confidence,
        "confidence_class": confidence_class,
    }


def get_confidence_label(confidence_class: str) -> str:
    """Nederlandse UI-label."""
    return {
        "hoog_betrouwbaar": "Hoog betrouwbaar",
        "bruikbaar": "Bruikbaar",
        "laag_betrouwbaar": "Laag betrouwbaar",
    }.get(confidence_class, confidence_class)
