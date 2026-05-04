"""
Main pricing engine orchestrator.

For each SKU:
1. Load all relevant data (prices, sales, inventory, competitors, affinity)
2. Route to the correct strategy function based on strategy_type
3. Apply safety rules
4. Persist recommendations to fact_pricing_recommendation_daily
"""
import numpy as np
import pandas as pd
from datetime import date, datetime
from sqlalchemy.orm import Session
import models
from engine import strategies
from engine.safety_rules import apply_safety_rules

MODEL_VERSION = "v1.0.0"


def run_pricing_engine(db: Session) -> tuple[int, int]:
    """
    Full model run: processes all active SKUs and writes recommendations.
    Returns (processed_count, skipped_count).
    """
    today = date.today()
    products = db.query(models.DimProduct).filter(
        models.DimProduct.lifecycle_status != "discontinued"
    ).all()

    # Preload all fact data into DataFrames for speed
    sales_df = _load_sales(db)
    price_df = _load_prices(db)
    comp_df = _load_competitor_prices(db)
    inventory_df = _load_inventory(db)
    basket_df = _load_basket_affinity(db)
    substitution_map = _load_substitutions(db)

    processed, skipped = 0, 0

    for product in products:
        try:
            # Check if recommendation already exists for today
            existing = db.query(models.FactPricingRecommendationDaily).filter(
                models.FactPricingRecommendationDaily.sku_id == product.sku_id,
                models.FactPricingRecommendationDaily.date == today,
            ).first()
            if existing:
                processed += 1
                continue

            # Gather per-SKU data slices
            sku_sales = sales_df[sales_df["sku_id"] == product.sku_id]
            sku_prices = price_df[price_df["sku_id"] == product.sku_id]
            sku_comp = comp_df[comp_df["sku_id"] == product.sku_id]
            sku_inv = inventory_df[inventory_df["sku_id"] == product.sku_id]
            sku_basket = basket_df[basket_df["sku_id_a"] == product.sku_id]
            subs = substitution_map.get(product.sku_id, [])

            context = {
                "product": product,
                "sales": sku_sales,
                "prices": sku_prices,
                "competitors": sku_comp,
                "inventory": sku_inv,
                "basket": sku_basket,
                "substitutions": subs,
                "all_products": {p.sku_id: p for p in products},
            }

            # Route to strategy
            strategy = product.strategy_type or "MARGIN_OPTIMIZATION"
            result = _run_strategy(strategy, context)

            if result is None:
                skipped += 1
                continue

            # Apply safety rules
            result = apply_safety_rules(product, result, sku_inv)

            # Persist
            rec = models.FactPricingRecommendationDaily(
                date=today,
                sku_id=product.sku_id,
                current_price=float(product.current_price) if product.current_price else None,
                recommended_price=result["recommended_price"],
                recommended_change_pct=result["change_pct"],
                expected_units=result.get("expected_units"),
                expected_revenue=result.get("expected_revenue"),
                expected_margin=result.get("expected_margin"),
                expected_margin_uplift=result.get("expected_margin_uplift"),
                confidence_score=result["confidence"],
                reason_code=result["reason_code"],
                strategy_type=strategy,
                safety_status=result.get("safety_status", "ok"),
                approval_status="pending",
                model_version=MODEL_VERSION,
            )
            db.add(rec)
            processed += 1

        except Exception:
            skipped += 1
            continue

    db.commit()
    return processed, skipped


def _run_strategy(strategy: str, context: dict) -> dict | None:
    """Dispatch to the appropriate strategy function."""
    dispatch = {
        "SUBSTITUTION_PORTFOLIO": strategies.substitution_portfolio,
        "COMPETITOR_INDEX": strategies.competitor_index,
        "MARGIN_OPTIMIZATION": strategies.margin_optimization,
        "STOCK_CLEARANCE": strategies.stock_clearance,
        "BASKET_BUILDER": strategies.basket_builder,
        "VOLUME_DISCOUNT": strategies.volume_discount,
        "REPEAT_PURCHASE": strategies.repeat_purchase,
        "LOW_VELOCITY": strategies.low_velocity,
    }
    fn = dispatch.get(strategy, strategies.margin_optimization)
    return fn(context)


def _load_sales(db: Session) -> pd.DataFrame:
    rows = db.query(models.FactSalesDaily).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "units_sold", "revenue", "margin", "margin_pct"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "units_sold": r.units_sold or 0,
        "revenue": float(r.revenue) if r.revenue else 0,
        "margin": float(r.margin) if r.margin else 0,
        "margin_pct": float(r.margin_pct) if r.margin_pct else 0,
    } for r in rows])


def _load_prices(db: Session) -> pd.DataFrame:
    rows = db.query(models.FactPriceDaily).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "price"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "price": float(r.price) if r.price else None,
    } for r in rows])


def _load_competitor_prices(db: Session) -> pd.DataFrame:
    rows = db.query(models.FactCompetitorPriceDaily).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "competitor_name", "price"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "competitor_name": r.competitor_name,
        "price": float(r.price) if r.price else None,
    } for r in rows])


def _load_inventory(db: Session) -> pd.DataFrame:
    rows = db.query(models.FactInventoryDaily).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "stock_quantity", "days_of_stock"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "stock_quantity": r.stock_quantity or 0,
        "days_of_stock": float(r.days_of_stock) if r.days_of_stock else None,
    } for r in rows])


def _load_basket_affinity(db: Session) -> pd.DataFrame:
    rows = db.query(models.FactBasketAffinity).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id_a", "sku_id_b", "affinity_score"])
    return pd.DataFrame([{
        "sku_id_a": r.sku_id_a,
        "sku_id_b": r.sku_id_b,
        "affinity_score": float(r.affinity_score) if r.affinity_score else 0,
    } for r in rows])


def _load_substitutions(db: Session) -> dict:
    rows = db.query(models.MapSubstitution).all()
    result = {}
    for r in rows:
        result.setdefault(r.a_brand_sku, []).append(r.private_label_sku)
        result.setdefault(r.private_label_sku, []).append(r.a_brand_sku)
    return result
