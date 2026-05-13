"""
Growth Potential Score (GPS) — onderdeel van BCG Intelligence Engine.

Berekent groeipotentieel per SKU op basis van:
- omzetgroei (30d vs 60d)
- volumegroei
- verkoopsnelheid (velocity)
- margetrend
"""
from datetime import date, timedelta
from typing import Any


def calculate_growth_potential(
    sales_data: list[dict[str, Any]],
    today: date | None = None,
) -> float:
    """
    Berekent GPS (Growth Potential Score) in bereik 0.00–1.00.

    Args:
        sales_data: lijst van dicts met keys: date, units_sold, revenue, margin
        today:      referentiedatum (standaard: date.today())

    Returns:
        GPS score 0.00–1.00
    """
    if today is None:
        today = date.today()

    if not sales_data:
        return 0.30

    cutoff_30 = today - timedelta(days=30)
    cutoff_60 = today - timedelta(days=60)

    recent = [s for s in sales_data if s.get("date", date.min) >= cutoff_30]
    previous = [s for s in sales_data if cutoff_60 <= s.get("date", date.min) < cutoff_30]

    # Omzetgroei
    recent_rev = sum(float(s.get("revenue") or 0) for s in recent)
    prev_rev = sum(float(s.get("revenue") or 0) for s in previous)
    rev_growth = (recent_rev - prev_rev) / prev_rev if prev_rev > 0 else 0.05

    # Volumegroei
    recent_vol = sum(int(s.get("units_sold") or 0) for s in recent)
    prev_vol = sum(int(s.get("units_sold") or 0) for s in previous)
    vol_growth = (recent_vol - prev_vol) / prev_vol if prev_vol > 0 else 0.05

    # Margetrend
    recent_margin = sum(float(s.get("margin") or 0) for s in recent)
    prev_margin = sum(float(s.get("margin") or 0) for s in previous)
    margin_growth = (recent_margin - prev_margin) / abs(prev_margin) if prev_margin != 0 else 0.0

    # Verkoopsnelheid (eenheden per dag, max ~100/dag = perfect)
    velocity_score = min(1.0, recent_vol / (30 * 100)) if recent_vol > 0 else 0.05

    # Normaliseer groei naar 0–1 bereik (basiswaarde 0.5 = geen groei)
    rev_score = min(1.0, max(0.0, 0.5 + rev_growth * 0.5))
    vol_score = min(1.0, max(0.0, 0.5 + vol_growth * 0.5))
    margin_score = min(1.0, max(0.0, 0.5 + margin_growth * 0.3))

    gps = (
        rev_score    * 0.35
        + vol_score    * 0.30
        + margin_score * 0.20
        + velocity_score * 0.15
    )

    return round(min(1.0, max(0.0, gps)), 4)
