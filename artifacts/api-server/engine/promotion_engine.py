"""
Promotion Intelligence Engine (§19) — historische promo-analyse.

Meet per promotie: uplift, break-even, incrementele omzet/marge,
cannibalisatie (verwante SKU's in dezelfde categorie) en halo
(basket-gerelateerde SKU's), met controlegroep waar mogelijk
(niet-gepromote SKU's in dezelfde categorie als marktbaseline).
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
PROMOTION_DEFAULT_CONFIG = {
    "min_baseline_days": 7,
    "marginal_uplift_threshold_pct": 5.0,  # net uplift boven deze grens = minimaal MARGINAAL
}


def _daily_stats(db: Session, sku_id: str, start: date, end: date, sid: int) -> Optional[dict]:
    """Gemiddelde per dag over [start, end] binnen één shop."""
    row = (
        db.query(
            func.count(models.FactSalesDaily.id),
            func.sum(models.FactSalesDaily.units_sold),
            func.sum(models.FactSalesDaily.revenue),
            func.sum(models.FactSalesDaily.margin),
        )
        .filter(
            models.FactSalesDaily.sku_id == sku_id,
            models.FactSalesDaily.shop_id == sid,
            models.FactSalesDaily.date >= start,
            models.FactSalesDaily.date <= end,
        )
        .first()
    )
    n_days = (end - start).days + 1
    if not row or not row[0]:
        return None
    return {
        "days": n_days,
        "units_per_day": float(row[1] or 0) / n_days,
        "revenue_per_day": float(row[2] or 0) / n_days,
        "margin_per_day": float(row[3] or 0) / n_days,
    }


def _category_units_per_day(db: Session, sku_ids: list[str], start: date, end: date, sid: int) -> float:
    if not sku_ids:
        return 0.0
    total = (
        db.query(func.sum(models.FactSalesDaily.units_sold))
        .filter(
            models.FactSalesDaily.sku_id.in_(sku_ids),
            models.FactSalesDaily.shop_id == sid,
            models.FactSalesDaily.date >= start,
            models.FactSalesDaily.date <= end,
        )
        .scalar()
    ) or 0
    return float(total) / max(1, (end - start).days + 1)


def analyze_promotion(db: Session, promo: models.Promotion, run_date: date, model_version: str,
                      sid: int, cfg: dict) -> Optional[models.FactPromotionEffect]:
    prod = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == promo.sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not prod:
        return None

    p_start = promo.start_date
    p_end = promo.end_date or min(date.today(), p_start + timedelta(days=13))
    if p_end < p_start:
        return None
    promo_days = (p_end - p_start).days + 1

    b_end = p_start - timedelta(days=1)
    b_start = b_end - timedelta(days=max(int(cfg["min_baseline_days"]), promo_days) - 1)

    baseline = _daily_stats(db, promo.sku_id, b_start, b_end, sid)
    during = _daily_stats(db, promo.sku_id, p_start, p_end, sid)
    if not baseline or not during or baseline["units_per_day"] <= 0:
        return None

    uplift_pct = (during["units_per_day"] - baseline["units_per_day"]) / baseline["units_per_day"] * 100
    incr_revenue = (during["revenue_per_day"] - baseline["revenue_per_day"]) * promo_days
    incr_margin = (during["margin_per_day"] - baseline["margin_per_day"]) * promo_days

    # Break-even: hoeveel extra eenheden nodig om de korting terug te verdienen
    price = float(prod.current_price or 0)
    cost = float(prod.cost_price or 0)
    if promo.promotion_type == "percentage_off":
        discount_eur = price * float(promo.discount_value or 0) / 100.0
    else:
        discount_eur = float(promo.discount_value or 0)
    promo_margin_unit = max(0.01, (price - discount_eur) - cost)
    margin_lost = discount_eur * baseline["units_per_day"] * promo_days
    break_even_units = margin_lost / promo_margin_unit if promo_margin_unit > 0 else 0
    extra_units_realized = (during["units_per_day"] - baseline["units_per_day"]) * promo_days
    break_even_achieved = extra_units_realized >= break_even_units

    # Controlegroep: niet-gepromote SKU's in dezelfde categorie
    promoted_now = {
        p.sku_id for p in db.query(models.Promotion).filter(
            models.Promotion.start_date <= p_end,
            (models.Promotion.end_date.is_(None)) | (models.Promotion.end_date >= p_start),
        ).all()
    }
    cat_skus = [
        p.sku_id for p in db.query(models.DimProduct).filter(
            models.DimProduct.category == prod.category,
            models.DimProduct.shop_id == sid,
            models.DimProduct.sku_id != promo.sku_id,
        ).all()
    ]
    control_skus = [s for s in cat_skus if s not in promoted_now]
    control_uplift = None
    if control_skus:
        ctl_base = _category_units_per_day(db, control_skus, b_start, b_end, sid)
        ctl_during = _category_units_per_day(db, control_skus, p_start, p_end, sid)
        if ctl_base > 0:
            control_uplift = (ctl_during - ctl_base) / ctl_base * 100
    net_uplift = uplift_pct - control_uplift if control_uplift is not None else uplift_pct

    # Cannibalisatie: afzetdaling bij verwante (categorie-)SKU's tijdens promo
    cannibalization = None
    if control_uplift is not None:
        cannibalization = round(max(0.0, -control_uplift), 2)

    # Halo: extra afzet bij basket-gerelateerde SKU's
    halo = None
    related = (
        db.query(models.BasketAssociation.consequent_sku)
        .filter(models.BasketAssociation.antecedent_sku == promo.sku_id,
                models.BasketAssociation.shop_id == sid)
        .limit(10).all()
    )
    related_skus = [r[0] for r in related]
    if related_skus:
        rel_base = _category_units_per_day(db, related_skus, b_start, b_end, sid)
        rel_during = _category_units_per_day(db, related_skus, p_start, p_end, sid)
        if rel_base > 0:
            halo = round((rel_during - rel_base) / rel_base * 100, 2)

    if incr_margin > 0 and break_even_achieved:
        verdict = "EFFECTIEF"
    elif incr_margin > 0 or net_uplift > float(cfg["marginal_uplift_threshold_pct"]):
        verdict = "MARGINAAL"
    else:
        verdict = "VERLIESGEVEND"

    confidence = min(1.0, 0.4
                     + (0.2 if baseline["days"] >= promo_days else 0.1)
                     + (0.2 if control_uplift is not None else 0.0)
                     + (0.2 if promo_days >= 7 else 0.1))

    explanation = (
        f"Promotie op {prod.product_name} ({p_start} t/m {p_end}): uplift {uplift_pct:+.1f}% "
        f"({'netto ' + format(net_uplift, '+.1f') + '% na controlegroep' if control_uplift is not None else 'geen controlegroep beschikbaar'}). "
        f"Incrementele marge €{incr_margin:,.2f}; break-even "
        f"{'gehaald' if break_even_achieved else 'NIET gehaald'} "
        f"({extra_units_realized:.0f} van {break_even_units:.0f} benodigde extra stuks). Oordeel: {verdict}."
    )

    effect = models.FactPromotionEffect(
        promotion_id=promo.id,
        shop_id=sid,
        sku_id=promo.sku_id,
        run_date=run_date,
        period_start=p_start,
        period_end=p_end,
        baseline_start=b_start,
        baseline_end=b_end,
        baseline_units_per_day=round(baseline["units_per_day"], 3),
        promo_units_per_day=round(during["units_per_day"], 3),
        baseline_revenue_per_day=round(baseline["revenue_per_day"], 4),
        promo_revenue_per_day=round(during["revenue_per_day"], 4),
        baseline_margin_per_day=round(baseline["margin_per_day"], 4),
        promo_margin_per_day=round(during["margin_per_day"], 4),
        uplift_pct=round(uplift_pct, 2),
        incremental_revenue=round(incr_revenue, 4),
        incremental_margin=round(incr_margin, 4),
        break_even_extra_units=round(break_even_units, 1),
        break_even_achieved=break_even_achieved,
        cannibalization_pct=cannibalization,
        halo_pct=halo,
        control_group_used=control_uplift is not None,
        control_group_size=len(control_skus),
        control_uplift_pct=round(control_uplift, 2) if control_uplift is not None else None,
        net_uplift_pct=round(net_uplift, 2),
        verdict=verdict,
        confidence=round(confidence, 2),
        explanation_nl=explanation,
        model_version=model_version,
    )
    db.add(effect)
    return effect


def run_promotion_engine(db: Session, run_date: date | None = None,
                         shop_id: int | None = None) -> Dict[str, Any]:
    run_date = run_date or date.today()
    sid = resolve_shop_id(db, shop_id)
    model = ensure_active_model(db, "promotion", description="Promotion Intelligence effectmodel",
                                default_config=PROMOTION_DEFAULT_CONFIG)
    cfg = get_active_config(db, "promotion", PROMOTION_DEFAULT_CONFIG)

    # Promotion heeft (nog) geen shop_id-kolom: scope via de producten van deze shop.
    shop_skus = {p[0] for p in db.query(models.DimProduct.sku_id).filter(
        models.DimProduct.shop_id == sid).all()}
    promos = [p for p in db.query(models.Promotion).order_by(models.Promotion.start_date).all()
              if p.sku_id in shop_skus]
    if not promos:
        record_run_metrics(db, "promotion", {"promotions": 0, "analyzed": 0, "status": "no_data",
                                             "shop_id": sid})
        db.commit()
        return {"promotions": 0, "analyzed": 0, "run_date": str(run_date), "shop_id": sid,
                "detail": "Geen promotiedata aanwezig (upload promoties)."}

    db.query(models.FactPromotionEffect).filter(
        models.FactPromotionEffect.run_date == run_date,
        models.FactPromotionEffect.shop_id == sid,
    ).delete(synchronize_session=False)

    analyzed = 0
    effects: list[models.FactPromotionEffect] = []
    for promo in promos:
        eff = analyze_promotion(db, promo, run_date, model.version, sid, cfg)
        if eff:
            analyzed += 1
            effects.append(eff)

    prods = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.shop_id == sid).all()}
    for eff in effects:
        if eff.verdict == "VERLIESGEVEND":
            sev, direction, action = "high", "negative", "Herhaal deze promotie niet in de huidige vorm"
            stype = "promotion_loss_making"
        elif eff.verdict == "EFFECTIEF":
            sev, direction, action = "info", "positive", "Overweeg deze effectieve promotie te herhalen"
            stype = "promotion_effective"
        else:
            continue
        prod = prods.get(eff.sku_id)
        publish_signal(
            db,
            shop_id=sid,
            engine="promotion",
            signal_type=stype,
            entity_type="sku",
            entity_id=eff.sku_id,
            entity_name=prod.product_name if prod else eff.sku_id,
            severity=sev,
            direction=direction,
            metric="gross_margin",
            current_value=float(eff.incremental_margin or 0),
            change_pct=float(eff.net_uplift_pct or 0),
            confidence=float(eff.confidence or 0),
            explanation=eff.explanation_nl,
            evidence={
                "promotion_id": eff.promotion_id,
                "uplift_pct": float(eff.uplift_pct or 0),
                "net_uplift_pct": float(eff.net_uplift_pct or 0),
                "incremental_margin": float(eff.incremental_margin or 0),
                "break_even_achieved": bool(eff.break_even_achieved),
                "control_group_size": eff.control_group_size,
            },
            sources=["promotions", "fact_sales_daily", "fact_promotion_effect"],
            suggested_action=action,
            model_version=model.version,
        )

    record_run_metrics(db, "promotion", {"promotions": len(promos), "analyzed": analyzed,
                                         "shop_id": sid})
    db.commit()
    return {"promotions": len(promos), "analyzed": analyzed, "run_date": str(run_date),
            "shop_id": sid}


def get_promotion_dashboard(db: Session, shop_id: int | None = None) -> Dict[str, Any]:
    sid = resolve_shop_id(db, shop_id)
    latest = db.query(func.max(models.FactPromotionEffect.run_date)).filter(
        models.FactPromotionEffect.shop_id == sid).scalar()
    if not latest:
        return {"run_date": None, "shop_id": sid, "totaal": 0, "effecten": [], "verdicts": {}}

    effects = (
        db.query(models.FactPromotionEffect)
        .filter(models.FactPromotionEffect.run_date == latest,
                models.FactPromotionEffect.shop_id == sid)
        .order_by(models.FactPromotionEffect.incremental_margin.desc())
        .all()
    )
    prods = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.shop_id == sid).all()}
    verdicts: Dict[str, int] = {}
    for e in effects:
        verdicts[e.verdict or "?"] = verdicts.get(e.verdict or "?", 0) + 1

    return {
        "run_date": str(latest),
        "shop_id": sid,
        "totaal": len(effects),
        "verdicts": verdicts,
        "totale_incrementele_marge": round(sum(float(e.incremental_margin or 0) for e in effects), 2),
        "totale_incrementele_omzet": round(sum(float(e.incremental_revenue or 0) for e in effects), 2),
        "met_controlegroep": sum(1 for e in effects if e.control_group_used),
        "effecten": [
            {
                "id": e.id,
                "promotion_id": e.promotion_id,
                "sku_id": e.sku_id,
                "naam": prods[e.sku_id].product_name if e.sku_id in prods else e.sku_id,
                "periode": f"{e.period_start} — {e.period_end}",
                "uplift_pct": float(e.uplift_pct or 0),
                "net_uplift_pct": float(e.net_uplift_pct or 0),
                "incrementele_omzet": float(e.incremental_revenue or 0),
                "incrementele_marge": float(e.incremental_margin or 0),
                "break_even_stuks": float(e.break_even_extra_units or 0),
                "break_even_gehaald": bool(e.break_even_achieved),
                "cannibalisatie_pct": float(e.cannibalization_pct) if e.cannibalization_pct is not None else None,
                "halo_pct": float(e.halo_pct) if e.halo_pct is not None else None,
                "controlegroep": bool(e.control_group_used),
                "controlegroep_grootte": e.control_group_size or 0,
                "oordeel": e.verdict,
                "confidence": float(e.confidence or 0),
                "toelichting": e.explanation_nl,
            }
            for e in effects
        ],
    }
