"""
Multi-concurrent scenario-simulatie (§concurrentiebeeld compleet).

Simuleert een eigen prijswijziging waarbij per concurrent, op basis van diens
herkende strategie, een volgkans wordt geschat. Het resultaat toont het
verwachte effect op prijsindex, afzet, omzet en marge onder het gewogen
volg/niet-volg-scenario én de twee uiterste scenario's.

Alleen simulatie — voert NOOIT een prijswijziging uit.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models

# Volgkans per herkende strategie (kans dat de concurrent een eigen
# prijsverlaging binnen de horizon volgt; bij verhoging halveren we die kans).
FOLLOW_PROBABILITY: dict[str, float] = {
    "EVERYDAY_LOW_PRICE":  0.90,
    "PRICE_FOLLOWER":      0.85,
    "MARKET_SHARE_ATTACK": 0.80,
    "PRICE_LEADER":        0.40,
    "PROMOTION_DRIVEN":    0.35,
    "INVENTORY_CLEARANCE": 0.15,
    "MARGIN_PROTECTION":   0.10,
}
DEFAULT_FOLLOW_PROBABILITY = 0.50


def simulate_competitor_scenario(
    db: Session,
    sku_id: str,
    change_pct: float,
    assume_follow: Optional[list[str]] = None,
    assume_no_follow: Optional[list[str]] = None,
    shop_id: Optional[int] = None,
) -> dict:
    """
    Simuleer een eigen prijswijziging (fractie, bv. -0.05) met per-concurrent
    volgkansen. `assume_follow` / `assume_no_follow` overschrijven de
    strategie-gebaseerde volgkans (1.0 resp. 0.0) voor de genoemde concurrenten.
    shop_id bakent de scope af; standaard wordt de shop van het product gebruikt.
    """
    if change_pct is None or abs(change_pct) > 0.5:
        raise HTTPException(status_code=400, detail="change_pct moet tussen -0.5 en 0.5 liggen")

    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} niet gevonden")
    # Shop-scope: gebruik de shop van het product (of de meegegeven shop_id indien opgegeven)
    sid = shop_id if shop_id is not None else (product.shop_id or 1)
    own_price = float(product.current_price) if product.current_price else None
    if not own_price:
        raise HTTPException(status_code=400, detail=f"SKU {sku_id} heeft geen actuele prijs")
    cost = float(product.cost_price) if product.cost_price else None

    # Meest recente concurrentprijzen (laatste waarnemingsdag per concurrent) — shop-gefilterd
    since = date.today() - timedelta(days=14)
    rows = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(models.FactCompetitorPriceDaily.sku_id == sku_id,
                models.FactCompetitorPriceDaily.date >= since,
                models.FactCompetitorPriceDaily.price.isnot(None),
                models.FactCompetitorPriceDaily.shop_id == sid)
        .order_by(models.FactCompetitorPriceDaily.date)
        .all()
    )
    from engine.competition_intelligence import rejected_pairs
    rejected = rejected_pairs(db)
    latest: dict[str, float] = {}
    for r in rows:
        if (r.sku_id, r.competitor_name) in rejected:
            continue
        latest[r.competitor_name] = float(r.price)
    if not latest:
        return {
            "sku_id": sku_id, "data_available": False,
            "note": "Geen recente concurrentprijzen voor deze SKU — simulatie niet mogelijk.",
        }

    # Strategieën per concurrent (laatste run) — shop-gefilterd
    strategies: dict[str, models.CompetitorStrategyResult] = {}
    for s in (db.query(models.CompetitorStrategyResult)
              .filter(models.CompetitorStrategyResult.competitor_name.in_(list(latest)),
                      models.CompetitorStrategyResult.shop_id == sid)
              .order_by(models.CompetitorStrategyResult.run_date)
              .all()):
        strategies[s.competitor_name] = s

    # Elasticiteit (laatste run)
    elast = (db.query(models.SkuElasticity)
             .filter(models.SkuElasticity.sku_id == sku_id)
             .order_by(models.SkuElasticity.run_date.desc())
             .first())
    own_e = float(elast.own_price_elasticity) if elast and elast.own_price_elasticity else -1.2
    comp_e = float(elast.competitive_elasticity) if elast and elast.competitive_elasticity else 0.4

    follow_set = {c.strip() for c in (assume_follow or [])}
    no_follow_set = {c.strip() for c in (assume_no_follow or [])}

    new_own = own_price * (1 + change_pct)
    per_comp = []
    exp_new_comp: dict[str, float] = {}
    for name, price in latest.items():
        strat = strategies.get(name)
        stype = strat.strategy_type if strat else None
        p = FOLLOW_PROBABILITY.get(stype or "", DEFAULT_FOLLOW_PROBABILITY)
        if change_pct > 0:
            p *= 0.5  # verhoging wordt minder vaak gevolgd
        if name in follow_set:
            p = 1.0
        elif name in no_follow_set:
            p = 0.0
        followed_price = price * (1 + change_pct)
        expected_price = p * followed_price + (1 - p) * price
        exp_new_comp[name] = expected_price
        per_comp.append({
            "competitor": name,
            "strategy_type": stype,
            "strategy_label": strat.strategy_label_nl if strat else None,
            "follow_probability": round(p, 2),
            "current_price": round(price, 2),
            "expected_price": round(expected_price, 2),
        })

    def _index(comp_prices: dict[str, float], own: float) -> Optional[float]:
        vals = [v for v in comp_prices.values() if v > 0]
        return round(own / (sum(vals) / len(vals)), 4) if vals else None

    idx_before = _index(latest, own_price)
    idx_expected = _index(exp_new_comp, new_own)
    idx_nobody = _index(latest, new_own)
    idx_all = _index({k: v * (1 + change_pct) for k, v in latest.items()}, new_own)

    # Volume-effect: eigen elasticiteit + competitieve correctie voor het
    # verwachte deel dat volgt (als iedereen volgt, blijft de relatieve
    # positie gelijk en dempt het effect).
    avg_follow = (sum(c["follow_probability"] for c in per_comp) / len(per_comp)) if per_comp else 0.0
    exp_comp_change = avg_follow * change_pct
    volume_effect = own_e * change_pct + comp_e * exp_comp_change
    volume_effect_nobody = own_e * change_pct
    volume_effect_all = own_e * change_pct + comp_e * change_pct

    # Baseline: verkoop laatste 30 dagen — shop-gefilterd
    sales = (db.query(models.FactSalesDaily)
             .filter(models.FactSalesDaily.sku_id == sku_id,
                     models.FactSalesDaily.date >= date.today() - timedelta(days=30),
                     models.FactSalesDaily.shop_id == sid)
             .all())
    base_units = sum(float(s.units_sold or 0) for s in sales)

    def _scenario(vol_eff: float, own_p: float) -> dict:
        units = base_units * (1 + vol_eff)
        revenue = units * own_p
        margin = units * (own_p - cost) if cost is not None else None
        return {
            "volume_effect_pct": round(vol_eff * 100, 2),
            "units": round(units, 1),
            "revenue": round(revenue, 2),
            "margin": round(margin, 2) if margin is not None else None,
        }

    base_margin = base_units * (own_price - cost) if cost is not None else None
    return {
        "sku_id": sku_id,
        "product_name": product.product_name,
        "data_available": True,
        "change_pct": change_pct,
        "current_price": round(own_price, 2),
        "new_price": round(new_own, 2),
        "elasticity_used": {"own": own_e, "competitive": comp_e,
                            "source": "sku_elasticity" if elast else "default",
                            "method": elast.method_label if elast and elast.method_label else "default",
                            "regression_r2": float(elast.regression_r2) if elast and elast.regression_r2 is not None else None},
        "price_index": {
            "before": idx_before,
            "expected": idx_expected,
            "if_nobody_follows": idx_nobody,
            "if_all_follow": idx_all,
        },
        "baseline_30d": {
            "units": round(base_units, 1),
            "revenue": round(base_units * own_price, 2),
            "margin": round(base_margin, 2) if base_margin is not None else None,
        },
        "scenario_expected": _scenario(volume_effect, new_own),
        "scenario_nobody_follows": _scenario(volume_effect_nobody, new_own),
        "scenario_all_follow": _scenario(volume_effect_all, new_own),
        "competitors": per_comp,
        "assumptions": [
            "Volgkans per concurrent is afgeleid van de herkende prijsstrategie.",
            "Bij een prijsverhoging is de volgkans gehalveerd.",
            "Volume-effect = eigen elasticiteit × eigen wijziging + competitieve "
            "elasticiteit × verwachte concurrentwijziging.",
        ],
        "note": "Simulatie — er wordt geen prijswijziging uitgevoerd of klaargezet.",
    }
