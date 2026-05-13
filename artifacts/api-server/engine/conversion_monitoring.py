"""
Conversion Monitoring — detecteert conversiedalingen en kansen.

Mogelijke oorzaken van conversiedaling:
  PRICE_TOO_HIGH         — prijs boven concurrentieniveau
  COMPETITOR_PRESSURE    — concurrent goedkoper met hoge CSRS
  STOCK_ISSUE            — voorraadprobleem / laag voorraad
  LOW_RELEVANCE          — lage zoekrelevantie / hoge bounce
  POOR_PROMOTION         — gebrekkige promotie-uitingen
  MARKET_INTEREST_DECLINE — marktinteresse daalt
  UNKNOWN                — onbekende oorzaak
"""
from typing import Any


SIGNAL_LABELS_NL = {
    "CONVERSION_DROP_DETECTED":      "Conversiedaling Gedetecteerd",
    "TRAFFIC_DROP_DETECTED":         "Trafficdaling Gedetecteerd",
    "SEARCH_DEMAND_HIGH_LOW_TRAFFIC": "Hoge Zoekvraag, Lage Eigen Traffic",
    "HIGH_TRAFFIC_LOW_CONVERSION":   "Hoge Traffic, Lage Conversie",
    "HIGH_SEARCH_GAP":               "Grote Search Gap",
    "TRAFFIC_OPPORTUNITY_HIGH":      "Hoge Traffic Opportunity",
    "PRICING_POWER_FROM_DEMAND":     "Pricing Power via Vraag",
    "PROMOTION_NEEDED_FOR_TRAFFIC":  "Promotie Nodig voor Traffic",
    "NEW_SKU_HIGH_SEARCH_DEMAND":    "Nieuw SKU — Hoge Zoekvraag",
    "CATEGORY_DEMAND_RISING":        "Categorievraag Stijgt",
    "CATEGORY_DEMAND_DECLINING":     "Categorievraag Daalt",
    "NO_SIGNAL":                     "Geen Signaal",
}

SIGNAL_PRIORITY: dict[str, str] = {
    "CONVERSION_DROP_DETECTED":      "hoog",
    "TRAFFIC_DROP_DETECTED":         "gemiddeld",
    "SEARCH_DEMAND_HIGH_LOW_TRAFFIC": "hoog",
    "HIGH_TRAFFIC_LOW_CONVERSION":   "hoog",
    "HIGH_SEARCH_GAP":               "gemiddeld",
    "TRAFFIC_OPPORTUNITY_HIGH":      "gemiddeld",
    "PRICING_POWER_FROM_DEMAND":     "hoog",
    "PROMOTION_NEEDED_FOR_TRAFFIC":  "gemiddeld",
    "NEW_SKU_HIGH_SEARCH_DEMAND":    "hoog",
    "CATEGORY_DEMAND_RISING":        "gemiddeld",
    "CATEGORY_DEMAND_DECLINING":     "gemiddeld",
    "NO_SIGNAL":                     "laag",
}

SIGNAL_KLEUR: dict[str, str] = {
    "CONVERSION_DROP_DETECTED":      "#ef4444",
    "TRAFFIC_DROP_DETECTED":         "#f97316",
    "SEARCH_DEMAND_HIGH_LOW_TRAFFIC": "#3b82f6",
    "HIGH_TRAFFIC_LOW_CONVERSION":   "#f59e0b",
    "HIGH_SEARCH_GAP":               "#6366f1",
    "TRAFFIC_OPPORTUNITY_HIGH":      "#22c55e",
    "PRICING_POWER_FROM_DEMAND":     "#10b981",
    "PROMOTION_NEEDED_FOR_TRAFFIC":  "#8b5cf6",
    "NEW_SKU_HIGH_SEARCH_DEMAND":    "#06b6d4",
    "CATEGORY_DEMAND_RISING":        "#22c55e",
    "CATEGORY_DEMAND_DECLINING":     "#94a3b8",
    "NO_SIGNAL":                     "#cbd5e1",
}

ADVIES_PER_SIGNAAL: dict[str, str] = {
    "CONVERSION_DROP_DETECTED":      "Prijs vergelijken met concurrenten. Overweeg prijs- of promotietest.",
    "TRAFFIC_DROP_DETECTED":         "Controleer SEO/SEA-positie en seizoenspatronen.",
    "SEARCH_DEMAND_HIGH_LOW_TRAFFIC": "SEO- of SEA-investering aanbevolen. Kijk naar contentstrategie.",
    "HIGH_TRAFFIC_LOW_CONVERSION":   "Optimaliseer landingspagina, prijs en beschikbaarheid.",
    "HIGH_SEARCH_GAP":               "Verhoog eigen zichtbaarheid via SEO of betaalde campagnes.",
    "TRAFFIC_OPPORTUNITY_HIGH":      "Verhoog traffic via gerichte marketing- of promotie-inzet.",
    "PRICING_POWER_FROM_DEMAND":     "Test geleidelijke prijsverhoging (3–5%) om marge te optimaliseren.",
    "PROMOTION_NEEDED_FOR_TRAFFIC":  "Launch marketing- of promotiepush om eigen traffic te activeren.",
    "NEW_SKU_HIGH_SEARCH_DEMAND":    "Launch-promotie aanbevolen om awareness en traffic te genereren.",
    "CATEGORY_DEMAND_RISING":        "Verhoog inkoopvolume en marketing voor deze categorie.",
    "CATEGORY_DEMAND_DECLINING":     "Wees voorzichtig met inkoop. Overweeg clearance voor overstock.",
    "NO_SIGNAL":                     "Geen actie vereist. Monitor regelmatig.",
}

MOGELIJKE_OORZAKEN: dict[str, list[str]] = {
    "CONVERSION_DROP_DETECTED": [
        "Concurrentieprijs lager",
        "Hoge CSRS concurrent",
        "Prijsindex gestegen",
        "Voorraadprobleem",
        "Lage promotie-effectiviteit",
    ],
    "HIGH_TRAFFIC_LOW_CONVERSION": [
        "Prijs te hoog",
        "Slecht productimage",
        "Voorraad onvoldoende",
        "Landingspagina niet relevant",
        "Hoge concurrentiedruk",
    ],
    "TRAFFIC_DROP_DETECTED": [
        "Lagere zoekrangschikking",
        "Seizoenseffect",
        "Concurrenten dominanter",
        "Campagne gestopt",
    ],
}


def classify_conversion_cause(
    price_index: float,
    csrs_score: float,
    stock_quantity: int,
    bounce_rate: float,
    conversion_trend: float,
) -> str:
    """Bepaalt de meest waarschijnlijke oorzaak van conversiedaling."""
    if price_index > 1.08:
        return "PRICE_TOO_HIGH"
    if csrs_score > 0.70:
        return "COMPETITOR_PRESSURE"
    if stock_quantity < 10:
        return "STOCK_ISSUE"
    if bounce_rate > 0.70:
        return "LOW_RELEVANCE"
    if conversion_trend < -0.30:
        return "MARKET_INTEREST_DECLINE"
    return "UNKNOWN"


def get_conversion_cause_nl(cause: str) -> str:
    labels = {
        "PRICE_TOO_HIGH":           "Prijs te hoog",
        "COMPETITOR_PRESSURE":      "Concurrentiedruk",
        "STOCK_ISSUE":              "Voorraadprobleem",
        "LOW_RELEVANCE":            "Lage relevantie",
        "POOR_PROMOTION":           "Slechte promotie",
        "MARKET_INTEREST_DECLINE":  "Marktinteresse daalt",
        "UNKNOWN":                  "Onbekende oorzaak",
    }
    return labels.get(cause, cause)
