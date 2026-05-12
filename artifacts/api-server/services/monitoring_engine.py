"""
Competitor Monitoring Engine — Module 3
Monitort concurrentieprijzen, voorraad en leverbetrouwbaarheid.
Genereert alerts en berekent CSRS/CSS trends.
"""
import statistics
from datetime import date, datetime, timedelta
from typing import Optional

# ── Alert types ──────────────────────────────────────────────────────────────
COMPETITOR_PRICE_DROPPED = "COMPETITOR_PRICE_DROPPED"
COMPETITOR_PRICE_INCREASED = "COMPETITOR_PRICE_INCREASED"
LOW_PRICE_LOW_STOCK_RELIABILITY = "LOW_PRICE_LOW_STOCK_RELIABILITY"
COMPETITOR_OUT_OF_STOCK = "COMPETITOR_OUT_OF_STOCK"
COMPETITOR_BACK_IN_STOCK = "COMPETITOR_BACK_IN_STOCK"
COMPETITOR_LISTING_DISAPPEARED = "COMPETITOR_LISTING_DISAPPEARED"
COMPETITOR_NEW_ENTRY = "COMPETITOR_NEW_ENTRY"
COMPETITOR_PRICE_OUTLIER = "COMPETITOR_PRICE_OUTLIER"
COMPETITOR_DELIVERY_WORSENED = "COMPETITOR_DELIVERY_WORSENED"
COMPETITOR_STOCK_RELIABILITY_DECLINED = "COMPETITOR_STOCK_RELIABILITY_DECLINED"

# ── Drempelwaarden ───────────────────────────────────────────────────────────
PRICE_DROP_THRESHOLD_PCT = 0.03       # >3% daling → alert
PRICE_INCREASE_THRESHOLD_PCT = 0.03   # >3% stijging → alert
OUTLIER_STD_FACTOR = 2.0              # meer dan 2 std van mediaan → outlier
LOW_CSRS_THRESHOLD = 0.45             # CSRS < 0.45 = lage betrouwbaarheid


def calculate_price_trend(prices: list[float]) -> dict:
    """
    Bereken prijstrend over een reeks historische prijzen.
    Geeft richting, gemiddelde verandering per periode en volatiliteit terug.
    """
    if len(prices) < 2:
        return {"richting": "stabiel", "gem_verandering_pct": 0.0, "volatiliteit": 0.0}

    veranderingen = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    gem = statistics.mean(veranderingen)

    richting = "stabiel"
    if gem < -PRICE_DROP_THRESHOLD_PCT:
        richting = "dalend"
    elif gem > PRICE_INCREASE_THRESHOLD_PCT:
        richting = "stijgend"

    return {
        "richting": richting,
        "gem_verandering_pct": round(gem * 100, 2),
        "volatiliteit": round(calculate_price_volatility(prices), 4),
    }


def calculate_price_volatility(prices: list[float]) -> float:
    """Standaarddeviatie van relatieve prijsveranderingen."""
    if len(prices) < 2:
        return 0.0
    veranderingen = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    if len(veranderingen) < 2:
        return abs(veranderingen[0]) if veranderingen else 0.0
    return statistics.stdev(veranderingen)


def calculate_csrs(
    availability_rate: float,
    delivery_speed_score: float,
    stock_stability_score: float,
    listing_consistency_score: float,
) -> float:
    """
    Competitor Stock Reliability Score:
    CSRS = 0.40 * availability_rate
         + 0.25 * delivery_speed_score
         + 0.20 * stock_stability_score
         + 0.15 * listing_consistency_score
    """
    csrs = (
        0.40 * availability_rate
        + 0.25 * delivery_speed_score
        + 0.20 * stock_stability_score
        + 0.15 * listing_consistency_score
    )
    return round(min(max(csrs, 0.0), 1.0), 4)


def calculate_css(
    price_deviation_score: float,
    price_volatility_score: float,
    competitor_type_score: float,
    delivery_reliability_score: float,
) -> float:
    """
    Competitor Sustainability Score:
    Hogere score = betrouwbaardere concurrent voor langdurige prijsreferentie.
    """
    css = (
        0.30 * (1.0 - price_deviation_score)
        + 0.25 * (1.0 - price_volatility_score)
        + 0.25 * competitor_type_score
        + 0.20 * delivery_reliability_score
    )
    return round(min(max(css, 0.0), 1.0), 4)


def detect_price_outlier(
    price: float,
    all_prices: list[float],
    std_factor: float = OUTLIER_STD_FACTOR,
) -> bool:
    """
    Detecteer of een prijs statistisch afwijkend is t.o.v. de markt.
    Gebruikt mediaan + standaarddeviatie.
    """
    if len(all_prices) < 3:
        return False
    med = statistics.median(all_prices)
    try:
        std = statistics.stdev(all_prices)
    except statistics.StatisticsError:
        return False
    if std == 0:
        return False
    return abs(price - med) > std_factor * std


def detect_listing_disappearance(
    current_urls: set[str],
    previous_urls: set[str],
) -> set[str]:
    """Geeft URLs terug die in de vorige meting aanwezig waren maar nu niet meer."""
    return previous_urls - current_urls


def detect_new_competitor_offer(
    current_competitor_ids: set[int],
    previous_competitor_ids: set[int],
) -> set[int]:
    """Geeft concurrent-IDs terug die nieuw zijn ten opzichte van vorige meting."""
    return current_competitor_ids - previous_competitor_ids


def generate_monitoring_alerts(
    sku_id: str,
    current_offers: list[dict],
    previous_offers: list[dict],
    csrs_scores: dict[int, float],
) -> list[dict]:
    """
    Genereer monitoring-alerts voor een SKU.
    Vergelijkt huidige met vorige concurrent-aanbiedingen.

    current_offers/previous_offers: lijst van {competitor_id, price, in_stock, delivery_days, product_url}
    csrs_scores: {competitor_id: csrs_score}
    """
    alerts = []
    vandaag = date.today()

    prev_map = {o["competitor_id"]: o for o in previous_offers}
    curr_map = {o["competitor_id"]: o for o in current_offers}

    all_prices = [o["price"] for o in current_offers if o.get("price")]

    for comp_id, curr in curr_map.items():
        prev = prev_map.get(comp_id)
        curr_price = curr.get("price")
        csrs = csrs_scores.get(comp_id, 1.0)

        if prev:
            prev_price = prev.get("price")

            # Prijsdaling
            if curr_price and prev_price and curr_price < prev_price * (1 - PRICE_DROP_THRESHOLD_PCT):
                pct = round((prev_price - curr_price) / prev_price * 100, 1)
                severity = "hoog" if pct > 10 else "middel"
                alerts.append({
                    "own_sku_id": sku_id,
                    "competitor_id": comp_id,
                    "alert_type": COMPETITOR_PRICE_DROPPED,
                    "severity": severity,
                    "message": f"Prijs gedaald met {pct}% (van €{prev_price:.2f} naar €{curr_price:.2f})",
                    "date": vandaag,
                })

            # Lage prijs + lage CSRS
            if curr_price and prev_price and curr_price < prev_price and csrs < LOW_CSRS_THRESHOLD:
                alerts.append({
                    "own_sku_id": sku_id,
                    "competitor_id": comp_id,
                    "alert_type": LOW_PRICE_LOW_STOCK_RELIABILITY,
                    "severity": "middel",
                    "message": f"Lage prijs €{curr_price:.2f} maar CSRS laag ({csrs:.2f}) — niet volgen",
                    "date": vandaag,
                })

            # Voorraadstatus
            if not curr.get("in_stock") and prev.get("in_stock"):
                alerts.append({
                    "own_sku_id": sku_id,
                    "competitor_id": comp_id,
                    "alert_type": COMPETITOR_OUT_OF_STOCK,
                    "severity": "laag",
                    "message": "Concurrent is uit voorraad gegaan",
                    "date": vandaag,
                })
            elif curr.get("in_stock") and not prev.get("in_stock"):
                alerts.append({
                    "own_sku_id": sku_id,
                    "competitor_id": comp_id,
                    "alert_type": COMPETITOR_BACK_IN_STOCK,
                    "severity": "laag",
                    "message": "Concurrent is terug op voorraad",
                    "date": vandaag,
                })

            # Levering verslechterd
            if curr.get("delivery_days") and prev.get("delivery_days"):
                if curr["delivery_days"] > prev["delivery_days"] + 1:
                    alerts.append({
                        "own_sku_id": sku_id,
                        "competitor_id": comp_id,
                        "alert_type": COMPETITOR_DELIVERY_WORSENED,
                        "severity": "laag",
                        "message": f"Levertijd gestegen van {prev['delivery_days']} naar {curr['delivery_days']} dagen",
                        "date": vandaag,
                    })

        else:
            # Nieuwe concurrent
            alerts.append({
                "own_sku_id": sku_id,
                "competitor_id": comp_id,
                "alert_type": COMPETITOR_NEW_ENTRY,
                "severity": "middel",
                "message": f"Nieuwe concurrent gevonden met prijs €{curr_price:.2f}" if curr_price else "Nieuwe concurrent gedetecteerd",
                "date": vandaag,
            })

        # Outlier
        if curr_price and detect_price_outlier(curr_price, all_prices):
            alerts.append({
                "own_sku_id": sku_id,
                "competitor_id": comp_id,
                "alert_type": COMPETITOR_PRICE_OUTLIER,
                "severity": "middel",
                "message": f"Prijs €{curr_price:.2f} is statistisch afwijkend van de markt",
                "date": vandaag,
            })

    # Verdwenen concurrenten
    for comp_id in set(prev_map.keys()) - set(curr_map.keys()):
        prev = prev_map[comp_id]
        alerts.append({
            "own_sku_id": sku_id,
            "competitor_id": comp_id,
            "alert_type": COMPETITOR_LISTING_DISAPPEARED,
            "severity": "laag",
            "message": "Concurrent-aanbieding verdwenen uit overzicht",
            "date": vandaag,
        })

    return alerts


def save_alerts(db, alerts: list[dict]):
    """Sla gegenereerde alerts op in de database."""
    from models import FactMonitoringAlert
    for a in alerts:
        record = FactMonitoringAlert(
            date=a["date"],
            own_sku_id=a.get("own_sku_id"),
            competitor_id=a.get("competitor_id"),
            alert_type=a["alert_type"],
            severity=a.get("severity", "laag"),
            message=a.get("message", ""),
            resolved=False,
        )
        db.add(record)
    db.commit()
