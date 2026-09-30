"""
Main pricing engine orchestrator.

For each SKU:
1. Load all relevant data (prices, sales, inventory, competitors, affinity)
2. Route to the correct strategy function based on strategy_type
3. Apply safety rules
4. Persist recommendations to fact_pricing_recommendation_daily
"""
import logging
from types import SimpleNamespace

import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
import models
from engine import strategies
from engine.safety_rules import apply_safety_rules
from engine.competitor_strategy_engine import analyseer_alle_concurrenten
from engine.model_governance import get_active_config
from engine.run_profiling import RunProfiler, check_slow_run

logger = logging.getLogger(__name__)

MODEL_VERSION = "v1.0.0"

# Default modelconfiguratie (governance §54). Drempel voor trage-run-bewaking
# van de volledige nachtelijke pricing-run (seconden); <= 0 schakelt uit.
PRICING_DEFAULT_CONFIG = {
    "slow_run_threshold_seconds": 60.0,
}


def _cfg(db: Session) -> dict:
    return get_active_config(db, "pricing", PRICING_DEFAULT_CONFIG)


def _py(v):
    """Zet numpy-scalars (numpy 2.x: repr = 'np.float64(...)') om naar native
    Python-getallen. psycopg2 kent numpy-typen niet en zou ze anders als
    letterlijke tekst in de SQL zetten ('np.float64(6.49)' → schema-fout)."""
    if isinstance(v, np.generic):
        return v.item()
    return v

# Aantal dagen prijshistorie dat wordt gebruikt om concurrentstrategieën te
# classificeren voordat de COMPETITOR_INDEX-strategie wordt gedraaid.
STRATEGY_LOOKBACK_DAYS = 30


def run_pricing_engine(db: Session, *, shop_id=None, sales_period=None,
                       model_version=MODEL_VERSION) -> tuple[int, int]:
    """
    Full model run: processes all active SKUs and writes recommendations.
    Returns (processed_count, skipped_count).
    """
    today = date.today()
    prof = RunProfiler("Pricing engine", logger)

    product_query = _shop_query(db, models.DimProduct, shop_id).filter(
        models.DimProduct.lifecycle_status != "discontinued")
    if shop_id is not None:
        product_query = product_query.with_for_update()
    products = prof.timed("load_products", product_query.all)

    # Preload all fact data into DataFrames for speed
    sales_df = prof.timed("load_sales", lambda: _load_sales(db, shop_id, sales_period))
    price_df = prof.timed("load_prices", lambda: _load_prices(db, shop_id))
    comp_df = prof.timed("load_competitor_prices", lambda: _load_competitor_prices(db, shop_id))
    inventory_df = prof.timed("load_inventory", lambda: _load_inventory(db, shop_id))
    basket_df = prof.timed("load_basket_affinity", lambda: _load_basket_affinity(db, shop_id))
    substitution_map = prof.timed("load_substitutions", lambda: _load_substitutions(db, shop_id))
    competitor_strategies = prof.timed("load_competitor_strategies",
                                       lambda: _load_competitor_strategies(db, shop_id))

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
    price_factors = {}
    if sales_period:
        # PriceShape stores current_price INCL VAT, DRS YTD EXCL VAT.
        # Never mutate the ORM catalog to normalize strategy inputs.
        normalized = []
        for p in products:
            factor = _drs_price_factor(p, sales_by.get(p.sku_id, empty_sales))
            price_factors[p.sku_id] = factor
            proxy = SimpleNamespace(**{c.key: getattr(p, c.key) for c in p.__table__.columns})
            if factor and p.cost_price is not None:
                proxy.cost_price = float(p.cost_price) * factor
            normalized.append(proxy)
        products = normalized

    # Verversingssemantiek: menselijke beslissingen (goedgekeurd/afgewezen) van
    # vandaag blijven behouden; openstaande (pending) aanbevelingen worden
    # opnieuw gegenereerd zodat een nieuwe modelrun na een feed-sync de laatste
    # prijzen weerspiegelt (delete-then-insert, net als de fact-tabellen).
    R = models.FactPricingRecommendationDaily
    existing_q = _shop_query(db, R, shop_id)
    if shop_id is None:
        existing_q = existing_q.filter(R.date == today)
    else:
        existing_q = existing_q.with_for_update()
    locked = {r.sku_id for r in existing_q.all()
              if r.approval_status != "pending" or r.override_price is not None
              or r.override_reason or r.source_decision_id is not None
              or r.processing_status not in (None, "niet_verwerkt")}
    _shop_query(db, R, shop_id).filter(
        models.FactPricingRecommendationDaily.date == today,
        models.FactPricingRecommendationDaily.approval_status == "pending",
        ~R.sku_id.in_(locked),
    ).delete(synchronize_session=False)
    if shop_id is None:
        db.commit()

    all_products = {p.sku_id: p for p in products}
    rec_maps: list[dict] = []
    processed, skipped = 0, 0

    def _generate_recommendations() -> None:
        nonlocal processed, skipped
        for product in products:
            try:
                if product.sku_id in locked:
                    skipped += 1
                    continue

                sku_inv = inv_by.get(product.sku_id, empty_inv)
                if sales_period and price_factors.get(product.sku_id) is None:
                    skipped += 1
                    continue  # unknown price VAT basis is not a valid margin input
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
                    "volume_days": (sales_period[1] - sales_period[0]).days + 1 if sales_period else None,
                }
                if sales_period:
                    factor = price_factors[product.sku_id]
                    # Portfolio comparisons can cross DRS (net) and PriceShape
                    # (gross) catalog items. Express substitutes in this advice's
                    # own price basis, without changing persisted product fields.
                    comparable = {}
                    for sku in context["substitutions"]:
                        other = all_products.get(sku)
                        other_factor = price_factors.get(sku)
                        if other and other_factor and other.current_price is not None:
                            comparable[sku] = SimpleNamespace(
                                current_price=float(other.current_price) / other_factor * factor)
                    context["all_products"] = comparable
                    competitors = context["competitors"]
                    if not competitors.empty:
                        vat = _observed_vat_factor(context["sales"])
                        if vat:
                            competitors = competitors[competitors["source"] == "priceshape"].copy()
                            competitors["price"] = competitors["price"] / vat * factor
                            context["competitors"] = competitors
                        else:
                            context["competitors"] = empty_comp

                # Route to strategy
                strategy = product.strategy_type or "MARGIN_OPTIMIZATION"
                result = _run_strategy(strategy, context)

                if result is None:
                    skipped += 1
                    continue

                # Apply safety rules
                result = apply_safety_rules(product, result, sku_inv)
                if sales_period:
                    # Guardrails can alter the price. Estimate the FINAL advice,
                    # using calendar days (including explicit zero-sales days).
                    sales = context["sales"]
                    factor = price_factors[product.sku_id]
                    cost, current = product.cost_price, product.current_price
                    if sales.empty or cost is None or current is None or float(cost) < 0 or sales["units_sold"].sum() < 0:
                        result.update(expected_units=None, expected_revenue=None,
                                      expected_margin=None, expected_margin_uplift=None)
                    else:
                        result.update(strategies._estimate_margin_uplift(
                            float(cost) / factor, float(current) / factor, result["recommended_price"] / factor,
                            strategies._avg_daily_units(context)))

                rec_maps.append({
                    "date": today,
                    "sku_id": product.sku_id,
                    "shop_id": product.shop_id,
                    "current_price": float(product.current_price) if product.current_price else None,
                    "recommended_price": _py(result["recommended_price"]),
                    "recommended_change_pct": _py(result["change_pct"]),
                    "expected_units": _py(result.get("expected_units")),
                    "expected_revenue": _py(result.get("expected_revenue")),
                    "expected_margin": _py(result.get("expected_margin")),
                    "expected_margin_uplift": _py(result.get("expected_margin_uplift")),
                    "confidence_score": _py(result["confidence"]),
                    "reason_code": result["reason_code"],
                    "strategy_type": strategy,
                    "competitor_strategy_signal": result.get("competitor_strategy_signal"),
                    "safety_status": result.get("safety_status", "ok"),
                    "approval_status": "pending",
                    "model_version": model_version,
                })
                processed += 1

            except Exception:
                if shop_id is not None:
                    raise  # no silent partial success in an explicit DRS run
                skipped += 1
                continue

    prof.timed("recommendations", _generate_recommendations)

    def _persist() -> None:
        for i in range(0, len(rec_maps), 5_000):
            db.bulk_insert_mappings(models.FactPricingRecommendationDaily, rec_maps[i:i + 5_000])
        if shop_id is None:
            db.commit()
        else:
            db.flush()

    prof.timed("persist", _persist)
    if shop_id is not None:
        # Caller publishes recommendations and durable run evidence atomically.
        return processed, skipped

    # Publiceer gestandaardiseerde IntelligenceSignals (§7-§8)
    from engine.signal_emitters import emit_for_engine
    prof.timed("signals", lambda: emit_for_engine(db, "pricing"))

    # Trage-run-bewaking: de pricing-run is altijd een volledige catalogus-run;
    # drempel configureerbaar via model-governance (model 'pricing').
    threshold = float(_cfg(db).get("slow_run_threshold_seconds",
                                   PRICING_DEFAULT_CONFIG["slow_run_threshold_seconds"]))
    if check_slow_run(db, prof, engine="pricing",
                      entity_name="Pricing Engine", run_date=today,
                      threshold_seconds=threshold, model_version=MODEL_VERSION):
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


def _shop_query(db, model, shop_id, sku_column=None):
    q = db.query(model)
    if shop_id is not None:
        if hasattr(model, "shop_id"):
            q = q.filter(model.shop_id == shop_id)
        else:
            col = sku_column if sku_column is not None else model.sku_id
            q = q.filter(col.in_(db.query(models.DimProduct.sku_id).filter(
                models.DimProduct.shop_id == shop_id)))
    return q


def _drs_price_factor(product, sales):
    source = (product.import_source or "").lower()
    if source == "drs":
        return 1.0
    return _observed_vat_factor(sales) if source == "priceshape" else None


def _observed_vat_factor(sales):
    if sales.empty or "revenue_incl_vat" not in sales or sales["revenue_incl_vat"].isna().any():
        return None
    net, gross = sales["revenue"].sum(), sales["revenue_incl_vat"].sum()
    if net <= 0 or gross < net:
        return None
    factor = float(gross / net)
    # Observed VAT conversion is an explicit forward-looking assumption.
    return factor if 1 <= factor <= 1.3 else None


def _load_sales(db: Session, shop_id=None, sales_period=None) -> pd.DataFrame:
    q = _shop_query(db, models.FactSalesDaily, shop_id)
    if sales_period:
        q = q.filter(models.FactSalesDaily.date.between(*sales_period),
                     models.FactSalesDaily.source == "DRS_DAILY")
    rows = q.all()
    data = [{
        "sku_id": r.sku_id,
        "date": r.date,
        "units_sold": r.units_sold or 0,
        "revenue": float(r.revenue) if r.revenue else 0,
        "revenue_incl_vat": float(r.revenue_incl_vat) if r.revenue_incl_vat is not None else float("nan"),
        "margin": float(r.margin) if r.margin else 0,
        "margin_pct": float(r.margin_pct) if r.margin_pct else 0,
    } for r in rows]
    if sales_period:
        from sqlalchemy import func
        C = models.SalesDailyClaim
        days = (sales_period[1] - sales_period[0]).days + 1
        complete = {r[0] for r in db.query(C.sku_id).filter(
            C.shop_id == shop_id, C.source == "DRS_DAILY", C.date.between(*sales_period)
        ).group_by(C.sku_id).having(func.count(C.id) == days)}
        data = [r for r in data if r["sku_id"] in complete]
        present = {r["sku_id"] for r in data}
        data.extend({"sku_id": sku, "date": sales_period[0], "units_sold": 0,
                     "revenue": 0, "revenue_incl_vat": 0, "margin": None, "margin_pct": None}
                    for sku in complete - present)
    return pd.DataFrame(data, columns=["sku_id", "date", "units_sold", "revenue",
                                      "revenue_incl_vat", "margin", "margin_pct"])


def _load_prices(db: Session, shop_id=None) -> pd.DataFrame:
    rows = _shop_query(db, models.FactPriceDaily, shop_id).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "price"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "price": float(r.price) if r.price else None,
    } for r in rows])


def _load_competitor_prices(db: Session, shop_id=None) -> pd.DataFrame:
    rows = _shop_query(db, models.FactCompetitorPriceDaily, shop_id).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "competitor_name", "price"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "competitor_name": r.competitor_name,
        "source": r.source,
        "price": float(r.price) if r.price else None,
    } for r in rows])


def _load_inventory(db: Session, shop_id=None) -> pd.DataFrame:
    rows = _shop_query(db, models.FactInventoryDaily, shop_id).all()
    if not rows:
        return pd.DataFrame(columns=["sku_id", "date", "stock_quantity", "days_of_stock"])
    return pd.DataFrame([{
        "sku_id": r.sku_id,
        "date": r.date,
        "stock_quantity": r.stock_quantity or 0,
        "days_of_stock": float(r.days_of_stock) if r.days_of_stock else None,
    } for r in rows])


def _load_basket_affinity(db: Session, shop_id=None) -> pd.DataFrame:
    rows = _shop_query(db, models.FactBasketAffinity, shop_id,
                       models.FactBasketAffinity.sku_id_a).all()
    if shop_id is not None:
        skus = {r[0] for r in db.query(models.DimProduct.sku_id).filter(models.DimProduct.shop_id == shop_id)}
        rows = [r for r in rows if r.sku_id_b in skus]
    if not rows:
        return pd.DataFrame(columns=["sku_id_a", "sku_id_b", "affinity_score"])
    return pd.DataFrame([{
        "sku_id_a": r.sku_id_a,
        "sku_id_b": r.sku_id_b,
        "affinity_score": float(r.affinity_score) if r.affinity_score else 0,
    } for r in rows])


def _load_substitutions(db: Session, shop_id=None) -> dict:
    rows = _shop_query(db, models.MapSubstitution, shop_id,
                       models.MapSubstitution.a_brand_sku).all()
    if shop_id is not None:
        skus = {r[0] for r in db.query(models.DimProduct.sku_id).filter(models.DimProduct.shop_id == shop_id)}
        rows = [r for r in rows if r.private_label_sku in skus]
    result = {}
    for r in rows:
        result.setdefault(r.a_brand_sku, []).append(r.private_label_sku)
        result.setdefault(r.private_label_sku, []).append(r.a_brand_sku)
    return result


def _load_competitor_strategies(db: Session, shop_id=None) -> dict[str, dict]:
    """
    Classificeer elke concurrent op basis van zijn prijshistorie van de
    afgelopen STRATEGY_LOOKBACK_DAYS dagen en geef een lookup terug van
    {concurrent_naam: classificatie-dict}. Deze signalen worden door de
    COMPETITOR_INDEX-strategie gebruikt om concurrenten te wegen.
    """
    since = date.today() - timedelta(days=STRATEGY_LOOKBACK_DAYS)
    rows = (
        _shop_query(db, models.FactCompetitorPriceDaily, shop_id)
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
