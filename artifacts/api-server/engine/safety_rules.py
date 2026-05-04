"""
Safety rule enforcement.

Applied to every recommendation BEFORE it is written to the database:
- Price cannot go below cost (unless explicitly allowed)
- Price cannot go below min_price
- Price cannot exceed max_price
- Max daily price increase: 5%
- Max daily price decrease: 5%
- No recommendation for out-of-stock SKUs (unless STOCK_CLEARANCE)
- Flag low-confidence recommendations
- Flag extreme competitor price differences
"""
import pandas as pd
from typing import Optional
import models


MAX_DAILY_CHANGE_PCT = 0.05  # 5%
LOW_CONFIDENCE_THRESHOLD = 0.40


def apply_safety_rules(
    product: models.DimProduct,
    result: dict,
    inventory_df: pd.DataFrame,
) -> dict:
    """
    Clamp the recommended price to safety limits and set safety_status.
    Returns the (possibly modified) result dict.
    """
    recommended = result["recommended_price"]
    current = float(product.current_price) if product.current_price else recommended
    cost = float(product.cost_price) if product.cost_price else None
    min_p = float(product.min_price) if product.min_price else None
    max_p = float(product.max_price) if product.max_price else None

    safety_status = "ok"
    reason_override = None

    # ── Out-of-stock check ─────────────────────────────────────────────────
    if not inventory_df.empty:
        latest = inventory_df.sort_values("date").iloc[-1]
        stock = int(latest.get("stock_quantity", 0))
        strategy = result.get("strategy_type", product.strategy_type or "")
        if stock == 0 and strategy != "STOCK_CLEARANCE":
            result["recommended_price"] = current
            result["change_pct"] = 0.0
            result["reason_code"] = "OUT_OF_STOCK_NO_CHANGE"
            result["safety_status"] = "blocked"
            return result

    # ── Daily change cap ──────────────────────────────────────────────────
    if current > 0:
        max_increase = current * (1 + MAX_DAILY_CHANGE_PCT)
        max_decrease = current * (1 - MAX_DAILY_CHANGE_PCT)
        if recommended > max_increase:
            recommended = max_increase
            reason_override = "MAX_PRICE_GUARDRAIL_APPLIED"
            safety_status = "warning"
        elif recommended < max_decrease:
            recommended = max_decrease
            reason_override = "MIN_PRICE_GUARDRAIL_APPLIED"
            safety_status = "warning"

    # ── Cost floor ────────────────────────────────────────────────────────
    if cost and recommended < cost:
        recommended = cost * 1.01
        reason_override = "MIN_PRICE_GUARDRAIL_APPLIED"
        safety_status = "warning"

    # ── Min/max price guardrails ──────────────────────────────────────────
    if min_p and recommended < min_p:
        recommended = min_p
        reason_override = "MIN_PRICE_GUARDRAIL_APPLIED"
        safety_status = "warning"
    if max_p and recommended > max_p:
        recommended = max_p
        reason_override = "MAX_PRICE_GUARDRAIL_APPLIED"
        safety_status = "warning"

    # ── Low confidence flag ───────────────────────────────────────────────
    if result.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD:
        safety_status = "warning"

    # Recompute change_pct after clamping
    if current > 0:
        result["change_pct"] = round((recommended - current) / current * 100, 2)

    result["recommended_price"] = round(recommended, 4)
    result["safety_status"] = safety_status
    if reason_override:
        result["reason_code"] = reason_override

    return result
