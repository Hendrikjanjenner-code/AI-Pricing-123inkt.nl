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
from typing import Optional

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
