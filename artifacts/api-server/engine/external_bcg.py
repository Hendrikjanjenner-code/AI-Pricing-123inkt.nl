"""
External BCG — berekent CSS_EXTERNAL (Competitive Strength Score) en MOS
(Market Opportunity Score) en classificeert.

Vraag: "Hoe sterk staat dit product in de markt?"

X-as: Competitive Strength Score (CSS_EXTERNAL)
Y-as: Market Opportunity Score (MOS)

Classificaties:
  EXTERNAL_STAR           CSS >= 0.60, MOS >= 0.60
  EXTERNAL_CASH_COW       CSS >= 0.60, MOS <  0.60
  EXTERNAL_QUESTION_MARK  CSS <  0.60, MOS >= 0.60
  EXTERNAL_DOG            CSS <  0.60, MOS <  0.60
"""
from typing import Any

THRESHOLD_HIGH = 0.60


def calculate_competitive_strength(
    sku_data: dict[str, Any],
) -> float:
    """
    CSS_EXTERNAL = maatstaf voor marktpositie.

    Gebaseerd op:
    - prijspositie vs concurrenten (price_index: eigen prijs / referentieprijs)
    - PCIS-score (omgekeerd: lage PCIS = minder concurrentiedruk = sterker)
    - CIS / CSRS / CSS scores van concurrenten
    - Voorraadbetrouwbaarheid
    - Substitutiepositie
    """
    price_index = float(sku_data.get("price_index") or 1.0)
    pcis_score = float(sku_data.get("pcis_score") or 0.5)
    cis_score = float(sku_data.get("cis_score") or 0.5)
    csrs_score = float(sku_data.get("csrs_score") or 0.5)
    css_score = float(sku_data.get("css_score") or 0.5)
    substitution_score = float(sku_data.get("substitution_score") or 0.3)

    # Prijspositie: lager dan concurrenten = sterker (price_index < 1.0 = goedkoper)
    # Price index 0.90 → score 0.80, 1.00 → 0.60, 1.10 → 0.40
    price_position_score = min(1.0, max(0.0, 1.0 - (price_index - 0.90) * 2.0))

    # PCIS omgekeerd: hoge PCIS = veel concurrentiedruk = zwakkere positie
    pcis_strength = 1.0 - min(1.0, pcis_score)

    # Gemiddeld CIS van concurrenten (lager = minder bedreiging = sterker)
    cis_strength = 1.0 - min(1.0, cis_score)

    # CSRS: hoge voorraadbetrouwbaarheid concurrent = meer druk
    csrs_strength = 1.0 - min(1.0, csrs_score * 0.5)

    # CSS duurzaamheid
    css_strength = 1.0 - min(1.0, css_score * 0.5)

    css_external = (
        price_position_score * 0.30
        + pcis_strength       * 0.25
        + cis_strength        * 0.20
        + csrs_strength       * 0.15
        + css_strength        * 0.10
    )

    return round(min(1.0, max(0.0, css_external)), 4)


def calculate_market_opportunity(
    sku_data: dict[str, Any],
    category_growth: float = 0.05,
) -> float:
    """
    MOS = Market Opportunity Score.

    Gebaseerd op:
    - groeipotentieel van de categorie
    - concurrentiedynamiek (veel concurrenten = meer kans)
    - prijsmogelijkheden (headroom)
    - vraagontwikkeling
    - substitutiepotentie
    """
    gps = float(sku_data.get("gps_score") or 0.4)
    competitors_used = int(sku_data.get("competitors_used") or 0)
    margin_pct = float(sku_data.get("margin_pct") or 0.20)
    elasticity = float(sku_data.get("own_price_elasticity") or -1.5)
    is_private_label = bool(sku_data.get("is_private_label"))

    # Categorie-groei bijdrage
    cat_growth_score = min(1.0, max(0.0, 0.5 + category_growth * 2.0))

    # Meer concurrenten = grotere markt
    competitor_score = min(1.0, competitors_used / 5.0)

    # Margeruimte: hogere marge = meer kansen
    margin_score = min(1.0, margin_pct / 0.40)

    # Lage elasticiteit (inelastisch) = meer prijsmacht = hogere MOS
    elasticity_score = min(1.0, max(0.0, 1.0 + elasticity / 3.0))  # elasticity -3..0 → 0..1

    # Huismerk heeft hogere MOS door substitutiepotentie
    pl_bonus = 0.10 if is_private_label else 0.0

    mos = (
        cat_growth_score   * 0.25
        + gps              * 0.25
        + competitor_score * 0.15
        + margin_score     * 0.20
        + elasticity_score * 0.15
        + pl_bonus
    )

    return round(min(1.0, max(0.0, mos)), 4)


def classify_external_bcg(css_external: float, mos: float) -> str:
    """Classificeert SKU in externe BCG-matrix."""
    high_css = css_external >= THRESHOLD_HIGH
    high_mos = mos >= THRESHOLD_HIGH

    if high_css and high_mos:
        return "EXTERNAL_STAR"
    elif high_css and not high_mos:
        return "EXTERNAL_CASH_COW"
    elif not high_css and high_mos:
        return "EXTERNAL_QUESTION_MARK"
    else:
        return "EXTERNAL_DOG"


def get_external_bcg_nl(classification: str) -> str:
    labels = {
        "EXTERNAL_STAR":           "Externe Ster",
        "EXTERNAL_CASH_COW":       "Externe Cash Cow",
        "EXTERNAL_QUESTION_MARK":  "Extern Vraagteken",
        "EXTERNAL_DOG":            "Externe Dog",
    }
    return labels.get(classification, classification)
