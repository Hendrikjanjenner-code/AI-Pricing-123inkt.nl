"""
Centrale commerciële metric-definities (masterprompt §5).

Eén plek waar de betekenis en berekening van elke commerciële metric is
vastgelegd. De semantic layer en dashboards gebruiken deze definities zodat
"Revenue" of "Gross Margin" overal exact hetzelfde betekent.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    name: str            # canonieke naam (gebruikt in IntelligenceSignal.metric)
    label_nl: str
    description: str
    formula: str
    unit: str            # eur / units / pct / ratio / count


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    m.name: m for m in [
        MetricDefinition(
            "revenue", "Omzet",
            "Totale verkoopopbrengst exclusief BTW over de periode.",
            "SUM(fact_sales_daily.revenue)", "eur"),
        MetricDefinition(
            "units_sold", "Afzet",
            "Aantal verkochte eenheden over de periode.",
            "SUM(fact_sales_daily.units_sold)", "units"),
        MetricDefinition(
            "cost", "Inkoopkosten",
            "Totale inkoopkosten (COGS) over de periode.",
            "SUM(fact_sales_daily.cost)", "eur"),
        MetricDefinition(
            "gross_margin", "Brutomarge",
            "Omzet minus inkoopkosten over de periode.",
            "SUM(revenue) - SUM(cost)", "eur"),
        MetricDefinition(
            "gross_margin_pct", "Brutomarge %",
            "Brutomarge als percentage van de omzet.",
            "(SUM(revenue) - SUM(cost)) / SUM(revenue) * 100", "pct"),
        MetricDefinition(
            "asp", "Gemiddelde verkoopprijs (ASP)",
            "Gemiddelde gerealiseerde verkoopprijs per eenheid.",
            "SUM(revenue) / SUM(units_sold)", "eur"),
        MetricDefinition(
            "price_index", "Prijsindex",
            "Eigen prijs gedeeld door concurrent-referentieprijs. "
            "<1.0 = wij zijn goedkoper, >1.0 = wij zijn duurder.",
            "own_price / competitor_reference_price", "ratio"),
        MetricDefinition(
            "stock_quantity", "Voorraad",
            "Actuele voorraad in eenheden.",
            "dim_product.stock_quantity", "units"),
        MetricDefinition(
            "days_of_stock", "Voorraaddagen",
            "Aantal dagen dat de huidige voorraad meegaat bij het huidige verkooptempo.",
            "stock_quantity / avg_daily_units", "count"),
        MetricDefinition(
            "sessions", "Sessies",
            "Aantal bezoeken (GA4) over de periode.",
            "SUM(fact_traffic_daily.sessions)", "count"),
        MetricDefinition(
            "conversion_rate", "Conversieratio",
            "Transacties gedeeld door sessies.",
            "SUM(transactions) / SUM(sessions) * 100", "pct"),
        MetricDefinition(
            "switch_probability", "Overstapkans",
            "Kans dat een klant overstapt van A-merk naar huismerk.",
            "internal_competition_scores.internal_switch_probability", "ratio"),
        MetricDefinition(
            "pcis", "Pricing Competition Impact Score",
            "Samengestelde score (0-100) voor concurrentiedruk per SKU.",
            "sku_competition_score.pcis_score", "count"),
        MetricDefinition(
            "confidence", "Betrouwbaarheid",
            "Modelvertrouwen in een uitkomst (0..1).",
            "model-specifiek", "ratio"),
    ]
}


def safe_div(numerator, denominator):
    """Deling die None teruggeeft i.p.v. te crashen op 0/None (§56 fail-safe)."""
    try:
        n = float(numerator or 0)
        d = float(denominator or 0)
        return n / d if d else None
    except (TypeError, ValueError):
        return None


def gross_margin(revenue, cost):
    return float(revenue or 0) - float(cost or 0)


def gross_margin_pct(revenue, cost):
    r = safe_div(gross_margin(revenue, cost), revenue)
    return r * 100 if r is not None else None


def asp(revenue, units):
    return safe_div(revenue, units)
