"""
Traffic → BCG Overlay — past traffic-intelligence toe op BCG-scores.

Integratie:
  Internal BCG:
    - traffic_growth verhoogt GPS
    - margin_per_visitor verhoogt IBSS
    - dalende conversie verlaagt confidence

  External BCG:
    - search_volume en trend_index verhogen MOS
    - search_gap_score verhoogt Question Mark kans

  Hybrid BCG:
    - hoge demand + lage concurrentiedruk = pricing power
    - hoge demand + hoge concurrentiedruk = defensieve pricing
    - hoge search_gap = marketing/promotie opportunity
"""
from typing import Any


def apply_traffic_to_bcg(
    bcg_record: Any,
    traffic_intel: Any,
) -> dict:
    """
    Berekent traffic-gecorrigeerde BCG-scores.

    Returns dict met aangepaste scores en eventuele classificatiewijziging.
    """
    if not bcg_record or not traffic_intel:
        return {}

    ibss = float(bcg_record.ibss_score or 0)
    gps = float(bcg_record.gps_score or 0)
    css_ext = float(bcg_record.css_external_score or 0)
    mos = float(bcg_record.mos_score or 0)
    pps = float(bcg_record.pricing_power_score or 0)
    confidence = float(bcg_record.confidence_score or 0.8)

    dss = float(traffic_intel.demand_signal_score or 0)
    chs = float(traffic_intel.conversion_health_score or 0)
    tos = float(traffic_intel.traffic_opportunity_score or 0)
    crs = float(traffic_intel.conversion_risk_score or 0)
    sgs = float(traffic_intel.search_gap_score or 0)
    tg = float(traffic_intel.traffic_growth or 0)
    ct = float(traffic_intel.conversion_trend or 0)

    # ── GPS aanpassing ─────────────────────────────────────────────────────────
    # Traffic groei verhoogt GPS
    gps_adjusted = min(1.0, max(0.0, gps + tg * 0.15))

    # ── IBSS aanpassing ────────────────────────────────────────────────────────
    # Hoge demand (DSS) en gezonde conversie (CHS) versterken interne positie
    ibss_adjusted = min(1.0, max(0.0, ibss + dss * 0.08 + chs * 0.05))

    # ── MOS aanpassing ─────────────────────────────────────────────────────────
    # Hoge externe vraag vergroot marktkans
    mos_adjusted = min(1.0, max(0.0, mos + dss * 0.12 + sgs * 0.08))

    # ── Confidence aanpassing ──────────────────────────────────────────────────
    # Dalende conversie = minder zeker van classificatie
    confidence_adjusted = min(1.0, max(0.2, confidence - crs * 0.10))

    # ── CSS aanpassing ─────────────────────────────────────────────────────────
    # Hoge search gap = zwakker in markt
    css_adjusted = min(1.0, max(0.0, css_ext - sgs * 0.05))

    # ── Pricing power aanpassing ───────────────────────────────────────────────
    # Hoge demand + lage CRS = meer pricing power
    pps_adjusted = min(1.0, max(0.0, pps + dss * 0.08 - crs * 0.10))

    # ── Traffic-BCG signaal ────────────────────────────────────────────────────
    reason = traffic_intel.reason_code or "NO_SIGNAL"
    traffic_bcg_impact = "neutraal"
    if reason in ("PRICING_POWER_FROM_DEMAND",):
        traffic_bcg_impact = "positief"
    elif reason in ("CONVERSION_DROP_DETECTED", "TRAFFIC_DROP_DETECTED"):
        traffic_bcg_impact = "negatief"
    elif reason in ("SEARCH_DEMAND_HIGH_LOW_TRAFFIC", "TRAFFIC_OPPORTUNITY_HIGH"):
        traffic_bcg_impact = "kans"

    return {
        "ibss_adjusted":        round(ibss_adjusted, 4),
        "gps_adjusted":         round(gps_adjusted, 4),
        "css_adjusted":         round(css_adjusted, 4),
        "mos_adjusted":         round(mos_adjusted, 4),
        "pps_adjusted":         round(pps_adjusted, 4),
        "confidence_adjusted":  round(confidence_adjusted, 4),
        "traffic_bcg_impact":   traffic_bcg_impact,
        "traffic_signal":       reason,
    }
