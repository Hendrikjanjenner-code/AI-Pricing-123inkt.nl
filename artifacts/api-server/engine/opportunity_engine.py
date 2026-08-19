"""
Opportunity Engine (§24) — centrale aggregator.

Normaliseert kansen uit alle engines (pricing, basket, promotion,
forecast_risk, competition/assortment) naar één opportunities-tabel met
expected value, revenue, margin, confidence, urgency, effort, risk,
supporting engines en een prioriteitsscore.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from engine.signal_publisher import publish_signal, resolve_shop_id
from engine.model_governance import ensure_active_model, record_run_metrics, get_active_config

URGENCY_W = {"low": 0.6, "medium": 0.8, "high": 1.0, "critical": 1.2}
EFFORT_W = {"low": 1.0, "medium": 0.8, "high": 0.6}
RISK_W = {"low": 1.0, "medium": 0.85, "high": 0.65}

# Default modelconfiguratie — vastgelegd per registry-versie (governance §54).
OPPORTUNITY_DEFAULT_CONFIG = {
    "pricing_limit": 50,
    "basket_limit": 25,
    "basket_min_lift": 1.2,
    "risk_signal_limit": 50,
    "pricing_high_urgency_uplift_eur": 500.0,
}


def _priority(ev: float, confidence: float, urgency: str, effort: str, risk: str, max_ev: float) -> float:
    base = (ev / max_ev) if max_ev > 0 else 0.0
    score = 100.0 * min(1.0, base) * max(0.1, confidence) \
        * URGENCY_W.get(urgency, 0.8) * EFFORT_W.get(effort, 0.8) * RISK_W.get(risk, 0.85)
    return round(min(100.0, score), 1)


def _collect(db: Session, model_version: str, run_date: date, sid: int, cfg: dict) -> list[dict]:
    opps: list[dict] = []
    prods = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.shop_id == sid).all()}

    # 1. Pricing: openstaande aanbevelingen met positieve verwachte marge-uplift
    latest_rec_date = db.query(func.max(models.FactPricingRecommendationDaily.date)).filter(
        models.FactPricingRecommendationDaily.shop_id == sid).scalar()
    if latest_rec_date:
        recs = (
            db.query(models.FactPricingRecommendationDaily)
            .filter(
                models.FactPricingRecommendationDaily.date == latest_rec_date,
                models.FactPricingRecommendationDaily.shop_id == sid,
                models.FactPricingRecommendationDaily.approval_status == "pending",
                models.FactPricingRecommendationDaily.expected_margin_uplift > 0,
            )
            .order_by(models.FactPricingRecommendationDaily.expected_margin_uplift.desc())
            .limit(int(cfg["pricing_limit"])).all()
        )
        for r in recs:
            uplift = float(r.expected_margin_uplift or 0)
            prod = prods.get(r.sku_id)
            opps.append(dict(
                source_engine="pricing", supporting_engines=["competition", "elasticity"],
                opportunity_type="price_change",
                entity_id=r.sku_id, entity_name=prod.product_name if prod else r.sku_id,
                title_nl=f"Prijsadvies: {float(r.current_price or 0):.2f} → {float(r.recommended_price or 0):.2f}",
                explanation_nl=(f"Openstaand prijsadvies ({r.reason_code or 'model'}) met verwachte "
                                f"marge-uplift van €{uplift:,.2f}."),
                expected_value_eur=uplift,
                expected_revenue_eur=float(r.expected_revenue or 0),
                expected_margin_eur=uplift,
                confidence=float(r.confidence_score or 0.5),
                urgency="high" if uplift > float(cfg["pricing_high_urgency_uplift_eur"]) else "medium",
                effort="low",
                risk="low" if (r.safety_status or "ok") == "ok" else "medium",
                evidence={"recommendation_id": r.id, "reason_code": r.reason_code,
                          "recommended_change_pct": float(r.recommended_change_pct or 0)},
            ))

    # 2. Basket: bundelkansen met hoge lift en marge
    latest_ba = db.query(func.max(models.BasketAssociation.run_date)).filter(
        models.BasketAssociation.shop_id == sid).scalar()
    if latest_ba:
        assocs = (
            db.query(models.BasketAssociation)
            .filter(
                models.BasketAssociation.run_date == latest_ba,
                models.BasketAssociation.shop_id == sid,
                models.BasketAssociation.lift >= float(cfg["basket_min_lift"]),
            )
            .order_by(models.BasketAssociation.bundle_margin_eur.desc())
            .limit(int(cfg["basket_limit"])).all()
        )
        for a in assocs:
            margin = float(a.bundle_margin_eur or 0)
            opps.append(dict(
                source_engine="basket", supporting_engines=["pricing"],
                opportunity_type="bundle",
                entity_id=a.antecedent_sku, entity_name=a.antecedent_name,
                title_nl=f"Bundel: {a.antecedent_name or a.antecedent_sku} + {a.consequent_name or a.consequent_sku}",
                explanation_nl=(f"Sterke associatie (lift {float(a.lift or 0):.2f}, "
                                f"{a.co_purchase_count or 0}× samen gekocht) met "
                                f"€{margin:.2f} marge per gecombineerd mandje."),
                expected_value_eur=margin * (a.co_purchase_count or 1),
                expected_revenue_eur=float(a.avg_basket_value or 0) * (a.co_purchase_count or 1),
                expected_margin_eur=margin * (a.co_purchase_count or 1),
                confidence=float(a.confidence or 0.5),
                urgency="medium", effort="medium", risk="low",
                evidence={"association_id": a.id, "lift": float(a.lift or 0),
                          "consequent_sku": a.consequent_sku,
                          "relation_type": a.relation_type},
            ))

    # 3. Promotion: effectieve promoties herhalen / verliesgevende stoppen
    latest_pe = db.query(func.max(models.FactPromotionEffect.run_date)).filter(
        models.FactPromotionEffect.shop_id == sid).scalar()
    if latest_pe:
        effects = (
            db.query(models.FactPromotionEffect)
            .filter(models.FactPromotionEffect.run_date == latest_pe,
                    models.FactPromotionEffect.shop_id == sid)
            .all()
        )
        for e in effects:
            prod = prods.get(e.sku_id)
            incr = float(e.incremental_margin or 0)
            if e.verdict == "EFFECTIEF" and incr > 0:
                opps.append(dict(
                    source_engine="promotion", supporting_engines=["basket", "forecast_risk"],
                    opportunity_type="promo_repeat",
                    entity_id=e.sku_id, entity_name=prod.product_name if prod else e.sku_id,
                    title_nl="Herhaal effectieve promotie",
                    explanation_nl=(f"Eerdere promotie leverde €{incr:,.2f} incrementele marge "
                                    f"(netto uplift {float(e.net_uplift_pct or 0):+.1f}%)."),
                    expected_value_eur=incr,
                    expected_revenue_eur=float(e.incremental_revenue or 0),
                    expected_margin_eur=incr,
                    confidence=float(e.confidence or 0.5),
                    urgency="medium", effort="medium", risk="low",
                    evidence={"promotion_effect_id": e.id, "net_uplift_pct": float(e.net_uplift_pct or 0)},
                ))
            elif e.verdict == "VERLIESGEVEND":
                opps.append(dict(
                    source_engine="promotion", supporting_engines=["pricing"],
                    opportunity_type="promo_stop",
                    entity_id=e.sku_id, entity_name=prod.product_name if prod else e.sku_id,
                    title_nl="Stop verliesgevende promotievorm",
                    explanation_nl=(f"Promotie kostte €{abs(incr):,.2f} marge zonder break-even; "
                                    f"niet herhalen in huidige vorm."),
                    expected_value_eur=abs(incr),
                    expected_revenue_eur=0.0,
                    expected_margin_eur=abs(incr),
                    confidence=float(e.confidence or 0.5),
                    urgency="high", effort="low", risk="low",
                    evidence={"promotion_effect_id": e.id, "verdict": e.verdict},
                ))

    # 4. Forecast & Risk: actieve risicosignalen als mitigatiekansen
    risk_signals = (
        db.query(models.IntelligenceSignal)
        .filter(
            models.IntelligenceSignal.engine == "forecast_risk",
            models.IntelligenceSignal.status == "active",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.severity.in_(["high", "critical"]),
        )
        .limit(int(cfg["risk_signal_limit"])).all()
    )
    for s in risk_signals:
        prod = prods.get(s.entity_id)
        # Waarde: 30 dagen marge van dit SKU als proxy voor wat op het spel staat
        margin_30 = 0.0
        fc = (
            db.query(models.FactForecastDaily)
            .filter(
                models.FactForecastDaily.sku_id == s.entity_id,
                models.FactForecastDaily.shop_id == sid,
                models.FactForecastDaily.forecast_type == "margin",
                models.FactForecastDaily.horizon_days == 30,
            )
            .order_by(models.FactForecastDaily.run_date.desc())
            .first()
        )
        if fc:
            margin_30 = max(0.0, float(fc.forecast_value or 0))
        opps.append(dict(
            source_engine="forecast_risk", supporting_engines=["forecast", "competition"],
            opportunity_type="risk_mitigation",
            entity_id=s.entity_id, entity_name=s.entity_name,
            title_nl=f"Mitigeer risico: {s.signal_type}",
            explanation_nl=s.explanation,
            expected_value_eur=margin_30,
            expected_revenue_eur=0.0,
            expected_margin_eur=margin_30,
            confidence=float(s.confidence or 0.5),
            urgency="critical" if s.severity == "critical" else "high",
            effort="medium", risk="medium",
            evidence={"signal_id": s.id, "signal_type": s.signal_type,
                      "suggested_action": s.suggested_action},
        ))

    return opps


def _warn_if_forecast_stale(db: Session, run_date: date, sid: int, model_version: str) -> bool:
    """
    Waarschuw (signaal + logging) als er voor `run_date` geen forecast-rijen
    bestaan terwijl er wél oudere forecast-data is. De opportunity-engine
    aggregeert dan kansen op basis van verouderde (T-2 of ouder) data.
    Retourneert True als de forecast-data verouderd is.
    """
    latest_fc = db.query(func.max(models.FactForecastDaily.run_date)).filter(
        models.FactForecastDaily.shop_id == sid).scalar()
    if latest_fc is not None and latest_fc >= run_date:
        # Verse data: los een eventueel nog actief stale-signaal op, zodat er
        # geen valse waarschuwing blijft staan na een succesvolle herstel-run.
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.engine == "opportunity",
            models.IntelligenceSignal.signal_type == "forecast_data_stale",
            models.IntelligenceSignal.status == "active",
        ).update({"status": "superseded"}, synchronize_session=False)
        return False

    if latest_fc is None:
        lag_days = None
        severity = "critical"
        explanation = (f"Er is nog geen enkele forecast-run voor deze shop; de "
                       f"forecast van vandaag ({run_date}) ontbreekt. De "
                       "opportunity-engine mist daardoor forecast-gedreven kansen.")
    else:
        lag_days = (run_date - latest_fc).days
        severity = "high" if lag_days == 1 else "critical"
        explanation = (f"De forecast-run van vandaag ({run_date}) ontbreekt; de meest "
                       f"recente forecast dateert van {latest_fc} ({lag_days} dag(en) oud). "
                       "De opportunity-engine aggregeert daardoor kansen op basis van "
                       "verouderde data.")

    publish_signal(
        db, shop_id=sid, engine="opportunity", signal_type="forecast_data_stale",
        entity_type="shop", entity_id=str(sid), entity_name="Forecast-data",
        severity=severity, direction="negative",
        metric="forecast_lag_days",
        current_value=float(lag_days) if lag_days is not None else None,
        expected_value=0.0,
        confidence=0.9,
        explanation=explanation,
        evidence={"expected_run_date": str(run_date),
                  "latest_forecast_run_date": str(latest_fc) if latest_fc else None,
                  "lag_days": lag_days},
        sources=["fact_forecast_daily"],
        suggested_action="Controleer de nachtelijke engine-run en herstart scheduled_engines.py",
        model_version=model_version,
    )
    return True


def run_opportunity_engine(db: Session, run_date: date | None = None,
                           shop_id: int | None = None) -> Dict[str, Any]:
    run_date = run_date or date.today()
    sid = resolve_shop_id(db, shop_id)
    model = ensure_active_model(db, "opportunity", description="Centrale opportunity-aggregator",
                                default_config=OPPORTUNITY_DEFAULT_CONFIG)
    cfg = get_active_config(db, "opportunity", OPPORTUNITY_DEFAULT_CONFIG)

    # Stale-data waakhond (taak 51): waarschuw als de forecast van vandaag
    # ontbreekt — dan aggregeert deze run kansen op basis van verouderde data.
    forecast_stale = _warn_if_forecast_stale(db, run_date, sid, model.version)

    raw = _collect(db, model.version, run_date, sid, cfg)

    # Elke run vervangt het volledige open portfolio van deze shop: eerdere
    # open kansen (van ELKE run_date) worden gearchiveerd als 'superseded',
    # zodat het dashboard nooit dubbele of verouderde open rijen toont.
    # Handmatige statussen (in_progress/done/dismissed) blijven bewaard.
    superseded = db.query(models.Opportunity).filter(
        models.Opportunity.shop_id == sid,
        models.Opportunity.status == "open",
    ).update({"status": "superseded"}, synchronize_session=False)

    max_ev = max((o["expected_value_eur"] for o in raw), default=0.0)
    created = 0
    top_priority = 0.0
    for o in raw:
        prio = _priority(o["expected_value_eur"], o["confidence"], o["urgency"], o["effort"], o["risk"], max_ev)
        top_priority = max(top_priority, prio)
        db.add(models.Opportunity(
            run_date=run_date,
            shop_id=sid,
            source_engine=o["source_engine"],
            supporting_engines=o["supporting_engines"],
            opportunity_type=o["opportunity_type"],
            entity_type="sku",
            entity_id=o["entity_id"],
            entity_name=o["entity_name"],
            title_nl=o["title_nl"],
            explanation_nl=o["explanation_nl"],
            expected_value_eur=round(o["expected_value_eur"], 4),
            expected_revenue_eur=round(o["expected_revenue_eur"], 4),
            expected_margin_eur=round(o["expected_margin_eur"], 4),
            confidence=round(o["confidence"], 2),
            urgency=o["urgency"], effort=o["effort"], risk=o["risk"],
            priority_score=prio,
            evidence=o["evidence"],
            model_version=model.version,
        ))
        created += 1

    if created:
        total_ev = round(sum(o["expected_value_eur"] for o in raw), 2)
        publish_signal(
            db, shop_id=sid, engine="opportunity", signal_type="opportunity_portfolio_updated",
            entity_type="shop", entity_id=str(sid), entity_name="Portfolio",
            severity="info", direction="positive",
            current_value=float(created), expected_value=total_ev,
            confidence=0.8,
            explanation=(f"Opportunity Engine identificeerde {created} kansen met een "
                         f"gecombineerde verwachte waarde van €{total_ev:,.2f}."),
            evidence={"opportunities": created, "total_expected_value_eur": total_ev,
                      "top_priority_score": top_priority},
            sources=["opportunities", "fact_pricing_recommendation_daily",
                     "basket_associations", "fact_promotion_effect", "intelligence_signals"],
            suggested_action="Beoordeel de top-kansen in het Opportunity-overzicht",
            model_version=model.version,
        )

    record_run_metrics(db, "opportunity", {"opportunities": created, "shop_id": sid,
                                           "superseded": int(superseded or 0)})
    db.commit()
    return {"opportunities": created, "superseded": int(superseded or 0),
            "run_date": str(run_date), "shop_id": sid,
            "forecast_stale": forecast_stale}


def get_opportunity_dashboard(db: Session, status: str = "open", limit: int = 200,
                              shop_id: int | None = None,
                              sku_filter: set | None = None) -> Dict[str, Any]:
    sid = resolve_shop_id(db, shop_id)
    latest = db.query(func.max(models.Opportunity.run_date)).filter(
        models.Opportunity.shop_id == sid).scalar()
    q = db.query(models.Opportunity).filter(models.Opportunity.shop_id == sid)
    if status != "all":
        q = q.filter(models.Opportunity.status == status)
    # Globale filtercontext (taak #217): kansen zijn SKU-gedragen (entity_id);
    # None = geen filter, lege set = niets matcht.
    if sku_filter is not None:
        q = q.filter(models.Opportunity.entity_id.in_(list(sku_filter)))
    rows = q.order_by(models.Opportunity.priority_score.desc()).limit(limit).all()

    per_engine: Dict[str, int] = {}
    for o in rows:
        per_engine[o.source_engine] = per_engine.get(o.source_engine, 0) + 1

    return {
        "run_date": str(latest) if latest else None,
        "shop_id": sid,
        "totaal": len(rows),
        "per_engine": per_engine,
        "totale_verwachte_waarde": round(sum(float(o.expected_value_eur or 0) for o in rows), 2),
        "opportunities": [
            {
                "id": o.id,
                "bron_engine": o.source_engine,
                "ondersteunende_engines": o.supporting_engines or [],
                "type": o.opportunity_type,
                "sku_id": o.entity_id,
                "naam": o.entity_name,
                "titel": o.title_nl,
                "toelichting": o.explanation_nl,
                "verwachte_waarde": float(o.expected_value_eur or 0),
                "verwachte_omzet": float(o.expected_revenue_eur or 0),
                "verwachte_marge": float(o.expected_margin_eur or 0),
                "confidence": float(o.confidence or 0),
                "urgentie": o.urgency,
                "effort": o.effort,
                "risico": o.risk,
                "prioriteit": float(o.priority_score or 0),
                "status": o.status,
                "evidence": o.evidence or {},
            }
            for o in rows
        ],
    }
