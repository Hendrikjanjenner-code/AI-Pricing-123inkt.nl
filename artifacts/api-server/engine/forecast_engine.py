"""
Forecast & Risk Engine (§20).

Forecast: unit/revenue/margin/stock forecasts per SKU over 30/90 dagen op
basis van weekdag-seizoenspatronen + trend uit fact_sales_daily, met
betrouwbaarheidsinterval, factoren en modelversie.

Risk: risicosignalen (competitor, supplier, stock, margin, traffic, demand)
gepubliceerd als IntelligenceSignals.
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from engine.signal_publisher import publish_signal, resolve_shop_id
from engine.model_governance import ensure_active_model, record_run_metrics, get_active_config

# Default modelconfiguratie — vastgelegd per registry-versie (governance §54).
FORECAST_DEFAULT_CONFIG = {
    "history_days": 120,
    "min_history_days": 14,
    "horizons": [30, 90],
    "demand_trend_threshold_pct": -15.0,   # sterker dalend dan dit = demand-risico
    "price_index_risk_threshold": 1.10,    # prijsindex boven dit = competitor-risico
    "stock_days_high_severity": 14,        # minder dagen dekking dan dit = severity high
}


def _forecast_sku(rows: list, horizon: int, min_history_days: int = 14) -> Optional[dict]:
    """Seizoensnaïef forecast: weekdaggemiddelden × trendfactor."""
    if len(rows) < min_history_days:
        return None
    rows = sorted(rows, key=lambda r: r.date)
    n = len(rows)

    # Weekdagpatroon
    weekday_sum: Dict[int, float] = {}
    weekday_cnt: Dict[int, int] = {}
    for r in rows:
        wd = r.date.weekday()
        weekday_sum[wd] = weekday_sum.get(wd, 0.0) + float(r.units_sold or 0)
        weekday_cnt[wd] = weekday_cnt.get(wd, 0) + 1
    weekday_avg = {wd: weekday_sum[wd] / weekday_cnt[wd] for wd in weekday_sum}
    overall_avg = sum(float(r.units_sold or 0) for r in rows) / n

    # Trend: tweede helft vs eerste helft
    half = n // 2
    first = sum(float(r.units_sold or 0) for r in rows[:half]) / max(1, half)
    second = sum(float(r.units_sold or 0) for r in rows[half:]) / max(1, n - half)
    trend_ratio = (second / first) if first > 0 else 1.0
    trend_ratio = max(0.3, min(3.0, trend_ratio))
    span_days = max(1, (rows[-1].date - rows[0].date).days)
    trend_pct_30 = (trend_ratio - 1.0) * 100 * (30.0 / max(30.0, span_days / 2))

    # Revenue/marge per eenheid uit de historie
    total_units = sum(float(r.units_sold or 0) for r in rows) or 1.0
    rev_per_unit = sum(float(r.revenue or 0) for r in rows) / total_units
    margin_per_unit = sum(float(r.margin or 0) for r in rows) / total_units

    # Residu-variantie → betrouwbaarheidsband
    residuals = [float(r.units_sold or 0) - weekday_avg.get(r.date.weekday(), overall_avg) for r in rows]
    variance = sum(e * e for e in residuals) / n
    std = variance ** 0.5

    start = rows[-1].date + timedelta(days=1)
    units_total = 0.0
    for i in range(horizon):
        d = start + timedelta(days=i)
        base = weekday_avg.get(d.weekday(), overall_avg)
        drift = 1.0 + (trend_ratio - 1.0) * ((i + 1) / max(30.0, span_days / 2)) / 2
        units_total += max(0.0, base * drift)

    band = 1.28 * std * (horizon ** 0.5)  # ~80% interval
    cv = std / overall_avg if overall_avg > 0 else 1.0
    confidence = max(0.2, min(0.95, 0.9 - 0.3 * cv - (0.05 if horizon > 30 else 0.0)))

    seasonality = (max(weekday_avg.values()) / overall_avg) if overall_avg > 0 else 1.0
    return {
        "units": units_total,
        "units_lower": max(0.0, units_total - band),
        "units_upper": units_total + band,
        "rev_per_unit": rev_per_unit,
        "margin_per_unit": margin_per_unit,
        "trend_pct_30": trend_pct_30,
        "seasonality_factor": round(seasonality, 3),
        "confidence": round(confidence, 2),
        "avg_daily_units": overall_avg,
        "history_days": n,
    }


def run_forecast_engine(db: Session, run_date: date | None = None,
                        shop_id: int | None = None) -> Dict[str, Any]:
    run_date = run_date or date.today()
    sid = resolve_shop_id(db, shop_id)
    model = ensure_active_model(db, "forecast_risk", description="Seizoensnaïef forecast- en risicomodel",
                                default_config=FORECAST_DEFAULT_CONFIG)
    cfg = get_active_config(db, "forecast_risk", FORECAST_DEFAULT_CONFIG)
    min_hist = int(cfg["min_history_days"])

    since = run_date - timedelta(days=int(cfg["history_days"]))
    sales = (
        db.query(models.FactSalesDaily)
        .filter(models.FactSalesDaily.date >= since,
                models.FactSalesDaily.shop_id == sid)
        .all()
    )
    by_sku: Dict[str, list] = {}
    for r in sales:
        by_sku.setdefault(r.sku_id, []).append(r)

    products = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.shop_id == sid,
        models.DimProduct.is_active.isnot(False)).all()}

    db.query(models.FactForecastDaily).filter(
        models.FactForecastDaily.run_date == run_date,
        models.FactForecastDaily.shop_id == sid,
    ).delete(synchronize_session=False)

    forecast_count = 0
    risk_count = 0
    for sku_id, rows in by_sku.items():
        prod = products.get(sku_id)
        if not prod:
            continue
        for horizon in [int(h) for h in cfg["horizons"]]:
            fc = _forecast_sku(rows, horizon, min_hist)
            if not fc:
                continue
            factors = {
                "weekdag_seizoenspatroon": fc["seasonality_factor"],
                "trend_pct_per_30d": round(fc["trend_pct_30"], 2),
                "historie_dagen": fc["history_days"],
                "gem_dagafzet": round(fc["avg_daily_units"], 2),
            }
            common = dict(
                run_date=run_date, shop_id=sid, sku_id=sku_id, sku_name=prod.product_name,
                category=prod.category, horizon_days=horizon,
                trend_pct=round(fc["trend_pct_30"], 2),
                seasonality_factor=fc["seasonality_factor"],
                factors=factors, confidence=fc["confidence"],
                model_version=model.version,
            )
            db.add(models.FactForecastDaily(
                forecast_type="units", forecast_value=round(fc["units"], 1),
                lower_bound=round(fc["units_lower"], 1), upper_bound=round(fc["units_upper"], 1),
                **common))
            db.add(models.FactForecastDaily(
                forecast_type="revenue", forecast_value=round(fc["units"] * fc["rev_per_unit"], 2),
                lower_bound=round(fc["units_lower"] * fc["rev_per_unit"], 2),
                upper_bound=round(fc["units_upper"] * fc["rev_per_unit"], 2),
                **common))
            db.add(models.FactForecastDaily(
                forecast_type="margin", forecast_value=round(fc["units"] * fc["margin_per_unit"], 2),
                lower_bound=round(fc["units_lower"] * fc["margin_per_unit"], 2),
                upper_bound=round(fc["units_upper"] * fc["margin_per_unit"], 2),
                **common))
            stock_end = float(prod.stock_quantity or 0) - fc["units"]
            db.add(models.FactForecastDaily(
                forecast_type="stock", forecast_value=round(stock_end, 1),
                lower_bound=round(float(prod.stock_quantity or 0) - fc["units_upper"], 1),
                upper_bound=round(float(prod.stock_quantity or 0) - fc["units_lower"], 1),
                **common))
            forecast_count += 4

        # ── Risicodetectie per SKU (op 30-dagen forecast) ────────────────────
        fc30 = _forecast_sku(rows, 30, min_hist)
        if fc30:
            risk_count += _detect_sku_risks(db, prod, fc30, run_date, model.version, sid, cfg)

    record_run_metrics(db, "forecast_risk", {
        "skus": len(by_sku), "forecasts": forecast_count, "risk_signals": risk_count,
        "shop_id": sid,
    })
    db.commit()
    return {"skus": len(by_sku), "forecasts": forecast_count,
            "risk_signals": risk_count, "run_date": str(run_date), "shop_id": sid}


def _detect_sku_risks(db: Session, prod: models.DimProduct, fc30: dict, run_date: date,
                      model_version: str, sid: int, cfg: dict) -> int:
    count = 0
    sku = prod.sku_id
    name = prod.product_name
    sources = ["fact_sales_daily", "dim_product", "fact_forecast_daily"]

    # Stock-risico: verwachte vraag > voorraad
    stock = float(prod.stock_quantity or 0)
    if fc30["units"] > 0 and stock < fc30["units"]:
        days_left = stock / max(0.01, fc30["avg_daily_units"])
        publish_signal(
            db, shop_id=sid, engine="forecast_risk", signal_type="stock_risk",
            entity_type="sku", entity_id=sku, entity_name=name,
            severity="high" if days_left < float(cfg["stock_days_high_severity"]) else "medium",
            direction="negative",
            metric="days_of_stock", current_value=round(days_left, 1),
            expected_value=30.0, confidence=fc30["confidence"],
            explanation=(f"Voorraadrisico voor {name}: verwachte 30-dagenvraag is "
                         f"{fc30['units']:.0f} stuks maar voorraad is {stock:.0f} "
                         f"(~{days_left:.0f} dagen dekking)."),
            evidence={"stock": stock, "forecast_units_30d": round(fc30["units"], 1),
                      "days_of_stock": round(days_left, 1)},
            sources=sources, suggested_action="Bestel bij of verhoog de prijs om vraag te dempen",
            model_version=model_version)
        count += 1

    # Demand-risico: sterk dalende trend
    if fc30["trend_pct_30"] < float(cfg["demand_trend_threshold_pct"]):
        publish_signal(
            db, shop_id=sid, engine="forecast_risk", signal_type="demand_risk",
            entity_type="sku", entity_id=sku, entity_name=name,
            severity="medium", direction="negative", metric="units_sold",
            change_pct=round(fc30["trend_pct_30"], 1), confidence=fc30["confidence"],
            explanation=(f"Vraagrisico voor {name}: trend {fc30['trend_pct_30']:+.0f}% "
                         f"per 30 dagen op basis van {fc30['history_days']} dagen historie."),
            evidence={"trend_pct_30d": round(fc30["trend_pct_30"], 1),
                      "avg_daily_units": round(fc30["avg_daily_units"], 2)},
            sources=sources, suggested_action="Onderzoek prijs/concurrentie of plan afbouw",
            model_version=model_version)
        count += 1

    # Marge-risico: verwachte marge per eenheid nihil of negatief
    if fc30["margin_per_unit"] <= 0 and fc30["avg_daily_units"] > 0:
        publish_signal(
            db, shop_id=sid, engine="forecast_risk", signal_type="margin_risk",
            entity_type="sku", entity_id=sku, entity_name=name,
            severity="high", direction="negative", metric="gross_margin",
            current_value=round(fc30["margin_per_unit"], 2), confidence=fc30["confidence"],
            explanation=(f"Margerisico voor {name}: gerealiseerde marge per eenheid is "
                         f"€{fc30['margin_per_unit']:.2f} bij doorlopende verkoop."),
            evidence={"margin_per_unit": round(fc30["margin_per_unit"], 2)},
            sources=sources, suggested_action="Verhoog prijs of heronderhandel inkoopprijs",
            model_version=model_version)
        count += 1

    # Competitor-risico: prijsindex fors boven de markt
    score = (
        db.query(models.SkuCompetitionScore)
        .filter(models.SkuCompetitionScore.sku_id == sku)
        .order_by(models.SkuCompetitionScore.run_date.desc())
        .first()
    )
    if score and score.price_index and float(score.price_index) > float(cfg["price_index_risk_threshold"]):
        publish_signal(
            db, shop_id=sid, engine="forecast_risk", signal_type="competitor_risk",
            entity_type="sku", entity_id=sku, entity_name=name,
            severity="medium", direction="negative", metric="price_index",
            current_value=round(float(score.price_index), 3), expected_value=1.0,
            confidence=min(0.9, fc30["confidence"] + 0.1),
            explanation=(f"Concurrentierisico voor {name}: prijsindex "
                         f"{float(score.price_index):.2f} — wij zijn "
                         f"{(float(score.price_index) - 1) * 100:.0f}% duurder dan de referentie."),
            evidence={"price_index": float(score.price_index),
                      "competition_class": score.competition_class,
                      "pcis_score": float(score.pcis_score or 0)},
            sources=sources + ["sku_competition_score"],
            suggested_action="Beoordeel prijsaanpassing via de pricing engine",
            model_version=model_version)
        count += 1

    # Supplier-risico: lange levertijd bij lage voorraaddekking
    supplier = (
        db.query(models.FactSupplierData)
        .filter(models.FactSupplierData.sku_id == sku)
        .order_by(models.FactSupplierData.created_at.desc())
        .first()
    )
    if supplier and supplier.lead_time_days and fc30["avg_daily_units"] > 0:
        days_left = stock / max(0.01, fc30["avg_daily_units"])
        if supplier.lead_time_days > days_left:
            publish_signal(
                db, shop_id=sid, engine="forecast_risk", signal_type="supplier_risk",
                entity_type="sku", entity_id=sku, entity_name=name,
                severity="high", direction="negative", metric="days_of_stock",
                current_value=round(days_left, 1),
                expected_value=float(supplier.lead_time_days),
                confidence=fc30["confidence"],
                explanation=(f"Leveranciersrisico voor {name}: levertijd "
                             f"{supplier.lead_time_days} dagen overschrijdt de "
                             f"voorraaddekking van {days_left:.0f} dagen."),
                evidence={"lead_time_days": supplier.lead_time_days,
                          "days_of_stock": round(days_left, 1),
                          "supplier": supplier.supplier_name},
                sources=sources + ["fact_supplier_data"],
                suggested_action="Plaats nu een order bij de leverancier",
                model_version=model_version)
            count += 1

    return count


def get_forecast_dashboard(db: Session, horizon: int = 30, shop_id: int | None = None) -> Dict[str, Any]:
    sid = resolve_shop_id(db, shop_id)
    latest = db.query(func.max(models.FactForecastDaily.run_date)).filter(
        models.FactForecastDaily.shop_id == sid).scalar()
    if not latest:
        return {"run_date": None, "shop_id": sid, "horizon": horizon, "skus": [], "totalen": {}}

    rows = (
        db.query(models.FactForecastDaily)
        .filter(
            models.FactForecastDaily.run_date == latest,
            models.FactForecastDaily.shop_id == sid,
            models.FactForecastDaily.horizon_days == horizon,
        )
        .all()
    )
    per_sku: Dict[str, dict] = {}
    for r in rows:
        d = per_sku.setdefault(r.sku_id, {
            "sku_id": r.sku_id, "naam": r.sku_name, "categorie": r.category,
            "confidence": float(r.confidence or 0), "trend_pct": float(r.trend_pct or 0),
            "model_version": r.model_version, "factoren": r.factors or {},
        })
        d[r.forecast_type] = float(r.forecast_value or 0)
        d[f"{r.forecast_type}_laag"] = float(r.lower_bound or 0)
        d[f"{r.forecast_type}_hoog"] = float(r.upper_bound or 0)

    skus = sorted(per_sku.values(), key=lambda x: x.get("revenue", 0), reverse=True)
    risk_signals = (
        db.query(models.IntelligenceSignal)
        .filter(
            models.IntelligenceSignal.engine == "forecast_risk",
            models.IntelligenceSignal.status == "active",
            models.IntelligenceSignal.shop_id == sid,
        )
        .order_by(models.IntelligenceSignal.observed_at.desc())
        .limit(100)
        .all()
    )
    return {
        "run_date": str(latest),
        "shop_id": sid,
        "horizon": horizon,
        "totalen": {
            "units": round(sum(s.get("units", 0) for s in skus), 0),
            "revenue": round(sum(s.get("revenue", 0) for s in skus), 2),
            "margin": round(sum(s.get("margin", 0) for s in skus), 2),
            "skus_met_forecast": len(skus),
            "gem_confidence": round(sum(s["confidence"] for s in skus) / len(skus), 2) if skus else 0,
        },
        "skus": skus,
        "risico_signalen": [
            {
                "id": s.id, "type": s.signal_type, "severity": s.severity,
                "sku_id": s.entity_id, "naam": s.entity_name,
                "toelichting": s.explanation, "actie": s.suggested_action,
                "confidence": float(s.confidence or 0),
                "observed_at": s.observed_at.isoformat() if s.observed_at else None,
            }
            for s in risk_signals
        ],
    }
