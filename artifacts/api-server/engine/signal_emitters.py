"""
Signal-emitters per engine (masterprompt §7-§8).

Elke emitter leest de meest recente engine-resultaten en publiceert
gestandaardiseerde IntelligenceSignals via engine.signal_publisher.
Deze functies worden aangeroepen aan het einde van elke engine-run en
gebundeld via emit_all_signals() (POST /api/signals/refresh).

Regels:
- Elk signaal heeft explanation, evidence, sources, confidence, model_version
- Per emitter een bovengrens per signaaltype zodat het overzicht bruikbaar
  blijft (topprioriteiten, geen duizenden rijen)
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from engine.signal_publisher import publish_signal, expire_stale_signals

logger = logging.getLogger(__name__)

MODEL_VERSION = "signals-v1.0.0"
MAX_PER_TYPE = 25


def _f(v) -> float | None:
    return float(v) if v is not None else None


# ── Competition ──────────────────────────────────────────────────────────────

def emit_competition_signals(db: Session) -> int:
    """Concurrentiedruk- en prijskanssignalen uit SkuCompetitionScore +
    ranking-verschuivingen uit CompetitorRanking."""
    n = 0
    scores = db.query(models.SkuCompetitionScore).all()
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}

    # Hoge concurrentiedruk: duurder dan de markt én sterke concurrentieklasse
    pressure = sorted(
        [s for s in scores if (s.price_index or 0) > 1.05
         and s.competition_class in ("Critical", "Strong")],
        key=lambda s: float(s.price_index or 1), reverse=True)[:MAX_PER_TYPE]
    for s in pressure:
        p = products.get(s.sku_id)
        pi = float(s.price_index)
        publish_signal(
            db, engine="competition", signal_type="competitive_pressure_increased",
            entity_type="sku", entity_id=s.sku_id,
            entity_name=p.product_name if p else s.sku_id,
            severity="high" if pi > 1.10 else "medium", direction="negative",
            metric="price_index", current_value=pi,
            change_pct=round((pi - 1) * 100, 2),
            confidence=min(0.9, 0.5 + 0.05 * (s.competitors_used or 0)),
            explanation=(
                f"Wij zijn {round((pi - 1) * 100, 1)}% duurder dan de referentieprijs van "
                f"{s.competitors_used or 0} relevante concurrenten, terwijl de concurrentieklasse "
                f"'{s.competition_class}' is (PCIS {round(float(s.pcis_score or 0), 2)}). "
                f"Dit verhoogt het risico op omzetverlies."),
            evidence={
                "price_index": pi,
                "pcis_score": _f(s.pcis_score),
                "competition_class": s.competition_class,
                "reference_price": _f(s.reference_price),
                "competitors_used": s.competitors_used,
                "competitors_excluded": s.competitors_excluded,
            },
            sources=["sku_competition_score", "fact_competitor_price_daily"],
            suggested_action="Prijspositie herzien voor deze SKU",
            model_version=MODEL_VERSION,
        )
        n += 1

    # Prijsverhogingskans: goedkoper dan de markt bij lage druk
    opportunity = sorted(
        [s for s in scores if (s.price_index or 1) < 0.95 and s.price_index],
        key=lambda s: float(s.price_index), reverse=False)[:MAX_PER_TYPE]
    for s in opportunity:
        p = products.get(s.sku_id)
        pi = float(s.price_index)
        publish_signal(
            db, engine="competition", signal_type="price_increase_opportunity",
            entity_type="sku", entity_id=s.sku_id,
            entity_name=p.product_name if p else s.sku_id,
            severity="medium" if pi < 0.90 else "low", direction="positive",
            metric="price_index", current_value=pi,
            change_pct=round((pi - 1) * 100, 2),
            confidence=min(0.85, 0.45 + 0.05 * (s.competitors_used or 0)),
            explanation=(
                f"Wij zijn {round((1 - pi) * 100, 1)}% goedkoper dan de referentieprijs van "
                f"{s.competitors_used or 0} concurrenten (klasse {s.competition_class or 'onbekend'}). "
                f"Er is ruimte voor een prijsverhoging zonder de concurrentiepositie te verliezen."),
            evidence={
                "price_index": pi,
                "pcis_score": _f(s.pcis_score),
                "competition_class": s.competition_class,
                "reference_price": _f(s.reference_price),
                "competitors_used": s.competitors_used,
            },
            sources=["sku_competition_score", "fact_competitor_price_daily"],
            suggested_action="Prijsverhoging overwegen voor deze SKU",
            model_version=MODEL_VERSION,
        )
        n += 1

    # Rankingverschuivingen (§11): concurrent stijgt in de overall ranking
    latest = db.query(func.max(models.CompetitorRanking.run_date)).scalar()
    if latest:
        movers = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.run_date == latest,
            models.CompetitorRanking.scope == "overall",
            models.CompetitorRanking.rank_trend == "up",
        ).order_by(models.CompetitorRanking.rank).limit(MAX_PER_TYPE).all()
        for r in movers:
            publish_signal(
                db, engine="competition", signal_type="competitor_rank_increased",
                entity_type="competitor", entity_id=r.competitor_name,
                entity_name=r.competitor_name,
                severity="medium" if (r.rank or 99) <= 3 else "low",
                direction="negative",
                current_value=float(r.rank), previous_value=_f(r.previous_rank),
                confidence=float(r.confidence or 0.5),
                explanation=(
                    f"{r.competitor_name} steeg van rank {r.previous_rank} naar {r.rank} in de "
                    f"overall concurrentranking (combined score {round(float(r.combined_score or 0), 2)}: "
                    f"relevance {round(float(r.competition_relevance_score or 0), 2)}, "
                    f"price relevance {round(float(r.price_relevance_score or 0), 2)}, "
                    f"influence {round(float(r.influence_score or 0), 2)})."),
                evidence=r.evidence or {"combined_score": _f(r.combined_score)},
                sources=["competitor_rankings", "competitor_influence_score", "category_competitor_relevance"],
                suggested_action="Concurrentprofiel en prijsbewegingen controleren",
                model_version=r.model_version or MODEL_VERSION,
            )
            n += 1
    return n


# ── Pricing ──────────────────────────────────────────────────────────────────

def emit_pricing_signals(db: Session) -> int:
    """Signalen uit de laatste pricing-engine-run (aanbevelingen van vandaag)."""
    latest = db.query(func.max(models.FactPricingRecommendationDaily.date)).scalar()
    if not latest:
        return 0
    recs = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.date == latest,
        models.FactPricingRecommendationDaily.approval_status == "pending",
    ).all()
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    n = 0

    for direction_label, sig_type, sev, dirn, subset in (
        ("verhoging", "price_increase_recommended", "medium", "positive",
         sorted([r for r in recs if (r.recommended_change_pct or 0) >= 2.0],
                key=lambda r: float(r.expected_margin_uplift or 0), reverse=True)[:MAX_PER_TYPE]),
        ("verlaging", "price_decrease_recommended", "medium", "negative",
         sorted([r for r in recs if (r.recommended_change_pct or 0) <= -2.0],
                key=lambda r: float(r.recommended_change_pct or 0))[:MAX_PER_TYPE]),
    ):
        for r in subset:
            p = products.get(r.sku_id)
            publish_signal(
                db, engine="pricing", signal_type=sig_type,
                entity_type="sku", entity_id=r.sku_id,
                entity_name=p.product_name if p else r.sku_id,
                severity=sev, direction=dirn,
                current_value=_f(r.current_price),
                expected_value=_f(r.recommended_price),
                change_pct=_f(r.recommended_change_pct),
                confidence=float(r.confidence_score or 0.5),
                explanation=(
                    f"De pricing engine adviseert een prijs{direction_label} van "
                    f"{round(float(r.recommended_change_pct or 0), 1)}% "
                    f"(van €{float(r.current_price or 0):.2f} naar €{float(r.recommended_price or 0):.2f}) "
                    f"op basis van strategie {r.strategy_type} (reden: {r.reason_code})."),
                evidence={
                    "strategy_type": r.strategy_type,
                    "reason_code": r.reason_code,
                    "expected_margin_uplift": _f(r.expected_margin_uplift),
                    "expected_revenue": _f(r.expected_revenue),
                    "safety_status": r.safety_status,
                },
                sources=["fact_pricing_recommendation_daily"],
                suggested_action=f"Prijsaanbeveling beoordelen ({r.strategy_type})",
                model_version=r.model_version or MODEL_VERSION,
            )
            n += 1
    return n


# ── BCG ──────────────────────────────────────────────────────────────────────

def emit_bcg_signals(db: Session) -> int:
    latest = db.query(func.max(models.FactBcgClassificationDaily.date)).filter(
        models.FactBcgClassificationDaily.entity_type == "SKU").scalar()
    if not latest:
        return 0
    rows = db.query(models.FactBcgClassificationDaily).filter(
        models.FactBcgClassificationDaily.entity_type == "SKU",
        models.FactBcgClassificationDaily.date == latest,
    ).all()
    n = 0

    stars = sorted([r for r in rows if r.hybrid_bcg_class == "PRICING_POWER_STAR"],
                   key=lambda r: float(r.pricing_power_score or 0), reverse=True)[:MAX_PER_TYPE]
    for r in stars:
        pps = float(r.pricing_power_score or 0)
        publish_signal(
            db, engine="bcg", signal_type="pricing_power_high",
            entity_type="sku", entity_id=r.entity_id, entity_name=r.entity_name,
            severity="medium" if pps >= 0.75 else "low", direction="positive",
            current_value=pps, confidence=float(r.confidence_score or 0.6),
            explanation=(
                f"{r.entity_name} is een Pricing Power Ster (score {pps:.2f}) met lage externe "
                f"concurrentiedruk (CSS {round(float(r.css_external_score or 0), 2)}). "
                f"Strategie: {r.pricing_strategy}. Er is ruimte om marge te pakken."),
            evidence={
                "pricing_power_score": pps,
                "css_external_score": _f(r.css_external_score),
                "ibss_score": _f(r.ibss_score),
                "gps_score": _f(r.gps_score),
                "hybrid_bcg_class": r.hybrid_bcg_class,
                "pricing_strategy": r.pricing_strategy,
            },
            sources=["fact_bcg_classification_daily"],
            suggested_action="Prijsverhoging testen (pricing power)",
            model_version=MODEL_VERSION,
        )
        n += 1

    dogs = sorted([r for r in rows if r.hybrid_bcg_class == "LOW_PRIORITY_DOG"],
                  key=lambda r: float(r.gps_score or 0))[:MAX_PER_TYPE]
    for r in dogs:
        publish_signal(
            db, engine="bcg", signal_type="sku_low_priority_dog",
            entity_type="sku", entity_id=r.entity_id, entity_name=r.entity_name,
            severity="low", direction="negative",
            current_value=_f(r.gps_score), confidence=float(r.confidence_score or 0.6),
            explanation=(
                f"{r.entity_name} is geclassificeerd als Lage Prioriteit Dog "
                f"(groei {round(float(r.gps_score or 0), 2)}, interne bijdrage "
                f"{round(float(r.ibss_score or 0), 2)}). Overweeg automatisering of sanering."),
            evidence={
                "gps_score": _f(r.gps_score),
                "ibss_score": _f(r.ibss_score),
                "hybrid_bcg_class": r.hybrid_bcg_class,
                "pricing_strategy": r.pricing_strategy,
            },
            sources=["fact_bcg_classification_daily"],
            suggested_action="Automatiseren of assortiment heroverwegen",
            model_version=MODEL_VERSION,
        )
        n += 1
    return n


# ── Traffic ──────────────────────────────────────────────────────────────────

def emit_traffic_signals(db: Session) -> int:
    from engine.conversion_monitoring import SIGNAL_LABELS_NL, SIGNAL_PRIORITY
    latest = db.query(func.max(models.FactTrafficIntelligenceDaily.date)).filter(
        models.FactTrafficIntelligenceDaily.entity_type == "SKU").scalar()
    if not latest:
        return 0
    rows = db.query(models.FactTrafficIntelligenceDaily).filter(
        models.FactTrafficIntelligenceDaily.entity_type == "SKU",
        models.FactTrafficIntelligenceDaily.date == latest,
        models.FactTrafficIntelligenceDaily.reason_code.isnot(None),
        models.FactTrafficIntelligenceDaily.reason_code != "NO_SIGNAL",
    ).all()
    rows.sort(key=lambda r: (float(r.conversion_risk_score or 0)
                             + float(r.traffic_opportunity_score or 0)), reverse=True)
    sev_map = {"hoog": "high", "gemiddeld": "medium", "laag": "low"}
    n = 0
    for r in rows[:MAX_PER_TYPE * 2]:
        code = r.reason_code or ""
        prio = SIGNAL_PRIORITY.get(code, "laag")
        growth = float(r.traffic_growth or 0)
        positive = code in ("TRAFFIC_OPPORTUNITY_HIGH", "PROMOTION_NEEDED_FOR_TRAFFIC")
        publish_signal(
            db, engine="traffic", signal_type=code.lower(),
            entity_type="sku", entity_id=r.entity_id, entity_name=r.entity_name,
            severity=sev_map.get(prio, "low"),
            direction="positive" if positive else "negative",
            current_value=float(r.conversion_risk_score or 0) if not positive
            else float(r.traffic_opportunity_score or 0),
            change_pct=round(growth * 100, 2),
            confidence=0.7 if prio == "hoog" else 0.55,
            explanation=(r.explanation_nl or SIGNAL_LABELS_NL.get(code, code))
            + f" (traffic {round(growth * 100, 1):+}%, conversietrend "
              f"{round(float(r.conversion_trend or 0) * 100, 1):+}%).",
            evidence={
                "reason_code": code,
                "demand_signal_score": _f(r.demand_signal_score),
                "conversion_health_score": _f(r.conversion_health_score),
                "traffic_opportunity_score": _f(r.traffic_opportunity_score),
                "conversion_risk_score": _f(r.conversion_risk_score),
                "search_gap_score": _f(r.search_gap_score),
                "traffic_growth": growth,
                "conversion_trend": _f(r.conversion_trend),
            },
            sources=["fact_traffic_intelligence_daily", "fact_traffic_daily"],
            suggested_action=SIGNAL_LABELS_NL.get(code, code),
            model_version=MODEL_VERSION,
        )
        n += 1
    return n


# ── Procurement / Supplier ───────────────────────────────────────────────────

def emit_procurement_signals(db: Session) -> int:
    latest = db.query(func.max(models.FactProcurementForecastDaily.date)).scalar()
    if not latest:
        return 0
    rows = db.query(models.FactProcurementForecastDaily).filter(
        models.FactProcurementForecastDaily.date == latest,
        models.FactProcurementForecastDaily.signal_code.in_(
            ("BUY_NOW", "URGENT_BUY", "MARGIN_RISK")),
    ).all()
    n = 0
    for r in sorted(rows, key=lambda x: float(x.future_margin_risk_score or 0)
                    + float(x.procurement_opportunity_score or 0), reverse=True)[:MAX_PER_TYPE * 2]:
        risk = r.signal_code == "MARGIN_RISK"
        publish_signal(
            db, engine="procurement", signal_type=(r.signal_code or "").lower(),
            entity_type="sku", entity_id=r.sku_id, entity_name=r.sku_name,
            severity="high" if r.signal_code == "URGENT_BUY" else "medium",
            direction="negative" if risk else "positive",
            current_value=float(r.future_margin_risk_score or 0) if risk
            else float(r.procurement_opportunity_score or 0),
            change_pct=_f(r.price_change_pct_90d),
            confidence=0.65,
            explanation=(
                f"{r.signal_label_nl or r.signal_code}: verwachte inkoopprijswijziging "
                f"{round(float(r.price_change_pct_90d or 0), 1)}% in 90 dagen "
                f"(POS {round(float(r.procurement_opportunity_score or 0), 2)}, "
                f"FMR {round(float(r.future_margin_risk_score or 0), 2)}). "
                f"{r.recommended_action_nl or ''}").strip(),
            evidence={
                "signal_code": r.signal_code,
                "pos": _f(r.procurement_opportunity_score),
                "fmr": _f(r.future_margin_risk_score),
                "price_change_pct_30d": _f(r.price_change_pct_30d),
                "price_change_pct_90d": _f(r.price_change_pct_90d),
                "recommended_order_qty": r.recommended_order_qty,
                "lead_time_days": r.lead_time_days,
            },
            sources=["fact_procurement_forecast_daily"],
            suggested_action=r.recommended_action_nl,
            model_version=MODEL_VERSION,
        )
        n += 1
    return n


# ── Switching / Huismerk ─────────────────────────────────────────────────────

def emit_switching_signals(db: Session) -> int:
    latest = db.query(func.max(models.InternalCompetitionScore.run_date)).scalar()
    if not latest:
        return 0
    rows = db.query(models.InternalCompetitionScore).filter(
        models.InternalCompetitionScore.run_date == latest,
    ).order_by(models.InternalCompetitionScore.isv.desc()).limit(MAX_PER_TYPE).all()
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    n = 0
    for r in rows:
        prob = float(r.internal_switch_probability or 0)
        if prob < 0.25:
            continue
        p = products.get(r.sku_id)
        publish_signal(
            db, engine="switching", signal_type="cannibalisation_risk",
            entity_type="sku", entity_id=r.sku_id,
            entity_name=p.product_name if p else r.sku_id,
            severity="high" if prob >= 0.5 else "medium",
            direction="neutral",
            metric="switch_probability", current_value=round(prob, 3),
            confidence=0.6,
            explanation=(
                f"Kannibalisatierisico {round(prob * 100)}%: klanten van dit A-merk kunnen "
                f"overstappen naar huismerk {r.paired_sku_id} "
                f"(margekloof {round(float(r.internal_margin_gap or 0), 2)}, "
                f"ISV {round(float(r.isv or 0), 2)}). Aanbevolen: {r.recommended_internal_action}."),
            evidence={
                "paired_sku_id": r.paired_sku_id,
                "internal_switch_probability": prob,
                "internal_margin_gap": _f(r.internal_margin_gap),
                "isv": _f(r.isv),
                "a_brand_price": _f(r.a_brand_price),
                "private_label_price": _f(r.private_label_price),
                "recommended_internal_action": r.recommended_internal_action,
            },
            sources=["internal_competition_scores"],
            suggested_action=r.recommended_internal_action,
            model_version=MODEL_VERSION,
        )
        n += 1
    return n


# ── Cost / Economic / Break-even ─────────────────────────────────────────────

def emit_cost_signals(db: Session) -> int:
    latest = db.query(func.max(models.FactCostDaily.date)).scalar()
    n = 0
    if latest:
        rows = db.query(models.FactCostDaily).filter(
            models.FactCostDaily.date == latest,
            models.FactCostDaily.net_margin_pct.isnot(None),
        ).order_by(models.FactCostDaily.net_margin_pct).limit(MAX_PER_TYPE).all()
        for r in rows:
            nm = float(r.net_margin_pct or 0)
            if nm >= 5:
                continue
            below_be = nm <= 0
            publish_signal(
                db, engine="cost", signal_type="below_break_even" if below_be else "margin_under_pressure",
                entity_type="sku", entity_id=r.sku_id, entity_name=r.sku_name,
                severity="critical" if below_be else "high",
                direction="negative",
                metric="gross_margin_pct", current_value=round(nm, 2),
                confidence=0.75,
                explanation=(
                    (f"Nettomarge is {round(nm, 1)}% — deze SKU verkoopt onder break-even "
                     if below_be else
                     f"Nettomarge is met {round(nm, 1)}% zeer dun ")
                    + f"bij verkoopprijs €{float(r.selling_price or 0):.2f} en totale kosten "
                      f"€{float(r.total_cost or 0):.2f} (incl. indirecte kosten)."),
                evidence={
                    "net_margin_pct": nm,
                    "selling_price": _f(r.selling_price),
                    "total_cost": _f(r.total_cost),
                    "total_direct_cost": _f(r.total_direct_cost),
                    "total_indirect_cost": _f(r.total_indirect_cost),
                    "cost_signal": r.cost_signal,
                },
                sources=["fact_cost_daily"],
                suggested_action="Prijs verhogen of kostenstructuur aanpakken",
                model_version=MODEL_VERSION,
            )
            n += 1

    # Economische omgevingssignalen (shop-niveau)
    today = date.today()
    econ = db.query(models.FactEconomicSignalDaily).filter(
        models.FactEconomicSignalDaily.valid_until >= today,
    ).all()
    for e in econ[:MAX_PER_TYPE]:
        sev = "high" if float(e.severity_score or 0) >= 0.6 else "medium"
        publish_signal(
            db, engine="economic", signal_type=(e.signal_code or "economic_signal").lower(),
            entity_type="shop", entity_id="1", entity_name=e.signal_name,
            severity=sev, direction="negative" if (e.margin_impact_pct or 0) < 0 else "neutral",
            current_value=_f(e.current_value), previous_value=_f(e.baseline_value),
            change_pct=_f(e.change_pct),
            confidence=float(e.severity_score or 0.5),
            explanation=e.description_nl or e.signal_name or "Economisch signaal",
            evidence={
                "signal_type": e.signal_type,
                "region": e.region,
                "pricing_impact_pct": _f(e.pricing_impact_pct),
                "margin_impact_pct": _f(e.margin_impact_pct),
                "affected_categories": e.affected_categories_json,
                "procurement_urgency": e.procurement_urgency,
            },
            sources=["fact_economic_signal_daily"],
            suggested_action=e.recommended_action_nl,
            model_version=MODEL_VERSION,
        )
        n += 1
    return n


# ── Orkestratie ──────────────────────────────────────────────────────────────

EMITTERS = {
    "competition": emit_competition_signals,
    "pricing": emit_pricing_signals,
    "bcg": emit_bcg_signals,
    "traffic": emit_traffic_signals,
    "procurement": emit_procurement_signals,
    "switching": emit_switching_signals,
    "cost": emit_cost_signals,
}


def emit_for_engine(db: Session, engine_name: str) -> int:
    """Draai één emitter en commit. Fouten worden gelogd en doorgegooid."""
    fn = EMITTERS.get(engine_name)
    if not fn:
        return 0
    count = fn(db)
    db.commit()
    return count


def emit_all_signals(db: Session) -> dict[str, int]:
    """Draai alle emitters (incl. verse competitor rankings) en expireer
    verouderde signalen. Retourneert aantallen per engine."""
    from engine.competition_rankings import run_competitor_rankings

    results: dict[str, int] = {}
    try:
        results["rankings"] = run_competitor_rankings(db)
    except Exception:
        db.rollback()
        logger.exception("Competitor rankings berekening mislukt")
        results["rankings"] = -1

    for name, fn in EMITTERS.items():
        try:
            results[name] = fn(db)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Signal-emitter '%s' mislukt", name)
            results[name] = -1

    expired = expire_stale_signals(db)
    db.commit()
    results["expired"] = expired
    return results
