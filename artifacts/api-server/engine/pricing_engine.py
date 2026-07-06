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
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
import models
from engine import strategies
from engine.safety_rules import apply_safety_rules
from engine.competitor_strategy_engine import analyseer_alle_concurrenten

MODEL_VERSION = "v1.0.0"

# Aantal dagen prijshistorie dat wordt gebruikt om concurrentstrategieën te
# classificeren voordat de COMPETITOR_INDEX-strategie wordt gedraaid.
STRATEGY_LOOKBACK_DAYS = 30


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
    competitor_strategies = _load_competitor_strategies(db)

    # Pre-group per SKU into dicts for O(1) lookup. With tens of thousands of
    # products and hundreds of thousands of competitor rows, boolean-masking each
    # DataFrame inside the loop is O(N·M) and far too slow; grouping once is O(N).
    empty_sales, empty_price = sales_df.iloc[0:0], price_df.iloc[0:0]
    empty_comp, empty_inv, empty_basket = comp_df.iloc[0:0], inventory_df.iloc[0:0], basket_df.iloc[0:0]
    sales_by = {k: v for k, v in sales_df.groupby("sku_id")} if not sales_df.empty else {}
    price_by = {k: v for k, v in price_df.groupby("sku_id")} if not price_df.empty else {}
    comp_by = {k: v for k, v in comp_df.groupby("sku_id")} if not comp_df.empty else {}
    inv_by = {k: v for k, v in inventory_df.groupby("sku_id")} if not inventory_df.empty else {}
    basket_by = {k: v for k, v in basket_df.groupby("sku_id_a")} if not basket_df.empty else {}

    # Verversingssemantiek: menselijke beslissingen (goedgekeurd/afgewezen) van
    # vandaag blijven behouden; openstaande (pending) aanbevelingen worden
    # opnieuw gegenereerd zodat een nieuwe modelrun na een feed-sync de laatste
    # prijzen weerspiegelt (delete-then-insert, net als de fact-tabellen).
    existing_today = db.query(
        models.FactPricingRecommendationDaily.sku_id,
        models.FactPricingRecommendationDaily.approval_status,
    ).filter(models.FactPricingRecommendationDaily.date == today).all()
    locked = {row[0] for row in existing_today if row[1] != "pending"}
    db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.date == today,
        models.FactPricingRecommendationDaily.approval_status == "pending",
    ).delete(synchronize_session=False)
    db.commit()

    all_products = {p.sku_id: p for p in products}
    rec_maps: list[dict] = []
    processed, skipped = 0, 0

    for product in products:
        try:
            if product.sku_id in locked:
                skipped += 1
                continue

            sku_inv = inv_by.get(product.sku_id, empty_inv)
            context = {
                "product": product,
                "sales": sales_by.get(product.sku_id, empty_sales),
                "prices": price_by.get(product.sku_id, empty_price),
                "competitors": comp_by.get(product.sku_id, empty_comp),
                "inventory": sku_inv,
                "basket": basket_by.get(product.sku_id, empty_basket),
                "substitutions": substitution_map.get(product.sku_id, []),
                "all_products": all_products,
                "competitor_strategies": competitor_strategies,
            }

            # Route to strategy
            strategy = product.strategy_type or "MARGIN_OPTIMIZATION"
            result = _run_strategy(strategy, context)

            if result is None:
                skipped += 1
                continue

            # Apply safety rules
            result = apply_safety_rules(product, result, sku_inv)

            rec_maps.append({
                "date": today,
                "sku_id": product.sku_id,
                "current_price": float(product.current_price) if product.current_price else None,
                "recommended_price": result["recommended_price"],
                "recommended_change_pct": result["change_pct"],
                "expected_units": result.get("expected_units"),
                "expected_revenue": result.get("expected_revenue"),
                "expected_margin": result.get("expected_margin"),
                "expected_margin_uplift": result.get("expected_margin_uplift"),
                "confidence_score": result["confidence"],
                "reason_code": result["reason_code"],
                "strategy_type": strategy,
                "competitor_strategy_signal": result.get("competitor_strategy_signal"),
                "safety_status": result.get("safety_status", "ok"),
                "approval_status": "pending",
                "model_version": MODEL_VERSION,
            })
            processed += 1

        except Exception:
            skipped += 1
            continue

    for i in range(0, len(rec_maps), 5_000):
        db.bulk_insert_mappings(models.FactPricingRecommendationDaily, rec_maps[i:i + 5_000])
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


def _load_competitor_strategies(db: Session) -> dict[str, dict]:
    """
    Classificeer elke concurrent op basis van zijn prijshistorie van de
    afgelopen STRATEGY_LOOKBACK_DAYS dagen en geef een lookup terug van
    {concurrent_naam: classificatie-dict}. Deze signalen worden door de
    COMPETITOR_INDEX-strategie gebruikt om concurrenten te wegen.
    """
    since = date.today() - timedelta(days=STRATEGY_LOOKBACK_DAYS)
    rows = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(models.FactCompetitorPriceDaily.date >= since)
        .all()
    )

    prijsdata: dict[str, list[tuple[date, float]]] = {}
    for r in rows:
        if r.price is None:
            continue
        naam = r.competitor_name or "Onbekend"
        prijsdata.setdefault(naam, []).append((r.date, float(r.price)))

    if not prijsdata:
        return {}

    resultaten = analyseer_alle_concurrenten(prijsdata)
    return {res["concurrent"]: res for res in resultaten}
