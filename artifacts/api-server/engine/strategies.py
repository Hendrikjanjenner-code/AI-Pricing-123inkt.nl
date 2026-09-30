"""
Pricing strategy implementations.

Each function receives a `context` dict with:
  - product: DimProduct ORM object
  - sales: pd.DataFrame of recent daily sales
  - prices: pd.DataFrame of own price history
  - competitors: pd.DataFrame of competitor prices
  - inventory: pd.DataFrame of stock levels
  - basket: pd.DataFrame of basket affinity data
  - substitutions: list of related SKU IDs
  - all_products: dict of sku_id -> DimProduct

Each function returns a dict:
  - recommended_price: float
  - change_pct: float
  - confidence: float (0-1)
  - reason_code: str
  - expected_units: float (optional)
  - expected_revenue: float (optional)
  - expected_margin: float (optional)
  - expected_margin_uplift: float (optional)
"""
import numpy as np
import pandas as pd
from typing import Optional

from engine.competitor_strategy_engine import strategie_gewicht


def _current_price(context: dict) -> Optional[float]:
    p = context["product"]
    if p.current_price:
        return float(p.current_price)
    prices = context["prices"]
    if not prices.empty:
        latest = prices.sort_values("date").iloc[-1]
        return latest.get("price")
    return None


def _cost_price(context: dict) -> Optional[float]:
    p = context["product"]
    return float(p.cost_price) if p.cost_price is not None else None


def _avg_daily_units(context: dict) -> float:
    sales = context["sales"]
    if sales.empty:
        return 0.0
    if context.get("volume_days"):
        return float(sales["units_sold"].sum()) / context["volume_days"]
    recent = sales.sort_values("date").tail(30)
    return float(recent["units_sold"].mean()) if not recent.empty else 0.0


def _estimate_margin_uplift(cost: float, current: float, new_price: float, avg_units: float) -> dict:
    """Estimate margin uplift from a price change, assuming unit demand shifts with price."""
    if current <= 0 or cost is None:
        return {"expected_units": avg_units, "expected_revenue": None, "expected_margin": None, "expected_margin_uplift": None}
    elasticity = -1.5  # Default own-price elasticity
    change_pct = (new_price - current) / current
    new_units = avg_units * (1 + elasticity * change_pct)
    new_units = max(0, new_units)
    new_margin_per_unit = new_price - cost
    old_margin_per_unit = current - cost
    new_total_margin = new_margin_per_unit * new_units
    old_total_margin = old_margin_per_unit * avg_units
    uplift = new_total_margin - old_total_margin
    return {
        "expected_units": round(new_units, 2),
        "expected_revenue": round(new_price * new_units, 2),
        "expected_margin": round(new_total_margin, 2),
        "expected_margin_uplift": round(uplift, 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. SUBSTITUTION_PORTFOLIO
# Optimise total portfolio margin across A-brand / private-label pair.
# ──────────────────────────────────────────────────────────────────────────────
def substitution_portfolio(context: dict) -> Optional[dict]:
    product = context["product"]
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    subs = context["substitutions"]
    all_products = context["all_products"]
    avg_units = _avg_daily_units(context)

    is_private_label = product.is_private_label
    if subs and all_products:
        sub_product = all_products.get(subs[0])
        if sub_product and sub_product.current_price:
            sub_price = float(sub_product.current_price)
            if is_private_label:
                # Private label: keep gap attractive (15-25% below A-brand)
                target = sub_price * 0.82
                reason = "PRIVATE_LABEL_SUBSTITUTION_OPPORTUNITY"
                confidence = 0.75
            else:
                # A-brand: maintain premium, slight uplift if gap too narrow
                gap = (current - sub_price) / sub_price if sub_price > 0 else 0
                if gap < 0.10:
                    target = current * 1.03
                    reason = "MARGIN_UPSIDE_PRICE_INCREASE"
                else:
                    target = current
                    reason = "REPEAT_PURCHASE_PRICE_STABILITY"
                confidence = 0.70
        else:
            target = current * 1.02
            reason = "MARGIN_UPSIDE_PRICE_INCREASE"
            confidence = 0.60
    else:
        target = current * 1.02
        reason = "MARGIN_UPSIDE_PRICE_INCREASE"
        confidence = 0.60

    change_pct = round((target - current) / current * 100, 2) if current > 0 else 0
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": reason,
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. COMPETITOR_INDEX
# Recommend price based on target price index vs competitors.
# ──────────────────────────────────────────────────────────────────────────────
def competitor_index(context: dict) -> Optional[dict]:
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    competitors = context["competitors"]
    avg_units = _avg_daily_units(context)

    if competitors.empty or competitors["price"].isna().all():
        return {
            "recommended_price": current,
            "change_pct": 0.0,
            "confidence": 0.30,
            "reason_code": "KEEP_PRICE_LOW_CONFIDENCE",
            **(_estimate_margin_uplift(cost, current, current, avg_units) if cost else {}),
        }

    recent_comp = competitors.sort_values("date").dropna(subset=["price"]).tail(7)
    comp_prices = recent_comp["price"]

    # Latest known price per competitor within the recent window.
    if "competitor_name" in recent_comp.columns:
        per_competitor = recent_comp.groupby("competitor_name", as_index=False).last()
    else:
        per_competitor = recent_comp

    # Strategy-weighted competitor index: down-weight competitors that are in
    # INVENTORY_CLEARANCE (leaving the market) and up-weight PRICE_LEADERs.
    strategy_map = context.get("competitor_strategies", {}) or {}
    weighted_sum = 0.0
    weight_total = 0.0
    signal_competitors: list[dict] = []
    for _, row in per_competitor.iterrows():
        price = float(row["price"])
        name = row.get("competitor_name") if hasattr(row, "get") else None
        strat = strategy_map.get(name) if name else None
        strategy_type = strat["strategy_type"] if strat else None
        weight = strategie_gewicht(strategy_type)
        weighted_sum += price * weight
        weight_total += weight
        if strat:
            signal_competitors.append({
                "name": name,
                "price": round(price, 4),
                "strategy_type": strategy_type,
                "label_nl": strat.get("label_nl"),
                "weight": weight,
            })

    if weight_total > 0:
        avg_comp = weighted_sum / weight_total
    else:
        avg_comp = float(comp_prices.mean())

    competitor_strategy_signal = None
    if signal_competitors:
        competitor_strategy_signal = {
            "applied": any(c["weight"] != 1.0 for c in signal_competitors),
            "method": "weighted_competitor_index",
            "competitors": signal_competitors,
        }

    # Target price index: 1.0 = match average, 0.98 = 2% below average
    target_index = 0.98
    target = avg_comp * target_index

    if cost and target < cost * 1.05:
        target = cost * 1.05
        reason = "MIN_PRICE_GUARDRAIL_APPLIED"
    else:
        price_diff_pct = (current - avg_comp) / avg_comp * 100 if avg_comp > 0 else 0
        if price_diff_pct > 5:
            reason = "COMPETITOR_PRICE_PRESSURE"
        elif price_diff_pct < -5:
            reason = "MARGIN_UPSIDE_PRICE_INCREASE"
        else:
            reason = "KEEP_PRICE_LOW_CONFIDENCE"

    change_pct = round((target - current) / current * 100, 2) if current > 0 else 0
    confidence = min(0.90, 0.5 + len(comp_prices) * 0.05)
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": round(confidence, 2),
        "reason_code": reason,
        "competitor_strategy_signal": competitor_strategy_signal,
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. MARGIN_OPTIMIZATION
# Find the margin-maximizing price using estimated demand sensitivity.
# ──────────────────────────────────────────────────────────────────────────────
def margin_optimization(context: dict) -> Optional[dict]:
    product = context["product"]
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    avg_units = _avg_daily_units(context)
    elasticity = -1.5
    min_p = float(product.min_price) if product.min_price else current * 0.8
    max_p = float(product.max_price) if product.max_price else current * 1.2

    # Grid search for margin-maximizing price
    best_price = current
    best_margin = 0.0
    test_prices = np.linspace(min_p, max_p, 20)
    for test_price in test_prices:
        if cost and test_price < cost:
            continue
        chg = (test_price - current) / current
        units = max(0, avg_units * (1 + elasticity * chg))
        margin_pu = test_price - (cost or 0)
        total = margin_pu * units
        if total > best_margin:
            best_margin = total
            best_price = test_price

    change_pct = round((best_price - current) / current * 100, 2) if current > 0 else 0
    confidence = 0.72 if avg_units > 5 else 0.45
    reason = "MARGIN_UPSIDE_PRICE_INCREASE" if change_pct > 0 else "KEEP_PRICE_LOW_CONFIDENCE"
    financials = _estimate_margin_uplift(cost, current, best_price, avg_units) if cost else {}
    return {
        "recommended_price": round(best_price, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": reason,
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. STOCK_CLEARANCE
# Drive down price gradually to liquidate overstock.
# ──────────────────────────────────────────────────────────────────────────────
def stock_clearance(context: dict) -> Optional[dict]:
    product = context["product"]
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    inventory = context["inventory"]
    avg_units = _avg_daily_units(context)

    if inventory.empty:
        stock_qty = product.stock_quantity or 0
        days_of_stock = None
    else:
        latest_inv = inventory.sort_values("date").iloc[-1]
        stock_qty = int(latest_inv.get("stock_quantity", 0))
        days_of_stock = latest_inv.get("days_of_stock")

    # Clearance discount: up to 20% below current, max 5% per day
    if days_of_stock and days_of_stock > 60:
        discount = 0.05
    elif days_of_stock and days_of_stock > 30:
        discount = 0.03
    else:
        discount = 0.02

    target = current * (1 - discount)
    min_p = float(product.min_price) if product.min_price else (cost or current * 0.7)
    target = max(target, min_p)

    change_pct = round((target - current) / current * 100, 2)
    confidence = 0.80 if days_of_stock else 0.55
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": "STOCK_CLEARANCE_DISCOUNT",
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. BASKET_BUILDER
# Keep price competitive to drive basket growth.
# ──────────────────────────────────────────────────────────────────────────────
def basket_builder(context: dict) -> Optional[dict]:
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    basket = context["basket"]
    avg_units = _avg_daily_units(context)
    competitors = context["competitors"]

    # Match or beat average competitor price to keep in basket
    if not competitors.empty and not competitors["price"].isna().all():
        avg_comp = float(competitors["price"].dropna().mean())
        target = min(current, avg_comp * 0.99)
    else:
        target = current

    if cost and target < cost * 1.02:
        target = cost * 1.02

    change_pct = round((target - current) / current * 100, 2) if current > 0 else 0
    avg_affinity = float(basket["affinity_score"].mean()) if not basket.empty else 0.3
    confidence = min(0.85, 0.5 + avg_affinity)
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": round(confidence, 2),
        "reason_code": "BASKET_BUILDER_KEEP_COMPETITIVE",
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. VOLUME_DISCOUNT
# Lower price when volume elasticity is strong.
# ──────────────────────────────────────────────────────────────────────────────
def volume_discount(context: dict) -> Optional[dict]:
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    sales = context["sales"]
    avg_units = _avg_daily_units(context)

    # High volume = stronger elasticity, recommend slight price drop to grow volume
    elasticity = -2.0  # More elastic for volume products
    if avg_units > 100:
        discount = 0.04  # 4% discount for very high volume
    elif avg_units > 20:
        discount = 0.02
    else:
        discount = 0.0

    target = current * (1 - discount)
    min_p = float(context["product"].min_price) if context["product"].min_price else (cost or current * 0.8)
    target = max(target, min_p)

    change_pct = round((target - current) / current * 100, 2)
    confidence = 0.70 if avg_units > 10 else 0.50
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": "MARGIN_UPSIDE_PRICE_INCREASE" if discount == 0 else "COMPETITOR_PRICE_PRESSURE",
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7. REPEAT_PURCHASE
# Prioritize price stability for recurring buyers.
# ──────────────────────────────────────────────────────────────────────────────
def repeat_purchase(context: dict) -> Optional[dict]:
    product = context["product"]
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    prices = context["prices"]
    avg_units = _avg_daily_units(context)

    # Penalise large price increases — max 2% up, 1% down
    if prices.empty:
        target = current
    else:
        recent = prices.sort_values("date").tail(30)
        price_std = float(recent["price"].dropna().std()) if len(recent) > 1 else 0
        price_trend = 0.0
        if len(recent) >= 7 and "price" in recent.columns:
            try:
                import numpy as np
                p_arr = recent["price"].dropna().values
                if len(p_arr) >= 3:
                    x = np.arange(len(p_arr))
                    slope = np.polyfit(x, p_arr, 1)[0]
                    price_trend = slope / current
            except Exception:
                pass
        # Only allow small adjustments to protect recurring customers
        if price_trend > 0.001:
            target = current * 1.01  # Very small increase
        else:
            target = current

    change_pct = round((target - current) / current * 100, 2) if current > 0 else 0
    confidence = 0.78 if avg_units > 3 else 0.55
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": "REPEAT_PURCHASE_PRICE_STABILITY",
        **financials,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 8. LOW_VELOCITY
# Avoid frequent changes; protect margin on slow-moving items.
# ──────────────────────────────────────────────────────────────────────────────
def low_velocity(context: dict) -> Optional[dict]:
    product = context["product"]
    current = _current_price(context)
    cost = _cost_price(context)
    if current is None:
        return None

    avg_units = _avg_daily_units(context)
    inventory = context["inventory"]

    # Only recommend a change if margin is very poor
    if cost and current < cost * 1.10:
        target = cost * 1.15  # Push up for margin
        reason = "LOW_VELOCITY_MARGIN_PROTECTION"
        confidence = 0.65
    else:
        target = current  # Keep stable
        reason = "KEEP_PRICE_LOW_CONFIDENCE"
        confidence = 0.60

    change_pct = round((target - current) / current * 100, 2) if current > 0 else 0
    financials = _estimate_margin_uplift(cost, current, target, avg_units) if cost else {}
    return {
        "recommended_price": round(target, 4),
        "change_pct": change_pct,
        "confidence": confidence,
        "reason_code": reason,
        **financials,
    }
