"""
BCG Intelligence Engine — hoofdorchestrator.

Berekent per SKU:
1. GPS   — Growth Potential Score       (growth_scoring)
2. IBSS  — Internal Business Strength   (internal_bcg)
3. CSS_E — Competitive Strength Score   (external_bcg)
4. MOS   — Market Opportunity Score     (external_bcg)
5. PPS   — Pricing Power Score          (pricing_power_engine)
6. PLSV  — Private Label Value Score    (private_label_intelligence)

En daarna:
- internal_bcg_class
- external_bcg_class
- hybrid_bcg_class
- pricing_strategy
- strategic_priority

Resultaten worden opgeslagen in:
- fact_bcg_classification_daily  (één record per SKU per dag)
- fact_bcg_history               (alleen bij classificatiewijziging)
- fact_private_label_intelligence (alleen voor huismerk-SKU's)
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
import metrics
from engine.growth_scoring import calculate_growth_potential
from engine.internal_bcg import calculate_internal_business_strength, classify_internal_bcg
from engine.external_bcg import calculate_competitive_strength, calculate_market_opportunity, classify_external_bcg
from engine.hybrid_bcg import classify_hybrid_bcg
from engine.pricing_power_engine import calculate_pricing_power_score
from engine.private_label_intelligence import calculate_private_label_value, classify_private_label


def run_bcg_engine(db: Session) -> tuple[int, int]:
    """
    Voert de volledige BCG-berekening uit voor alle actieve SKU's.
    Returns: (processed_count, skipped_count)
    """
    today = date.today()
    lookback_90 = today - timedelta(days=90)

    products = db.query(models.DimProduct).filter(
        models.DimProduct.lifecycle_status != "discontinued"
    ).all()

    # ── Pre-load fact-tabellen ──────────────────────────────────────────────
    sales_rows = db.query(models.FactSalesDaily).filter(
        models.FactSalesDaily.date >= lookback_90
    ).all()

    pcis_rows = db.query(models.SkuCompetitionScore).all()
    pcis_map: dict[str, models.SkuCompetitionScore] = {r.sku_id: r for r in pcis_rows}

    cis_rows = db.query(models.CompetitorInfluenceScore).all()
    cis_map: dict[str, list] = {}
    for r in cis_rows:
        cis_map.setdefault(r.sku_id, []).append(r)

    elasticity_rows = db.query(models.SkuElasticity).all()
    elast_map: dict[str, models.SkuElasticity] = {r.sku_id: r for r in elasticity_rows}

    isv_rows = db.query(models.InternalCompetitionScore).all()
    isv_map: dict[str, models.InternalCompetitionScore] = {r.sku_id: r for r in isv_rows}

    basket_rows = db.query(models.FactBasketAffinity).all()
    basket_map: dict[str, float] = {}
    for r in basket_rows:
        basket_map[r.sku_id_a] = max(basket_map.get(r.sku_id_a, 0.0), float(r.affinity_score or 0))

    subst_rows = db.query(models.MapSubstitution).all()
    # A-merk → huismerk SKU
    abrand_to_pl: dict[str, str] = {r.a_brand_sku: r.private_label_sku for r in subst_rows}
    # Huismerk → A-merk SKU
    pl_to_abrand: dict[str, str] = {r.private_label_sku: r.a_brand_sku for r in subst_rows}

    product_map: dict[str, models.DimProduct] = {p.sku_id: p for p in products}

    # Totalen voor normalisatie
    total_revenue = sum(float(s.revenue or 0) for s in sales_rows)
    total_margin = sum(float(s.margin or 0) for s in sales_rows)

    processed, skipped = 0, 0

    for product in products:
        try:
            # Skip als er al een record bestaat voor vandaag
            existing = db.query(models.FactBcgClassificationDaily).filter_by(
                date=today,
                entity_type="SKU",
                entity_id=product.sku_id,
            ).first()
            if existing:
                processed += 1
                continue

            sku_sales = [
                {
                    "date": s.date,
                    "units_sold": s.units_sold,
                    "revenue": float(s.revenue or 0),
                    "margin": float(s.margin or 0),
                }
                for s in sales_rows
                if s.sku_id == product.sku_id
            ]

            pcis = pcis_map.get(product.sku_id)
            cis_list = cis_map.get(product.sku_id, [])
            elast = elast_map.get(product.sku_id)
            isv = isv_map.get(product.sku_id)

            # Gemiddeld CIS/CSRS/CSS
            avg_cis = sum(float(r.cis_score or 0) for r in cis_list) / len(cis_list) if cis_list else 0.5
            avg_csrs = sum(float(r.csrs_score or 0) for r in cis_list) / len(cis_list) if cis_list else 0.5
            avg_css = sum(float(r.css_score or 0) for r in cis_list) / len(cis_list) if cis_list else 0.5

            # Omzet/marge afgelopen 30d
            cutoff_30 = today - timedelta(days=30)
            rev_30d = sum(float(s["revenue"]) for s in sku_sales if s["date"] >= cutoff_30)
            margin_30d = sum(float(s["margin"]) for s in sku_sales if s["date"] >= cutoff_30)
            cost = float(product.cost_price or 1)
            price = float(product.current_price or cost * 1.3)
            margin_pct = metrics.margin_ratio(price, cost)

            sku_context = {
                "revenue_30d": rev_30d,
                "margin_30d": margin_30d,
                "margin_pct": margin_pct,
                "is_private_label": product.is_private_label,
                "is_a_brand": product.is_a_brand,
                "basket_affinity_score": basket_map.get(product.sku_id, 0.2),
                "strategy_weight": _strategy_weight(product.strategy_type),
                "stock_quantity": product.stock_quantity or 0,
                "price_index": float(pcis.price_index) if pcis and pcis.price_index else 1.0,
                "pcis_score": float(pcis.pcis_score) if pcis else 0.5,
                "cis_score": avg_cis,
                "csrs_score": avg_csrs,
                "css_score": avg_css,
                "substitution_score": float(pcis.substitution_score) if pcis else 0.3,
                "competitors_used": int(pcis.competitors_used) if pcis else 2,
                "own_price_elasticity": float(elast.own_price_elasticity) if elast and elast.own_price_elasticity else -1.5,
                "current_price": price,
                "cost_price": cost,
                "repeat_rate": 0.5 if product.strategy_type in ("REPEAT_PURCHASE", "BASKET_BUILDER") else 0.3,
            }

            # ── 1. GPS ─────────────────────────────────────────────────────
            gps = calculate_growth_potential(sku_sales, today)
            sku_context["gps_score"] = gps

            # ── 2. IBSS ────────────────────────────────────────────────────
            ibss = calculate_internal_business_strength(sku_context, total_revenue, total_margin)

            # ── 3. CSS_EXTERNAL & MOS ──────────────────────────────────────
            css_ext = calculate_competitive_strength(sku_context)
            mos = calculate_market_opportunity(sku_context, category_growth=0.05)

            # ── 4. Pricing Power ───────────────────────────────────────────
            pps = calculate_pricing_power_score(sku_context)

            # ── 5. PLSV ────────────────────────────────────────────────────
            plsv = 0.0
            if product.is_private_label:
                a_sku_id = pl_to_abrand.get(product.sku_id)
                a_brand = product_map.get(a_sku_id) if a_sku_id else None
                a_data = None
                if a_brand:
                    a_price = float(a_brand.current_price or price * 2)
                    a_cost = float(a_brand.cost_price or a_price * 0.5)
                    a_data = {
                        "margin_pct": metrics.margin_ratio(a_price, a_cost, default=0.2),
                        "current_price": a_price,
                    }
                _, _, _, plsv = calculate_private_label_value(sku_context, a_data)

            # ── 6. Classificaties ──────────────────────────────────────────
            confidence = float(product.data_quality_score or 0.8)
            internal_class = classify_internal_bcg(ibss, gps)
            external_class = classify_external_bcg(css_ext, mos)
            hybrid_class, strategy, priority = classify_hybrid_bcg(
                ibss, gps, css_ext, mos, pps, plsv, confidence,
                bool(product.is_private_label)
            )

            # ── 7. Opslaan ─────────────────────────────────────────────────
            record = models.FactBcgClassificationDaily(
                date=today,
                entity_type="SKU",
                entity_id=product.sku_id,
                entity_name=product.product_name,
                internal_bcg_class=internal_class,
                external_bcg_class=external_class,
                hybrid_bcg_class=hybrid_class,
                ibss_score=ibss,
                gps_score=gps,
                css_external_score=css_ext,
                mos_score=mos,
                pricing_power_score=pps,
                plsv_score=plsv,
                confidence_score=confidence,
                pricing_strategy=strategy,
                strategic_priority=priority,
            )
            db.add(record)

            # ── 8. Huismerk intelligence ───────────────────────────────────
            if product.is_private_label:
                existing_pl = db.query(models.FactPrivateLabelIntelligence).filter_by(
                    sku_id=product.sku_id, run_date=today
                ).first()
                if not existing_pl:
                    a_sku_id = pl_to_abrand.get(product.sku_id)
                    a_brand = product_map.get(a_sku_id) if a_sku_id else None
                    a_data_pl = None
                    if a_brand:
                        a_p = float(a_brand.current_price or price * 2)
                        a_c = float(a_brand.cost_price or a_p * 0.5)
                        a_data_pl = {"margin_pct": metrics.margin_ratio(a_p, a_c, default=0.2), "current_price": a_p}
                    sw_prob, mg, isv_val, plsv_val = calculate_private_label_value(sku_context, a_data_pl)
                    pl_class, pl_prio = classify_private_label(plsv_val)
                    db.add(models.FactPrivateLabelIntelligence(
                        sku_id=product.sku_id,
                        run_date=today,
                        internal_substitution_score=isv_val,
                        internal_switch_probability=sw_prob,
                        internal_margin_gap=mg,
                        private_label_value_score=plsv_val,
                        private_label_class=pl_class,
                        strategic_priority=pl_prio,
                        a_brand_sku=a_sku_id,
                        paired_sku_name=a_brand.product_name if a_brand else None,
                    ))

            processed += 1

        except Exception:
            skipped += 1
            continue

    # ── Categorie-level BCG ─────────────────────────────────────────────────
    _run_category_bcg(db, today)

    db.commit()

    # Publiceer gestandaardiseerde IntelligenceSignals (§7-§8)
    from engine.signal_emitters import emit_for_engine
    emit_for_engine(db, "bcg")

    return processed, skipped


def _run_category_bcg(db: Session, today: date) -> None:
    """Berekent BCG-classificatie op categorieniveau als aggregatie van SKU's."""
    sku_records = db.query(models.FactBcgClassificationDaily).filter_by(
        date=today, entity_type="SKU"
    ).all()

    products = db.query(models.DimProduct).all()
    cat_map: dict[str, str] = {p.sku_id: p.category for p in products}

    # Groepeer per categorie
    cat_scores: dict[str, list] = {}
    for r in sku_records:
        cat = cat_map.get(r.entity_id, "Onbekend")
        cat_scores.setdefault(cat, []).append(r)

    for cat, records in cat_scores.items():
        existing = db.query(models.FactBcgClassificationDaily).filter_by(
            date=today, entity_type="CATEGORY", entity_id=cat
        ).first()
        if existing:
            continue

        n = len(records)
        avg_ibss = sum(r.ibss_score or 0 for r in records) / n
        avg_gps = sum(r.gps_score or 0 for r in records) / n
        avg_css = sum(r.css_external_score or 0 for r in records) / n
        avg_mos = sum(r.mos_score or 0 for r in records) / n
        avg_pps = sum(r.pricing_power_score or 0 for r in records) / n
        avg_plsv = sum(r.plsv_score or 0 for r in records) / n

        internal_class = classify_internal_bcg(avg_ibss, avg_gps)
        external_class = classify_external_bcg(avg_css, avg_mos)
        hybrid_class, strategy, priority = classify_hybrid_bcg(
            avg_ibss, avg_gps, avg_css, avg_mos, avg_pps, avg_plsv,
            confidence=0.80,
            is_private_label=False,
        )

        db.add(models.FactBcgClassificationDaily(
            date=today,
            entity_type="CATEGORY",
            entity_id=cat,
            entity_name=cat,
            internal_bcg_class=internal_class,
            external_bcg_class=external_class,
            hybrid_bcg_class=hybrid_class,
            ibss_score=round(avg_ibss, 4),
            gps_score=round(avg_gps, 4),
            css_external_score=round(avg_css, 4),
            mos_score=round(avg_mos, 4),
            pricing_power_score=round(avg_pps, 4),
            plsv_score=round(avg_plsv, 4),
            confidence_score=0.80,
            pricing_strategy=strategy,
            strategic_priority=priority,
        ))


def _strategy_weight(strategy_type: str | None) -> float:
    """Vertaalt pricingstrategie naar een strategisch gewicht."""
    weights = {
        "SUBSTITUTION_PORTFOLIO": 0.85,
        "COMPETITOR_INDEX":       0.75,
        "MARGIN_OPTIMIZATION":    0.80,
        "REPEAT_PURCHASE":        0.70,
        "BASKET_BUILDER":         0.65,
        "VOLUME_DISCOUNT":        0.60,
        "STOCK_CLEARANCE":        0.30,
        "LOW_VELOCITY":           0.20,
    }
    return weights.get(strategy_type or "", 0.50)
