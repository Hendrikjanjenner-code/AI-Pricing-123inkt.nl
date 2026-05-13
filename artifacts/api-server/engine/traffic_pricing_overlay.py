"""
Traffic → Prijsadvies Overlay.

Regels:
  IF traffic stabiel AND conversie daalt AND PCIS hoog
    → concurrentie-/prijssignaal versterken

  IF traffic hoog AND conversie hoog AND elasticiteit laag
    → prijsverhoging testen

  IF search_demand hoog AND eigen traffic laag
    → niet automatisch prijs verlagen; eerst traffic opportunity tonen

  IF conversie daalt AND CSRS concurrent hoog AND competitor_price lager
    → prijsdruk serieus nemen

  IF traffic laag AND conversie hoog AND demand laag
    → prijsstabiliteit handhaven
"""
from typing import Any


PRICING_ACTIES = {
    "TEST_PRICE_INCREASE":    "Prijsverhoging testen",
    "MATCH_COMPETITOR_PRICE": "Concurrentieprijs volgen",
    "DEFEND_PRICE":           "Huidige prijs verdedigen",
    "PRICE_REDUCTION":        "Prijsverlaging overwegen",
    "STABILIZE_PRICE":        "Prijsstabiliteit handhaven",
    "MONITOR_COMPETITOR":     "Concurrentie nauwlettend monitoren",
    "NO_ACTION":              "Geen prijsactie nodig",
}


def apply_traffic_to_pricing_advice(
    dss: float,
    chs: float,
    crs: float,
    traffic_growth: float,
    conversion_trend: float,
    sessions: int,
    price_index: float,
    pcis_score: float,
    own_elasticity: float,
    csrs_score: float,
) -> dict:
    """
    Bepaalt prijsadvies op basis van traffic intelligence + PCIS/elasticiteit.

    Returns: { actie, actie_nl, prioriteit, toelichting, signaalsterkte }
    """
    # Scenario 1: hoge traffic + hoge conversie + lage elasticiteit → prijsverhoging
    if sessions >= 800 and chs >= 0.65 and (own_elasticity or -2.0) > -1.0:
        actie = "TEST_PRICE_INCREASE"
        toelichting = (
            f"Hoge traffic ({sessions} sess/mnd) + gezonde conversie (CHS {round(chs*100)}%) "
            f"+ lage elasticiteit ({round(own_elasticity or -1, 2)}). "
            "Prijsverhoging van 3–5% testen zonder significant omzetverlies."
        )
        return {"actie": actie, "actie_nl": PRICING_ACTIES[actie], "prioriteit": "hoog", "toelichting": toelichting, "signaalsterkte": round(chs * 0.6 + (1 + (own_elasticity or -1)) * 0.4, 2)}

    # Scenario 2: conversie daalt + CSRS hoog + concurrent goedkoper
    if conversion_trend < -0.15 and csrs_score >= 0.65 and price_index > 1.05:
        actie = "MATCH_COMPETITOR_PRICE"
        toelichting = (
            f"Conversie daalt ({round(conversion_trend*100, 1)}%) terwijl concurrent betrouwbaar en goedkoper is "
            f"(CSRS {round(csrs_score*100)}%, prijsindex {round(price_index, 2)}). "
            "Concurrentieprijs volgen aanbevolen."
        )
        return {"actie": actie, "actie_nl": PRICING_ACTIES[actie], "prioriteit": "hoog", "toelichting": toelichting, "signaalsterkte": round(crs, 2)}

    # Scenario 3: traffic stabiel + conversie daalt + PCIS hoog
    if abs(traffic_growth) < 0.10 and conversion_trend < -0.10 and pcis_score >= 0.60:
        actie = "MONITOR_COMPETITOR"
        toelichting = (
            f"Traffic stabiel maar conversie daalt ({round(conversion_trend*100, 1)}%) "
            f"onder hoge concurrentiedruk (PCIS {round(pcis_score*100)}%). "
            "Monitor concurrentieprijzen nauwlettend."
        )
        return {"actie": actie, "actie_nl": PRICING_ACTIES[actie], "prioriteit": "hoog", "toelichting": toelichting, "signaalsterkte": round(crs, 2)}

    # Scenario 4: hoge search demand + lage eigen traffic → geen automatische verlaging
    if dss >= 0.60 and sessions < 600:
        actie = "STABILIZE_PRICE"
        toelichting = (
            f"Hoge externe vraag (DSS {round(dss*100)}%) maar lage eigen traffic. "
            "Prijs niet verlagen; focus eerst op traffic via SEO/SEA."
        )
        return {"actie": actie, "actie_nl": PRICING_ACTIES[actie], "prioriteit": "gemiddeld", "toelichting": toelichting, "signaalsterkte": round(dss, 2)}

    # Scenario 5: lage traffic + lage demand → prijsstabiliteit
    if sessions < 300 and dss < 0.35:
        actie = "STABILIZE_PRICE"
        toelichting = "Lage traffic en vraag. Handhaven huidige prijs; agressieve actie niet zinvol."
        return {"actie": actie, "actie_nl": PRICING_ACTIES[actie], "prioriteit": "laag", "toelichting": toelichting, "signaalsterkte": 0.20}

    return {
        "actie": "NO_ACTION",
        "actie_nl": PRICING_ACTIES["NO_ACTION"],
        "prioriteit": "laag",
        "toelichting": "Geen sterk pricing-signaal vanuit traffic. Huidige strategie handhaven.",
        "signaalsterkte": 0.30,
    }
