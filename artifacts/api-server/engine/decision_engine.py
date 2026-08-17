"""
Commercial Decision & Impact Engine (§25).

Consumeert actieve IntelligenceSignals van alle engines en bouwt per entiteit
(SKU) meerdere scenario's (price increase/decrease/hold, promotion, loyalty
incentive, bundle, house-brand action, no action) met verwachte impact,
risico en confidence. Kiest een aanbevolen scenario met volledige
WHY-structuur (§51) en slaat alles op voor reconstructie (§53).

Faalveilig (§56): ontbrekende signalen of data leiden tot expliciete
"data unavailable"-vermeldingen, nooit tot een crash of stille aanname.
Human approval blijft verplicht — deze engine voert nooit iets uit.
"""
from datetime import date, datetime
from sqlalchemy.orm import Session
import models

DECISION_MODEL_VERSION = "decision-v1.0.0"
AI_PROPOSER = "decision-engine"
MAX_DECISIONS_PER_RUN = 50

# Standaard horizon voor impactschatting (dagen)
IMPACT_HORIZON_DAYS = 30

SCENARIO_LABELS = {
    "price_increase": "Prijsverhoging",
    "price_decrease": "Prijsverlaging",
    "price_hold": "Prijs handhaven",
    "promotion": "Promotie",
    "loyalty_incentive": "Loyalty-incentive",
    "bundle": "Bundel",
    "house_brand_action": "Huismerk-actie",
    "no_action": "Geen actie",
}


def _f(v, default=None):
    """Veilig naar float; None blijft None."""
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def run_decision_engine(db: Session, shop_id: int | None = None) -> dict:
    """
    Volledige run: verzamel actieve signalen, groepeer per SKU-entiteit,
    genereer per entiteit een Decision met scenario's en een aanbeveling.
    Bestaande draft/proposed beslissingen van vandaag voor dezelfde entiteit
    worden vervangen; menselijk beoordeelde beslissingen blijven staan.

    Shop-scoping: signalen, producten, verkoop, pricing-aanbevelingen en de
    beslissingen zelf zijn expliciet shop-scoped. Elasticiteit, basket-
    affiniteit en substitutierelaties hebben (nog) geen shop-kolom en gelden
    als globale referentiedata; ze worden per SKU opgezocht en een SKU hoort
    bij precies één shop, dus praktisch lekt hier geen cross-shop-bewijs.
    Returns {decisions_created, entities_skipped, data_gaps_total}.
    """
    from semantic_layer import _shop_scope
    sid = _shop_scope(db, shop_id)
    today = date.today()

    signals = (
        db.query(models.IntelligenceSignal)
        .filter(
            models.IntelligenceSignal.status == "active",
            models.IntelligenceSignal.shop_id == sid,
        )
        .order_by(models.IntelligenceSignal.observed_at.desc())
        .all()
    )

    # Groepeer signalen per SKU-entiteit
    per_entity: dict[str, list] = {}
    for s in signals:
        if s.entity_type == "sku":
            per_entity.setdefault(s.entity_id, []).append(s)

    # Menselijk behandelde beslissingen van vandaag niet overschrijven
    existing = db.query(models.Decision).filter(
        models.Decision.run_date == today,
        models.Decision.shop_id == sid,
    ).all()
    locked_entities = {d.entity_id for d in existing if d.status not in ("draft", "proposed")}

    # Verwijder oude draft/proposed beslissingen van vandaag (regenereren)
    stale = [d for d in existing if d.status in ("draft", "proposed")]
    for d in stale:
        db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id == d.id).delete(synchronize_session=False)
        db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id == d.id).delete(synchronize_session=False)
        db.delete(d)
    db.flush()

    # Rangschik entiteiten op signaal-zwaarte zodat de belangrijkste eerst komen
    sev_w = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}

    def entity_weight(sigs):
        return sum(sev_w.get(s.severity or "info", 1) for s in sigs)

    ranked = sorted(per_entity.items(), key=lambda kv: entity_weight(kv[1]), reverse=True)

    created, skipped, gaps_total = 0, 0, 0
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.shop_id == sid).all()
    }

    for entity_id, sigs in ranked[:MAX_DECISIONS_PER_RUN]:
        if entity_id in locked_entities:
            skipped += 1
            continue
        try:
            # Savepoint per entiteit (§56): één kapotte entiteit rolt alleen
            # haar eigen werk terug, nooit eerder aangemaakte beslissingen of
            # de opschoning van verouderde drafts.
            with db.begin_nested():
                decision, n_gaps = _build_decision(db, today, sid, entity_id, sigs, products.get(entity_id))
            if decision is None:
                skipped += 1
                continue
            created += 1
            gaps_total += n_gaps
        except Exception:
            # §56: één kapotte entiteit mag de run niet stoppen; de savepoint
            # heeft alleen deze entiteit teruggedraaid.
            skipped += 1
            continue

    db.commit()
    return {"decisions_created": created, "entities_skipped": skipped, "data_gaps_total": gaps_total}


def _build_decision(db: Session, today: date, sid: int, sku_id: str, sigs: list, product) -> tuple:
    """Bouw één Decision + scenario's voor een SKU. Returns (decision, n_gaps)."""
    ctx, gaps = _build_context(db, sid, sku_id, sigs, product)

    decision = models.Decision(
        shop_id=sid,
        run_date=today,
        entity_type="sku",
        entity_id=sku_id,
        entity_name=ctx["product_name"],
        title=f"Commerciële beslissing voor {ctx['product_name']}",
        signal_ids=[s.id for s in sigs],
        signal_snapshot=[_signal_snapshot(s) for s in sigs],
        data_gaps=gaps,
        status="proposed",
        proposed_by=AI_PROPOSER,
        ai_model_version=DECISION_MODEL_VERSION,
        model_version=DECISION_MODEL_VERSION,
    )
    db.add(decision)
    db.flush()

    scenarios = _generate_scenarios(ctx, sigs, gaps)
    if not scenarios:
        db.delete(decision)
        return None, 0

    best = max(scenarios, key=lambda s: s["score"])
    rows = []
    for sc in scenarios:
        row = models.DecisionScenario(
            decision_id=decision.id,
            scenario_type=sc["scenario_type"],
            label=SCENARIO_LABELS.get(sc["scenario_type"], sc["scenario_type"]),
            description=sc["description"],
            expected_units=sc.get("expected_units"),
            expected_revenue=sc.get("expected_revenue"),
            expected_margin=sc.get("expected_margin"),
            customer_impact=sc.get("customer_impact"),
            basket_impact=sc.get("basket_impact"),
            stock_impact=sc.get("stock_impact"),
            strategic_impact=sc.get("strategic_impact"),
            risk_level=sc.get("risk_level", "medium"),
            risk_notes=sc.get("risk_notes"),
            confidence=sc.get("confidence", 0.5),
            score=sc["score"],
            is_recommended=(sc is best),
            why_factors=sc.get("why_factors", []),
            why_sources=sc.get("why_sources", []),
            why_assumptions=sc.get("why_assumptions", []),
            why_calculations=sc.get("why_calculations", []),
            parameters=sc.get("parameters", {}),
        )
        db.add(row)
        rows.append(row)
    db.flush()

    rec_row = next(r for r in rows if r.is_recommended)
    decision.recommended_scenario_id = rec_row.id
    decision.confidence = rec_row.confidence
    decision.summary = (
        f"Aanbevolen: {rec_row.label} — {rec_row.description} "
        f"(confidence {rec_row.confidence:.0%}, {len(rows)} scenario's vergeleken)."
    )

    db.add(models.DecisionEvent(
        decision_id=decision.id,
        from_status=None,
        to_status="proposed",
        actor=AI_PROPOSER,
        actor_type="ai",
        note=f"Automatisch voorgesteld op basis van {len(sigs)} signalen; aanbevolen scenario: {rec_row.label}.",
        values_snapshot={
            "recommended_scenario": rec_row.scenario_type,
            "confidence": rec_row.confidence,
            "expected_margin": rec_row.expected_margin,
            "signal_count": len(sigs),
            "data_gaps": len(decision.data_gaps or []),
        },
    ))
    return decision, len(gaps)


def _signal_snapshot(s) -> dict:
    return {
        "id": s.id, "engine": s.engine, "signal_type": s.signal_type,
        "severity": s.severity, "direction": s.direction,
        "metric": s.metric, "current_value": s.current_value,
        "expected_value": s.expected_value, "change_pct": s.change_pct,
        "confidence": s.confidence, "explanation": s.explanation,
        "observed_at": str(s.observed_at) if s.observed_at else None,
    }


def _build_context(db: Session, sid: int, sku_id: str, sigs: list, product) -> tuple[dict, list[str]]:
    """Verzamel alle benodigde data; ontbrekende data → expliciete gap (§56)."""
    gaps: list[str] = []

    ctx = {
        "sku_id": sku_id,
        "product_name": product.product_name if product else sku_id,
        "current_price": _f(product.current_price) if product else None,
        "cost_price": _f(product.cost_price) if product else None,
        "min_price": _f(product.min_price) if product else None,
        "max_price": _f(product.max_price) if product else None,
        "is_private_label": bool(product.is_private_label) if product else False,
        "stock_quantity": product.stock_quantity if product else None,
    }
    if product is None:
        gaps.append("data unavailable: productstamdata (dim_product) ontbreekt voor deze SKU")
    if ctx["current_price"] is None:
        gaps.append("data unavailable: actuele verkoopprijs ontbreekt")
    if ctx["cost_price"] is None:
        gaps.append("data unavailable: kostprijs ontbreekt — marge-impact is een schatting")

    # Recente verkoop (30 dagen) voor baseline units/revenue/marge
    sales = (
        db.query(models.FactSalesDaily)
        .filter(
            models.FactSalesDaily.sku_id == sku_id,
            models.FactSalesDaily.shop_id == sid,
        )
        .order_by(models.FactSalesDaily.date.desc())
        .limit(IMPACT_HORIZON_DAYS)
        .all()
    )
    if sales:
        ctx["base_units"] = sum(r.units_sold or 0 for r in sales)
        ctx["base_revenue"] = sum(_f(r.revenue, 0.0) for r in sales)
        ctx["base_margin"] = sum(_f(r.margin, 0.0) for r in sales)
        ctx["sales_days"] = len(sales)
    else:
        ctx["base_units"] = ctx["base_revenue"] = ctx["base_margin"] = None
        ctx["sales_days"] = 0
        gaps.append("data unavailable: geen recente verkoophistorie — impactcijfers niet berekenbaar")

    # Signaalindex per engine voor snelle lookup
    by_engine: dict[str, list] = {}
    for s in sigs:
        by_engine.setdefault(s.engine, []).append(s)
    ctx["by_engine"] = by_engine

    # Laatste pricing-aanbeveling als anker voor prijs-scenario's
    rec = (
        db.query(models.FactPricingRecommendationDaily)
        .filter(
            models.FactPricingRecommendationDaily.sku_id == sku_id,
            models.FactPricingRecommendationDaily.shop_id == sid,
        )
        .order_by(models.FactPricingRecommendationDaily.date.desc())
        .first()
    )
    ctx["pricing_rec"] = rec
    if rec is None and "pricing" not in by_engine:
        gaps.append("data unavailable: geen pricing-aanbeveling of pricing-signaal beschikbaar")

    # Elasticiteit indien beschikbaar
    ctx["elasticity"] = None
    el = (
        db.query(models.SkuElasticity)
        .filter(models.SkuElasticity.sku_id == sku_id)
        .order_by(models.SkuElasticity.run_date.desc())
        .first()
    )
    if el is not None:
        ctx["elasticity"] = _f(el.own_price_elasticity)
    if ctx["elasticity"] is None:
        gaps.append("data unavailable: prijselasticiteit onbekend — aanname -1,5 gebruikt voor volume-effect")

    # Basket-affiniteit (voor bundel/basket-impact)
    affinities = (
        db.query(models.FactBasketAffinity)
        .filter(models.FactBasketAffinity.sku_id_a == sku_id)
        .order_by(models.FactBasketAffinity.affinity_score.desc())
        .limit(3)
        .all()
    )
    ctx["top_affinities"] = [
        {"sku_id": a.sku_id_b, "affinity_score": _f(a.affinity_score, 0.0)} for a in affinities
    ]
    if not affinities:
        gaps.append("data unavailable: geen basket-affiniteitsdata — basket-impact indicatief")

    # Substituties (huismerk-scenario)
    subs = db.query(models.MapSubstitution).filter(
        (models.MapSubstitution.a_brand_sku == sku_id)
        | (models.MapSubstitution.private_label_sku == sku_id)
    ).all()
    ctx["substitutions"] = subs

    return ctx, gaps


# ── Scenario-generatie ───────────────────────────────────────────────────────

DEFAULT_ELASTICITY = -1.5


def _impact_for_price_change(ctx: dict, change_pct: float) -> tuple:
    """
    Schat units/revenue/marge over IMPACT_HORIZON_DAYS bij een prijswijziging,
    met elasticiteit. Returns (units, revenue, margin, calculations, assumptions).
    """
    calcs, assumptions = [], []
    elasticity = ctx["elasticity"] if ctx["elasticity"] is not None else DEFAULT_ELASTICITY
    if ctx["elasticity"] is None:
        assumptions.append(f"Prijselasticiteit onbekend; standaardwaarde {DEFAULT_ELASTICITY} aangenomen.")

    base_units = ctx["base_units"]
    price = ctx["current_price"]
    cost = ctx["cost_price"]
    if base_units is None or price is None:
        return None, None, None, calcs, assumptions + [
            "Verkoophistorie of prijs ontbreekt: impact niet kwantificeerbaar (data unavailable)."
        ]

    volume_effect = elasticity * change_pct
    new_units = max(0.0, base_units * (1 + volume_effect))
    new_price = price * (1 + change_pct)
    revenue = new_units * new_price
    margin = new_units * (new_price - cost) if cost is not None else None

    calcs.append({
        "stap": "volume-effect",
        "formule": f"Δunits = elasticiteit ({elasticity:.2f}) × Δprijs ({change_pct:+.1%})",
        "resultaat": f"{volume_effect:+.1%} → {new_units:.0f} stuks per {IMPACT_HORIZON_DAYS} dagen",
    })
    calcs.append({
        "stap": "omzet",
        "formule": f"units ({new_units:.0f}) × nieuwe prijs (€{new_price:.2f})",
        "resultaat": f"€{revenue:,.0f}",
    })
    if margin is not None:
        calcs.append({
            "stap": "marge",
            "formule": f"units × (prijs €{new_price:.2f} − kostprijs €{cost:.2f})",
            "resultaat": f"€{margin:,.0f}",
        })
    else:
        assumptions.append("Kostprijs ontbreekt: marge niet berekenbaar (data unavailable).")
    return new_units, revenue, margin, calcs, assumptions


def _why_sources(sigs: list, engines: list[str] | None = None) -> list[dict]:
    out = []
    for s in sigs:
        if engines is None or s.engine in engines:
            out.append({"engine": s.engine, "signal_type": s.signal_type, "signal_id": s.id,
                        "confidence": s.confidence})
    if not out:
        out.append({"engine": None, "signal_type": None, "signal_id": None,
                    "note": "data unavailable: geen ondersteunende signalen voor dit scenario"})
    return out


def _signal_factors(sigs: list) -> list[dict]:
    return [{
        "factor": f"{s.engine}:{s.signal_type}",
        "waarde": s.current_value,
        "richting": s.direction or "neutral",
        "severity": s.severity,
    } for s in sigs]


def _avg_conf(sigs: list, fallback: float = 0.3) -> float:
    vals = [s.confidence for s in sigs if s.confidence is not None]
    return round(sum(vals) / len(vals), 3) if vals else fallback


def _generate_scenarios(ctx: dict, sigs: list, gaps: list[str]) -> list[dict]:
    """Genereer de §25-scenario's met impact, risico, confidence en WHY."""
    scenarios: list[dict] = []
    by_engine = ctx["by_engine"]
    rec = ctx["pricing_rec"]
    price = ctx["current_price"]

    pricing_sigs = by_engine.get("pricing", [])
    comp_sigs = by_engine.get("competition", [])
    all_factors = _signal_factors(sigs)
    common_assumptions = list(gaps)  # data gaps zijn expliciete aannames/vermeldingen

    # Richting uit pricing-aanbeveling of signalen
    rec_change = None
    if rec is not None and rec.recommended_change_pct is not None:
        rec_change = _f(rec.recommended_change_pct) / 100.0 if abs(_f(rec.recommended_change_pct, 0)) > 1 else _f(rec.recommended_change_pct)

    opportunity = any(s.signal_type in ("price_increase_opportunity", "price_increase_recommended", "pricing_power_high") for s in sigs)
    pressure = any(s.signal_type in ("competitive_pressure_increased", "price_decrease_recommended") for s in sigs)

    # 1. Prijsverhoging
    up_pct = rec_change if (rec_change and rec_change > 0) else 0.05
    units, revenue, margin, calcs, assum = _impact_for_price_change(ctx, up_pct)
    scenarios.append({
        "scenario_type": "price_increase",
        "description": f"Verhoog de prijs met {up_pct:.1%}" + (f" naar €{price * (1 + up_pct):.2f}" if price else ""),
        "expected_units": units, "expected_revenue": revenue, "expected_margin": margin,
        "customer_impact": "Licht negatief: hogere prijs kan prijsgevoelige klanten afschrikken",
        "basket_impact": _basket_note(ctx, "Hogere marge per basket; risico op lagere attach-rate"),
        "stock_impact": "Lagere doorloop; voorraad blijft langer liggen",
        "strategic_impact": "Versterkt marge; risico op marktaandeelverlies bij sterke concurrentie",
        "risk_level": "low" if opportunity else ("high" if pressure else "medium"),
        "risk_notes": "Concurrentiedruk actief — verhoging riskant" if pressure else "Signalen ondersteunen prijsruimte" if opportunity else None,
        "confidence": _avg_conf(pricing_sigs + comp_sigs),
        "score": _score(margin, ctx, base_bias=(0.15 if opportunity else -0.15 if pressure else 0.0)),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs, ["pricing", "competition", "bcg"]),
        "why_assumptions": common_assumptions + assum,
        "why_calculations": calcs,
        "parameters": {"change_pct": up_pct, "new_price": round(price * (1 + up_pct), 2) if price else None},
    })

    # 2. Prijsverlaging
    down_pct = rec_change if (rec_change and rec_change < 0) else -0.05
    units, revenue, margin, calcs, assum = _impact_for_price_change(ctx, down_pct)
    scenarios.append({
        "scenario_type": "price_decrease",
        "description": f"Verlaag de prijs met {abs(down_pct):.1%}" + (f" naar €{price * (1 + down_pct):.2f}" if price else ""),
        "expected_units": units, "expected_revenue": revenue, "expected_margin": margin,
        "customer_impact": "Positief: scherpere prijs verhoogt conversie en klanttevredenheid",
        "basket_impact": _basket_note(ctx, "Meer traffic kan cross-sell in de basket verhogen"),
        "stock_impact": "Snellere doorloop; let op voorraadtoereikendheid",
        "strategic_impact": "Verdedigt marktaandeel; drukt marge",
        "risk_level": "low" if pressure else "medium",
        "risk_notes": "Margedruk; alleen zinvol bij aantoonbare concurrentiedruk" if not pressure else None,
        "confidence": _avg_conf(pricing_sigs + comp_sigs),
        "score": _score(margin, ctx, base_bias=(0.15 if pressure else -0.1)),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs, ["pricing", "competition"]),
        "why_assumptions": common_assumptions + assum,
        "why_calculations": calcs,
        "parameters": {"change_pct": down_pct, "new_price": round(price * (1 + down_pct), 2) if price else None},
    })

    # 3. Prijs handhaven
    units, revenue, margin, calcs, assum = _impact_for_price_change(ctx, 0.0)
    scenarios.append({
        "scenario_type": "price_hold",
        "description": "Handhaaf de huidige prijs en monitor signalen",
        "expected_units": units, "expected_revenue": revenue, "expected_margin": margin,
        "customer_impact": "Neutraal: geen prijsverandering voor de klant",
        "basket_impact": "Neutraal",
        "stock_impact": "Ongewijzigde doorloop",
        "strategic_impact": "Stabiliteit; geen reactie op actieve signalen",
        "risk_level": "low",
        "risk_notes": None,
        "confidence": 0.6,
        "score": _score(margin, ctx, base_bias=0.0),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs),
        "why_assumptions": common_assumptions + assum + ["Baseline: huidige prestaties zetten door zonder wijziging."],
        "why_calculations": calcs,
        "parameters": {"change_pct": 0.0},
    })

    # 4. Promotie (tijdelijke korting, hogere elasticiteit)
    promo_pct = -0.10
    units, revenue, margin, calcs, assum = _impact_for_price_change(ctx, promo_pct)
    if units is not None:
        units *= 1.2  # promotie-uplift boven puur prijseffect
        revenue = revenue * 1.2 if revenue is not None else None
        margin = margin * 1.2 if margin is not None else None
        calcs = calcs + [{"stap": "promotie-uplift", "formule": "units × 1,2 (zichtbaarheid/actie-effect)", "resultaat": f"{units:.0f} stuks"}]
    scenarios.append({
        "scenario_type": "promotion",
        "description": "Tijdelijke promotie van 10% korting met actiecommunicatie",
        "expected_units": units, "expected_revenue": revenue, "expected_margin": margin,
        "customer_impact": "Positief: actiegevoel en traffic; risico op promo-gewenning",
        "basket_impact": _basket_note(ctx, "Promotie trekt baskets aan waarin dit product zit"),
        "stock_impact": "Sterk versnelde doorloop — geschikt bij overvoorraad",
        "strategic_impact": "Kortetermijn-volume; kan prijsperceptie beïnvloeden",
        "risk_level": "medium",
        "risk_notes": "Tijdelijk margeverlies; effect vervalt na actieperiode",
        "confidence": min(0.9, _avg_conf(sigs) + 0.05),
        "score": _score(margin, ctx, base_bias=(0.1 if _high_stock(ctx) else -0.05)),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs, ["pricing", "traffic", "competition"]),
        "why_assumptions": common_assumptions + assum + ["Promotie-uplift van 20% extra volume aangenomen bovenop het prijseffect."],
        "why_calculations": calcs,
        "parameters": {"discount_pct": 0.10, "duration_days": 14},
    })

    # 5. Loyalty-incentive
    base_margin = ctx["base_margin"]
    loyalty_margin = base_margin * 0.97 if base_margin is not None else None
    scenarios.append({
        "scenario_type": "loyalty_incentive",
        "description": "Bied extra loyaliteitspunten (3% van omzet) i.p.v. directe korting",
        "expected_units": ctx["base_units"] * 1.05 if ctx["base_units"] is not None else None,
        "expected_revenue": ctx["base_revenue"] * 1.05 if ctx["base_revenue"] is not None else None,
        "expected_margin": loyalty_margin,
        "customer_impact": "Positief voor leden: verhoogt retentie en herhaalaankopen",
        "basket_impact": "Leden kopen gemiddeld grotere baskets",
        "stock_impact": "Licht versnelde doorloop",
        "strategic_impact": "Bouwt klantwaarde op zonder prijsperceptie te schaden",
        "risk_level": "low",
        "risk_notes": "Puntenliability stijgt; effect afhankelijk van ledenaandeel",
        "confidence": _avg_conf(by_engine.get("loyalty", []), 0.4),
        "score": _score(loyalty_margin, ctx, base_bias=(0.1 if by_engine.get("loyalty") else -0.1)),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs, ["loyalty"]),
        "why_assumptions": common_assumptions + [
            "Aanname: +5% volume door loyalty-incentive, puntenkosten 3% van omzet.",
        ],
        "why_calculations": [{"stap": "marge", "formule": "basismarge × (1 − 0,03 puntenkosten)",
                              "resultaat": f"€{loyalty_margin:,.0f}" if loyalty_margin is not None else "data unavailable"}],
        "parameters": {"points_pct": 0.03},
    })

    # 6. Bundel (alleen zinvol met affiniteitsdata)
    aff = ctx["top_affinities"]
    bundle_margin = base_margin * 1.10 if (base_margin is not None and aff) else None
    scenarios.append({
        "scenario_type": "bundle",
        "description": (
            f"Bundel met sterk gerelateerde producten ({', '.join(a['sku_id'] for a in aff)})"
            if aff else "Bundel met gerelateerde producten (geen affiniteitsdata beschikbaar)"
        ),
        "expected_units": ctx["base_units"] * 1.08 if (ctx["base_units"] is not None and aff) else None,
        "expected_revenue": ctx["base_revenue"] * 1.12 if (ctx["base_revenue"] is not None and aff) else None,
        "expected_margin": bundle_margin,
        "customer_impact": "Positief: gemak en waargenomen voordeel",
        "basket_impact": "Direct hogere basketwaarde door gekoppelde verkoop",
        "stock_impact": "Verdeelt doorloop over bundelproducten",
        "strategic_impact": "Verhoogt ecosysteemwaarde van het assortiment",
        "risk_level": "medium" if aff else "high",
        "risk_notes": None if aff else "Geen affiniteitsdata — bundelkeuze zou giswerk zijn (data unavailable)",
        "confidence": (min(0.85, max(a["affinity_score"] for a in aff)) if aff else 0.2),
        "score": _score(bundle_margin, ctx, base_bias=(0.05 if aff else -0.4)),
        "why_factors": all_factors + [
            {"factor": f"basket-affiniteit met {a['sku_id']}", "waarde": a["affinity_score"], "richting": "positive"}
            for a in aff
        ],
        "why_sources": _why_sources(sigs, ["basket", "traffic"]),
        "why_assumptions": common_assumptions + ["Aanname: +8% volume en +12% omzet bij bundeling met top-affiniteitsproducten."],
        "why_calculations": [{"stap": "marge", "formule": "basismarge × 1,10 (bundelpremie)",
                              "resultaat": f"€{bundle_margin:,.0f}" if bundle_margin is not None else "data unavailable"}],
        "parameters": {"bundle_partners": [a["sku_id"] for a in aff]},
    })

    # 7. Huismerk-actie (alleen indien substitutierelatie bestaat)
    subs = ctx["substitutions"]
    if subs:
        hb_margin = base_margin * 1.15 if base_margin is not None else None
        partner = subs[0].private_label_sku if not ctx["is_private_label"] else subs[0].a_brand_sku
        scenarios.append({
            "scenario_type": "house_brand_action",
            "description": (
                f"Stuur actief op huismerk-alternatief {partner}" if not ctx["is_private_label"]
                else f"Positioneer dit huismerk scherper t.o.v. A-merk {partner}"
            ),
            "expected_units": ctx["base_units"] * 0.95 if ctx["base_units"] is not None else None,
            "expected_revenue": ctx["base_revenue"] * 0.97 if ctx["base_revenue"] is not None else None,
            "expected_margin": hb_margin,
            "customer_impact": "Neutraal tot positief: goedkoper alternatief beschikbaar",
            "basket_impact": "Substitutie binnen de basket; totale basketwaarde licht lager",
            "stock_impact": "Verschuift doorloop naar huismerk",
            "strategic_impact": "Verhoogt huismerkaandeel en structurele marge",
            "risk_level": "medium",
            "risk_notes": "Merkleverancier-relatie en klantperceptie bewaken",
            "confidence": _avg_conf(by_engine.get("switching", []), 0.45),
            "score": _score(hb_margin, ctx, base_bias=(0.1 if ctx["is_private_label"] is False else 0.0)),
            "why_factors": all_factors + [{"factor": "substitutierelatie", "waarde": len(subs), "richting": "positive"}],
            "why_sources": _why_sources(sigs, ["switching", "bcg"]),
            "why_assumptions": common_assumptions + ["Aanname: 15% margeverbetering door mix-shift naar huismerk, 5% volumeverlies op dit SKU."],
            "why_calculations": [{"stap": "marge", "formule": "basismarge × 1,15 (mix-shift)",
                                  "resultaat": f"€{hb_margin:,.0f}" if hb_margin is not None else "data unavailable"}],
            "parameters": {"substitution_partner": partner},
        })

    # 8. Geen actie
    scenarios.append({
        "scenario_type": "no_action",
        "description": "Geen actie ondernemen; signalen bewust negeren",
        "expected_units": ctx["base_units"],
        "expected_revenue": ctx["base_revenue"],
        "expected_margin": base_margin,
        "customer_impact": "Neutraal",
        "basket_impact": "Neutraal",
        "stock_impact": "Ongewijzigd",
        "strategic_impact": "Actieve signalen blijven onbeantwoord",
        "risk_level": "low" if not sigs else "medium",
        "risk_notes": f"{len(sigs)} actieve signalen blijven onbehandeld" if sigs else None,
        "confidence": 0.5,
        "score": _score(base_margin, ctx, base_bias=-0.2 if sigs else 0.0),
        "why_factors": all_factors,
        "why_sources": _why_sources(sigs),
        "why_assumptions": common_assumptions + ["Baseline zonder interventie."],
        "why_calculations": [],
        "parameters": {},
    })

    return scenarios


def _basket_note(ctx: dict, default: str) -> str:
    if not ctx["top_affinities"]:
        return "data unavailable: geen basket-affiniteitsdata"
    return default


def _high_stock(ctx: dict) -> bool:
    sq = ctx.get("stock_quantity")
    return sq is not None and sq > 100


def _score(margin, ctx: dict, base_bias: float = 0.0) -> float:
    """
    Rangschikkingsscore: relatieve marge t.o.v. baseline plus signaal-bias.
    Bij ontbrekende marge geldt alleen de bias (met malus voor onzekerheid).
    """
    base = ctx.get("base_margin")
    if margin is None:
        return round(base_bias - 0.25, 4)
    if base is None or base == 0:
        return round(base_bias + (0.1 if margin > 0 else -0.1), 4)
    rel = (margin - base) / abs(base)
    rel = max(-1.0, min(1.0, rel))
    return round(rel + base_bias, 4)
