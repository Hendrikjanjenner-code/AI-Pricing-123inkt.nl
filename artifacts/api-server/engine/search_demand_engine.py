"""
Search Demand Engine — berekent externe zoekvraag scores per SKU/categorie.

Scores:
  external_demand_score     — totale externe vraag (0–1)
  search_trend_score        — trendrichting (0–1)
  keyword_opportunity_score — ROI-potentie van keywords (0–1)
  own_visibility_score      — eigen zichtbaarheid in zoekresultaten (0–1)
  search_gap_score          — verschil marktvraag vs eigen zichtbaarheid (0–1)
"""
from typing import Any


def calculate_external_demand_score(
    search_volume: int,
    trend_index: float,
    competition_level: float,
) -> float:
    """
    EDS — totale externe vraag.

    Hoog zoekvolume + stijgende trend + niet te competitief = hoge score.
    """
    vol_score    = min(1.0, search_volume / 10_000)
    trend_score  = min(1.0, max(0.0, trend_index))
    comp_score   = max(0.0, 1.0 - competition_level * 0.5)

    eds = (
        vol_score   * 0.50
        + trend_score * 0.30
        + comp_score  * 0.20
    )
    return round(min(1.0, max(0.0, eds)), 4)


def calculate_search_trend_score(trend_index: float, historical_avg: float = 0.50) -> float:
    """
    STS — hoe stijgt de zoekvraag t.o.v. historisch gemiddelde?

    trend_index 0–1 (bijv. Google Trends normalisatie).
    """
    if historical_avg <= 0:
        return trend_index
    growth = (trend_index - historical_avg) / historical_avg
    score = min(1.0, max(0.0, 0.5 + growth))
    return round(score, 4)


def calculate_keyword_opportunity_score(
    search_volume: int,
    competition_level: float,
    cpc_estimate: float,
    own_position: float,
) -> float:
    """
    KOS — ROI-potentie: hoog volume, lage competitie, hoge CPC, slechte eigen positie.

    Slechte eigen positie = veel ruimte om te winnen.
    """
    vol_score  = min(1.0, search_volume / 8_000)
    comp_score = max(0.0, 1.0 - competition_level)
    cpc_score  = min(1.0, cpc_estimate / 3.0)   # CPC > €3 = hoge waarde
    pos_gap    = min(1.0, max(0.0, (own_position - 1.0) / 10.0)) if own_position else 0.5

    kos = (
        vol_score  * 0.35
        + comp_score * 0.25
        + cpc_score  * 0.20
        + pos_gap    * 0.20
    )
    return round(min(1.0, max(0.0, kos)), 4)


def calculate_own_visibility_score(
    impressions: int,
    clicks: int,
    ctr: float,
    average_position: float,
    search_volume: int,
) -> float:
    """
    OVS — hoe goed is eigen zichtbaarheid?

    Hoge score = veel eigen vertoningen + klikken + goede positie.
    """
    if search_volume <= 0:
        return 0.0

    imp_share  = min(1.0, impressions / max(search_volume, 1))
    click_share = min(1.0, clicks / max(search_volume * 0.05, 1))
    ctr_score   = min(1.0, (ctr or 0) / 0.10)   # CTR > 10% = uitstekend
    pos_score   = max(0.0, 1.0 - (average_position or 10) / 10.0) if average_position else 0.0

    ovs = (
        imp_share   * 0.30
        + click_share * 0.25
        + ctr_score   * 0.25
        + pos_score   * 0.20
    )
    return round(min(1.0, max(0.0, ovs)), 4)


def calculate_search_gap_score(
    external_demand_score: float,
    own_visibility_score: float,
) -> float:
    """
    SGS — hoog externe vraag + lage eigen zichtbaarheid = grote gap (kans).
    """
    gap = external_demand_score * (1.0 - own_visibility_score)
    return round(min(1.0, max(0.0, gap)), 4)


def aggregate_sku_search_demand(search_rows: list[Any]) -> dict:
    """
    Aggregeert meerdere keyword-rijen naar één SKU-samenvatting.
    """
    if not search_rows:
        return {
            "total_volume": 0,
            "avg_trend": 0.30,
            "avg_competition": 0.50,
            "total_impressions": 0,
            "total_clicks": 0,
            "avg_ctr": 0.0,
            "avg_position": 10.0,
            "avg_cpc": 0.0,
        }

    n = len(search_rows)
    return {
        "total_volume":    sum(r.search_volume or 0 for r in search_rows),
        "avg_trend":       sum(r.trend_index or 0 for r in search_rows) / n,
        "avg_competition": sum(r.competition_level or 0 for r in search_rows) / n,
        "total_impressions": sum(r.impressions or 0 for r in search_rows),
        "total_clicks":    sum(r.clicks or 0 for r in search_rows),
        "avg_ctr":         sum(r.ctr or 0 for r in search_rows) / n,
        "avg_position":    sum(r.average_position or 10 for r in search_rows) / n,
        "avg_cpc":         float(sum(float(r.cpc_estimate or 0) for r in search_rows) / n),
    }
