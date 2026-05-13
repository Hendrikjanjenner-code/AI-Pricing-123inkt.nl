"""
Hybrid Pricing BCG — combineert interne waarde, externe concurrentiedruk,
pricing power en huismerkpotentie tot een pricingstrategie-classificatie.

Classificaties:
  PRICING_POWER_STAR       hoge marge + lage druk + hoge pricing power
  DEFENSIVE_CASH_COW       hoge omzet/marge + hoge concurrentiedruk
  PRIVATE_LABEL_STAR       hoge huismerkmarge + hoge substitutiepotentie
  EXPERIMENTAL_QUESTION_MARK hoge groeipotentie + lage databetrouwbaarheid
  LOW_PRIORITY_DOG         lage waarde + lage groei

Bijbehorende pricingstrategieën:
  PROTECT_MARGIN           bescherm huidige marge
  DEFEND_MARKET_POSITION   defensieve pricing vs concurrenten
  PRIVATE_LABEL_PUSH       stuur traffic naar huismerk
  EXPERIMENT_PRICE_INCREASE elasticiteitexperiment
  COMPETITIVE_PRICE_MATCH  volg concurrentprijs
  LOW_PRIORITY_AUTOMATION  minimale aandacht
"""
from typing import Any

THRESHOLD_HIGH = 0.60
THRESHOLD_LOW = 0.40


def classify_hybrid_bcg(
    ibss: float,
    gps: float,
    css_external: float,
    mos: float,
    pricing_power: float,
    plsv: float,
    confidence: float,
    is_private_label: bool,
) -> tuple[str, str, str]:
    """
    Bepaalt hybride BCG-classificatie, pricingstrategie en prioriteit.

    Returns:
        (hybrid_class, pricing_strategy, strategic_priority)
    """
    # PRIVATE_LABEL_STAR: huismerk met hoge marge en substitutiepotentie
    if is_private_label and plsv >= THRESHOLD_HIGH:
        return ("PRIVATE_LABEL_STAR", "PRIVATE_LABEL_PUSH", "hoog")

    # PRICING_POWER_STAR: hoge interne kracht + lage externe druk + hoge pricing power
    if ibss >= THRESHOLD_HIGH and css_external >= THRESHOLD_HIGH and pricing_power >= THRESHOLD_HIGH:
        return ("PRICING_POWER_STAR", "PROTECT_MARGIN", "hoog")

    # DEFENSIVE_CASH_COW: hoog IBSS maar veel concurrentiedruk
    if ibss >= THRESHOLD_HIGH and css_external < THRESHOLD_HIGH:
        return ("DEFENSIVE_CASH_COW", "DEFEND_MARKET_POSITION", "hoog")

    # EXPERIMENTAL_QUESTION_MARK: hoge groei maar lage betrouwbaarheid
    if gps >= THRESHOLD_HIGH and confidence < 0.60:
        return ("EXPERIMENTAL_QUESTION_MARK", "EXPERIMENT_PRICE_INCREASE", "gemiddeld")

    # Generieke vraagtteken: hoge MOS maar zwakke interne positie
    if mos >= THRESHOLD_HIGH and ibss < THRESHOLD_HIGH:
        return ("EXPERIMENTAL_QUESTION_MARK", "COMPETITIVE_PRICE_MATCH", "gemiddeld")

    # LOW_PRIORITY_DOG
    if ibss < THRESHOLD_LOW and gps < THRESHOLD_LOW:
        return ("LOW_PRIORITY_DOG", "LOW_PRIORITY_AUTOMATION", "laag")

    # Standaard: volg concurrentprijs als er weinig pricing power is
    if pricing_power < THRESHOLD_HIGH:
        return ("DEFENSIVE_CASH_COW", "COMPETITIVE_PRICE_MATCH", "gemiddeld")

    return ("PRICING_POWER_STAR", "PROTECT_MARGIN", "gemiddeld")


def get_hybrid_bcg_nl(classification: str) -> str:
    labels = {
        "PRICING_POWER_STAR":          "Pricing Power Ster",
        "DEFENSIVE_CASH_COW":          "Defensieve Cash Cow",
        "PRIVATE_LABEL_STAR":          "Huismerk Ster",
        "EXPERIMENTAL_QUESTION_MARK":  "Experimenteel Vraagteken",
        "LOW_PRIORITY_DOG":            "Lage Prioriteit Dog",
    }
    return labels.get(classification, classification)


def get_pricing_strategy_nl(strategy: str) -> str:
    labels = {
        "PROTECT_MARGIN":           "Bescherm Marge",
        "DEFEND_MARKET_POSITION":   "Verdedig Marktpositie",
        "PRIVATE_LABEL_PUSH":       "Huismerk Promoten",
        "EXPERIMENT_PRICE_INCREASE": "Prijsverhoging Testen",
        "COMPETITIVE_PRICE_MATCH":  "Concurrentieprijs Volgen",
        "LOW_PRIORITY_AUTOMATION":  "Automatiseer (Laag Prioriteit)",
    }
    return labels.get(strategy, strategy)


BCG_KLEUR: dict[str, str] = {
    "PRICING_POWER_STAR":          "#22c55e",
    "DEFENSIVE_CASH_COW":          "#f59e0b",
    "PRIVATE_LABEL_STAR":          "#8b5cf6",
    "EXPERIMENTAL_QUESTION_MARK":  "#3b82f6",
    "LOW_PRIORITY_DOG":            "#94a3b8",
    "INTERNAL_STAR":               "#22c55e",
    "INTERNAL_CASH_COW":           "#f59e0b",
    "INTERNAL_QUESTION_MARK":      "#3b82f6",
    "INTERNAL_DOG":                "#94a3b8",
    "EXTERNAL_STAR":               "#10b981",
    "EXTERNAL_CASH_COW":           "#f97316",
    "EXTERNAL_QUESTION_MARK":      "#6366f1",
    "EXTERNAL_DOG":                "#64748b",
}
