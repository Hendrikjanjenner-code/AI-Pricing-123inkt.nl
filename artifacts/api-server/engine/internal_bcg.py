"""
Internal BCG — berekent IBSS (Internal Business Strength Score) en classificeert.

Vraag: "Hoe belangrijk is dit product voor onze business?"

X-as: Internal Business Strength Score (IBSS)
Y-as: Growth Potential Score (GPS)

Classificaties:
  INTERNAL_STAR           IBSS >= 0.60, GPS >= 0.60
  INTERNAL_CASH_COW       IBSS >= 0.60, GPS <  0.60
  INTERNAL_QUESTION_MARK  IBSS <  0.60, GPS >= 0.60
  INTERNAL_DOG            IBSS <  0.60, GPS <  0.60
"""
from typing import Any

THRESHOLD_HIGH = 0.60


def calculate_internal_business_strength(
    sku_data: dict[str, Any],
    total_revenue: float,
    total_margin: float,
) -> float:
    """
    IBSS = gewogen combinatie van:
    - omzetbijdrage (revenue_share)
    - margebijdrage (margin_share)
    - repeat-aankooprate (geschat uit verkoopfrequentie)
    - mandbijdrage (basket_impact)
    - huismerkwaarde (private label bonus)
    - strategisch gewicht
    """
    revenue = float(sku_data.get("revenue_30d") or 0)
    margin = float(sku_data.get("margin_30d") or 0)
    is_private_label = bool(sku_data.get("is_private_label"))
    is_a_brand = bool(sku_data.get("is_a_brand"))
    basket_affinity = float(sku_data.get("basket_affinity_score") or 0.0)
    strategy_weight = float(sku_data.get("strategy_weight") or 0.5)
    stock_quantity = int(sku_data.get("stock_quantity") or 0)

    # Omzetbijdrage (0–1)
    revenue_share = min(1.0, revenue / max(total_revenue * 0.05, 1.0))

    # Margebijdrage (0–1)
    margin_share = min(1.0, margin / max(total_margin * 0.05, 1.0)) if total_margin > 0 else 0.0

    # Repeat-rate: hoog als hoge voorraad en regelmatige verkoop
    repeat_score = min(1.0, stock_quantity / 500) * 0.5 + 0.3

    # Basket impact (0–1)
    basket_score = min(1.0, basket_affinity)

    # Huismerktoeslag: huismerk is strategisch waardevoller
    brand_bonus = 0.15 if is_private_label else (0.05 if is_a_brand else 0.0)

    ibss = (
        revenue_share   * 0.30
        + margin_share    * 0.25
        + repeat_score    * 0.15
        + basket_score    * 0.10
        + strategy_weight * 0.15
        + brand_bonus
    )

    return round(min(1.0, max(0.0, ibss)), 4)


def classify_internal_bcg(ibss: float, gps: float) -> str:
    """Classificeert SKU in interne BCG-matrix op basis van IBSS en GPS."""
    high_ibss = ibss >= THRESHOLD_HIGH
    high_gps = gps >= THRESHOLD_HIGH

    if high_ibss and high_gps:
        return "INTERNAL_STAR"
    elif high_ibss and not high_gps:
        return "INTERNAL_CASH_COW"
    elif not high_ibss and high_gps:
        return "INTERNAL_QUESTION_MARK"
    else:
        return "INTERNAL_DOG"


def get_internal_bcg_nl(classification: str) -> str:
    """Nederlandstalig label voor interne BCG-classificatie."""
    labels = {
        "INTERNAL_STAR":           "Interne Ster",
        "INTERNAL_CASH_COW":       "Interne Cash Cow",
        "INTERNAL_QUESTION_MARK":  "Intern Vraagteken",
        "INTERNAL_DOG":            "Interne Dog",
    }
    return labels.get(classification, classification)
