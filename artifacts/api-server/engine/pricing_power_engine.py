"""
Pricing Power Engine — berekent Pricing Power Score (PPS) per SKU.

Pricing power = de mate waarin een bedrijf zijn prijs kan verhogen
zonder significant omzetverlies.

Hoge pricing power:
- lage prijselasticiteit
- geringe concurrentiedruk (lage PCIS)
- hoge margeruimte
- sterk merk of uniek product

Lage pricing power:
- hoge elasticiteit
- veel directe concurrenten
- krappe marges
- commodityproduct
"""
from typing import Any


def calculate_pricing_power_score(sku_data: dict[str, Any]) -> float:
    """
    PPS (Pricing Power Score) bereik 0.00–1.00.

    Inputs (uit sku_data):
    - own_price_elasticity: eigen prijselasticiteit (negatief getal, bv. -1.5)
    - pcis_score:           PCIS concurrentiedruk (0–1)
    - margin_pct:           brutomargepct
    - is_private_label:     bool
    - is_a_brand:           bool
    - competitors_used:     aantal relevante concurrenten
    - css_score:            Competitor Sustainability Score
    """
    elasticity = float(sku_data.get("own_price_elasticity") or -1.5)
    pcis_score = float(sku_data.get("pcis_score") or 0.5)
    margin_pct = float(sku_data.get("margin_pct") or 0.25)
    is_private_label = bool(sku_data.get("is_private_label"))
    is_a_brand = bool(sku_data.get("is_a_brand"))
    competitors_used = int(sku_data.get("competitors_used") or 2)
    css_score = float(sku_data.get("css_score") or 0.5)

    # Elasticiteit → pricing power: -0.5 (inelastisch) = hoog, -3.0 = laag
    # elasticity bereik: -3.0..0 → score 0..1
    elasticity_score = min(1.0, max(0.0, (elasticity + 3.0) / 3.0))

    # PCIS (omgekeerd): lage PCIS = weinig concurrentiedruk = meer pricing power
    pcis_power = 1.0 - min(1.0, pcis_score)

    # Margeruimte: hogere marge = meer buffer voor prijsverhoging
    margin_score = min(1.0, margin_pct / 0.50)

    # Merkwaarde
    brand_score = 0.80 if is_a_brand else (0.70 if is_private_label else 0.40)

    # Aantal concurrenten (meer = minder power)
    competitor_score = max(0.0, 1.0 - competitors_used / 6.0)

    # CSS: stabiele concurrenten = meer druk (omgekeerd)
    css_power = 1.0 - min(1.0, css_score)

    pps = (
        elasticity_score * 0.30
        + pcis_power       * 0.25
        + margin_score     * 0.20
        + brand_score      * 0.10
        + competitor_score * 0.10
        + css_power        * 0.05
    )

    return round(min(1.0, max(0.0, pps)), 4)


def get_pricing_power_label(score: float) -> str:
    """Geeft een beschrijvend label terug voor de pricing power score."""
    if score >= 0.75:
        return "Zeer hoog"
    elif score >= 0.60:
        return "Hoog"
    elif score >= 0.45:
        return "Gemiddeld"
    elif score >= 0.30:
        return "Laag"
    else:
        return "Zeer laag"
