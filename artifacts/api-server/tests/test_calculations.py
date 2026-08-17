"""
Berekeningstests (§43): pure unit tests voor kernberekeningen —
marge-metrics, pricing-strategieën, safety rules en customer switching (ISV).
Geen database nodig.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest

from metrics import (
    gross_margin, gross_margin_pct, margin_ratio, safe_div, asp, price_index,
)
from engine.strategies import (
    _estimate_margin_uplift, margin_optimization, stock_clearance,
)
from engine.safety_rules import apply_safety_rules, MAX_DAILY_CHANGE_PCT
from engine.internal_competition import (
    calculate_isv, estimate_switch_probability, get_recommended_action,
)
from engine.competition_engine import get_competition_class


# ---------- Marge-metrics ----------

def test_gross_margin():
    assert gross_margin(100.0, 60.0) == 40.0


def test_gross_margin_pct():
    assert gross_margin_pct(100.0, 60.0) == 40.0
    assert gross_margin_pct(0.0, 60.0) is None


def test_margin_ratio():
    assert margin_ratio(10.0, 6.0) == pytest.approx(0.4)
    # ontbrekende/nul-prijs → default
    assert margin_ratio(0.0, 6.0) == pytest.approx(0.25)


def test_safe_div_and_asp():
    assert safe_div(1, 0) is None
    assert asp(100.0, 4) == 25.0


def test_price_index_direction():
    # price_index = eigen / concurrent: <1.0 betekent goedkoper (gunstig)
    assert price_index(9.0, 10.0) == pytest.approx(0.9)
    assert price_index(11.0, 10.0) > 1.0


# ---------- Pricing-strategieën ----------

def _product(**over):
    base = dict(current_price=10.0, cost_price=6.0, min_price=None,
                max_price=None, is_private_label=False, stock_quantity=0,
                strategy_type=None, sku_id="UT-1")
    base.update(over)
    return SimpleNamespace(**base)


def _ctx(**over):
    ctx = {
        "product": _product(),
        "sales": pd.DataFrame({"date": [], "units_sold": []}),
        "prices": pd.DataFrame({"date": [], "price": []}),
        "competitors": pd.DataFrame({"date": [], "price": []}),
        "inventory": pd.DataFrame(),
        "basket": pd.DataFrame({"affinity_score": []}),
        "substitutions": [],
        "all_products": {},
    }
    ctx.update(over)
    return ctx


def test_estimate_margin_uplift_elasticity():
    r = _estimate_margin_uplift(6.0, 10.0, 11.0, 20.0)
    # +10% prijs bij elasticiteit -1.5 → -15% volume: 20 → 17 stuks/dag
    assert r["expected_units"] == pytest.approx(17.0)
    assert r["expected_margin"] == pytest.approx((11.0 - 6.0) * 17.0, rel=1e-6)


def test_margin_optimization_never_prices_below_cost():
    res = margin_optimization(_ctx())
    if res is not None:
        assert res["recommended_price"] >= 6.0


def test_stock_clearance_discounts_but_not_below_cost():
    inv = pd.DataFrame({
        "date": [pd.Timestamp("2026-08-01")],
        "stock_quantity": [500],
        "days_of_stock": [120],
    })
    ctx = _ctx(inventory=inv)
    res = stock_clearance(ctx)
    if res is not None:
        assert res["recommended_price"] < 10.0
        assert res["recommended_price"] >= 6.0


# ---------- Safety rules ----------

def test_safety_rules_clamp_max_daily_change():
    p = _product(current_price=10.0, stock_quantity=50)
    result = apply_safety_rules(p, {"recommended_price": 15.0, "confidence": 0.9},
                                pd.DataFrame())
    assert result["recommended_price"] <= 10.0 * (1 + MAX_DAILY_CHANGE_PCT) + 1e-9


def test_safety_rules_never_below_cost():
    p = _product(current_price=10.0, cost_price=9.8, stock_quantity=50)
    result = apply_safety_rules(p, {"recommended_price": 9.0, "confidence": 0.9},
                                pd.DataFrame())
    assert result["recommended_price"] >= 9.8 - 1e-9


def test_safety_rules_respect_min_price():
    p = _product(current_price=10.0, min_price=9.9, stock_quantity=50)
    result = apply_safety_rules(p, {"recommended_price": 9.0, "confidence": 0.9},
                                pd.DataFrame())
    assert result["recommended_price"] >= 9.9 - 1e-9


# ---------- Customer switching / cannibalisatie ----------

def test_calculate_isv():
    assert calculate_isv(0.6, 0.4) == pytest.approx(0.24)
    assert calculate_isv(0.0, 0.9) == 0.0


def test_estimate_switch_probability_monotonic_in_strength():
    weak = estimate_switch_probability(-0.2, 0.2)
    strong = estimate_switch_probability(-0.2, 0.9)
    assert strong > weak
    assert 0.0 <= weak <= 1.0 and 0.0 <= strong <= 1.0


def test_recommended_action_private_label_push():
    action, _, _ = get_recommended_action(0.6, 0.2, 0.2, 0.3)
    assert action == "PRIVATE_LABEL_PUSH"


# ---------- PCIS / competition class ----------

def test_competition_class_bounds():
    lo = get_competition_class(0.05)
    hi = get_competition_class(0.95)
    assert lo != hi
    for v in (0.0, 0.25, 0.5, 0.75, 0.999):
        assert isinstance(get_competition_class(v), str)
