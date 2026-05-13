"""
Private Label Intelligence — berekent PLSV (Private Label Strategic Value Score)
en ISV (Internal Substitution Value) voor huismerk-SKU's.

Specifiek voor 123inkt: huismerk is cruciaal voor marge en traffic-to-margin strategie.

Private Label classificaties:
  PRIVATE_LABEL_STAR       PLSV >= 0.70
  PRIVATE_LABEL_GROWTH     0.50 <= PLSV < 0.70
  PRIVATE_LABEL_DEFENSIVE  0.30 <= PLSV < 0.50
  PRIVATE_LABEL_LOW_PRIORITY PLSV < 0.30
"""
from typing import Any


def calculate_private_label_value(
    sku_data: dict[str, Any],
    a_brand_data: dict[str, Any] | None = None,
) -> tuple[float, float, float, float]:
    """
    Berekent ISV en PLSV voor een huismerk-SKU.

    Returns:
        (switch_probability, margin_gap, isv, plsv)
    """
    pl_margin_pct = float(sku_data.get("margin_pct") or 0.40)
    pl_price = float(sku_data.get("current_price") or 10.0)
    pl_cost = float(sku_data.get("cost_price") or 5.0)
    basket_affinity = float(sku_data.get("basket_affinity_score") or 0.3)
    repeat_rate = float(sku_data.get("repeat_rate") or 0.4)

    # Bepaal A-merk data
    if a_brand_data:
        a_margin_pct = float(a_brand_data.get("margin_pct") or 0.20)
        a_price = float(a_brand_data.get("current_price") or pl_price * 2.0)
    else:
        a_margin_pct = pl_margin_pct * 0.5
        a_price = pl_price * 2.5

    # Overstapkans: hoe groter het prijsverschil, hoe groter de kans
    price_gap_ratio = max(0.0, (a_price - pl_price) / a_price) if a_price > 0 else 0.3
    switch_probability = min(0.95, price_gap_ratio * 1.5 + 0.10)

    # Margeverschil per eenheid (€)
    a_margin_per_unit = a_price * a_margin_pct
    pl_margin_per_unit = pl_price * pl_margin_pct
    margin_gap = round(pl_margin_per_unit - a_margin_per_unit * 0.3, 4)

    # ISV = overstapkans × margeverschil (genormaliseerd)
    isv = round(switch_probability * min(1.0, abs(margin_gap) / 5.0), 4)

    # PLSV = gewogen combinatie
    pl_margin_score = min(1.0, pl_margin_pct / 0.50)
    price_gap_score = min(1.0, price_gap_ratio * 2.0)
    basket_score = basket_affinity
    repeat_score = repeat_rate

    plsv = (
        pl_margin_score * 0.35
        + price_gap_score * 0.30
        + basket_score    * 0.20
        + repeat_score    * 0.15
    )

    return (
        round(switch_probability, 4),
        round(margin_gap, 4),
        round(isv, 4),
        round(min(1.0, max(0.0, plsv)), 4),
    )


def classify_private_label(plsv: float) -> tuple[str, str]:
    """Classificeert huismerk-SKU en geeft strategische prioriteit terug."""
    if plsv >= 0.70:
        return ("PRIVATE_LABEL_STAR", "hoog")
    elif plsv >= 0.50:
        return ("PRIVATE_LABEL_GROWTH", "hoog")
    elif plsv >= 0.30:
        return ("PRIVATE_LABEL_DEFENSIVE", "gemiddeld")
    else:
        return ("PRIVATE_LABEL_LOW_PRIORITY", "laag")


def get_pl_class_nl(classification: str) -> str:
    labels = {
        "PRIVATE_LABEL_STAR":          "Huismerk Ster",
        "PRIVATE_LABEL_GROWTH":        "Huismerk Groei",
        "PRIVATE_LABEL_DEFENSIVE":     "Huismerk Defensief",
        "PRIVATE_LABEL_LOW_PRIORITY":  "Huismerk Laag Prioriteit",
    }
    return labels.get(classification, classification)
