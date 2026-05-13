"""
Traffic → Promotieadvies Overlay.

Regels:
  IF search_demand hoog AND eigen_traffic laag AND margin hoog
    → marketing/promotion push

  IF traffic hoog AND conversie laag AND price_index hoog
    → prijs- of promotietest

  IF traffic hoog AND conversie hoog AND margin laag
    → beperk promoties

  IF nieuwe SKU AND search_demand hoog
    → launch promotion

  IF search_demand laag AND stock hoog
    → clearance overwegen
"""
from typing import Any


PROMOTIE_ACTIES = {
    "MARKETING_PUSH":       "Marketing- of advertentiepush",
    "PRICE_PROMOTION_TEST": "Prijs- of promotietest",
    "LIMIT_PROMOTIONS":     "Beperk actieve promoties",
    "LAUNCH_PROMOTION":     "Launch-promotie activeren",
    "CLEARANCE_PROMOTION":  "Clearance overwegen",
    "SEO_SEA_PUSH":         "SEO/SEA-investering",
    "NO_ACTION":            "Geen promotie-actie nodig",
    "MONITOR":              "Blijf monitoren",
}


def apply_traffic_to_promotion_advice(
    dss: float,
    chs: float,
    tos: float,
    crs: float,
    sgs: float,
    sessions: int,
    margin_pct: float,
    stock_quantity: int,
    price_index: float,
    reason_code: str,
    is_new_sku: bool = False,
) -> dict:
    """
    Bepaalt promotieadvies op basis van traffic intelligence.

    Returns: { actie, actie_nl, prioriteit, toelichting }
    """
    # Scenario 1: hoge search demand + lage eigen traffic + hoge marge
    if dss >= 0.60 and sessions < 800 and margin_pct >= 0.25:
        actie = "SEO_SEA_PUSH" if sgs >= 0.55 else "MARKETING_PUSH"
        prioriteit = "hoog"
        toelichting = (
            f"Extern zoekvolume hoog (DSS {round(dss*100)}%) maar eigen traffic laag ({sessions} sess/mnd). "
            "Investeer in SEO, SEA of contentmarketing."
        )
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": prioriteit, "toelichting": toelichting}

    # Scenario 2: nieuwe SKU + hoge zoekvraag
    if is_new_sku and dss >= 0.55:
        actie = "LAUNCH_PROMOTION"
        toelichting = f"Nieuw product met veelbelovende zoekvraag (DSS {round(dss*100)}%). Launch-promotie aanbevolen."
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": "hoog", "toelichting": toelichting}

    # Scenario 3: traffic hoog + conversie laag + prijs hoog
    if sessions >= 1000 and chs < 0.40 and price_index > 1.05:
        actie = "PRICE_PROMOTION_TEST"
        toelichting = (
            f"Hoge traffic ({sessions} sess/mnd) maar lage conversie (CHS {round(chs*100)}%). "
            f"Prijsindex {round(price_index, 2)} ligt boven concurrentieniveau. Test promotie of prijsverlaging."
        )
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": "hoog", "toelichting": toelichting}

    # Scenario 4: clearance — lage demand + hoge voorraad
    if dss < 0.30 and stock_quantity > 200:
        actie = "CLEARANCE_PROMOTION"
        toelichting = f"Lage externe vraag (DSS {round(dss*100)}%) + hoge voorraad ({stock_quantity} stuks). Clearance overwegen."
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": "gemiddeld", "toelichting": toelichting}

    # Scenario 5: hoge traffic + hoge conversie + lage marge
    if sessions >= 800 and chs >= 0.65 and margin_pct < 0.15:
        actie = "LIMIT_PROMOTIONS"
        toelichting = (
            f"Hoge traffic en goede conversie maar krappe marge ({round(margin_pct*100)}%). "
            "Beperk verdere promoties; bescherm marge."
        )
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": "gemiddeld", "toelichting": toelichting}

    if tos >= 0.60:
        actie = "MARKETING_PUSH"
        toelichting = f"Hoge traffic opportunity (TOS {round(tos*100)}%). Extra marketinginzet aanbevolen."
        return {"actie": actie, "actie_nl": PROMOTIE_ACTIES[actie], "prioriteit": "gemiddeld", "toelichting": toelichting}

    return {
        "actie": "NO_ACTION",
        "actie_nl": PROMOTIE_ACTIES["NO_ACTION"],
        "prioriteit": "laag",
        "toelichting": "Traffic en conversie binnen normale bandbreedte. Geen actieve promotie nodig.",
    }
