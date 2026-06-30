"""
Backfill Competition Intelligence Engine 2.0.

Vult de volgende tabellen met demo-data:
- competitor_discovery_run          (2 runs)
- competitor_discovery_queue        (10 concurrenten PROPOSED/APPROVED/REJECTED)
- competitor_profile                (5 profielen)
- category_competitor_relevance     (5 concurrenten × 3 categorieën = 15 rijen)
- ai_match_result                   (20 matches, diverse typen)
- competitor_strategy_result        (5 concurrenten met strategie + 2 met gewijzigde strategie)
- assortment_gap                    (15 gaten in 3 categorieën)

Idempotent: reeds gevulde tabellen worden overgeslagen.
"""
import sys
import os
import uuid
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
import models

TODAY = date.today()


def _already_filled(db, model_class, threshold: int = 1) -> bool:
    return db.query(model_class).count() >= threshold


def backfill_discovery_runs(db) -> None:
    if _already_filled(db, models.CompetitorDiscoveryRun):
        print("  ⏭  competitor_discovery_run al gevuld — overgeslagen")
        return

    runs = [
        models.CompetitorDiscoveryRun(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            started_at=datetime.utcnow() - timedelta(days=7),
            completed_at=datetime.utcnow() - timedelta(days=7, seconds=45),
            status="completed",
            categories_searched=["Ink & Toner", "Paper", "Office Supplies"],
            candidates_found=8,
            candidates_new=8,
            candidates_approved=0,
            candidates_rejected=0,
            parameters={"min_confidence": 0.60},
        ),
        models.CompetitorDiscoveryRun(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            started_at=datetime.utcnow() - timedelta(days=1),
            completed_at=datetime.utcnow() - timedelta(days=1, seconds=38),
            status="completed",
            categories_searched=["Printers", "Electronics"],
            candidates_found=4,
            candidates_new=2,
            candidates_approved=0,
            candidates_rejected=0,
            parameters={"min_confidence": 0.70},
        ),
    ]
    db.add_all(runs)
    db.flush()
    print(f"  ✅ {len(runs)} discovery-runs aangemaakt")


def backfill_discovery_queue(db) -> None:
    if _already_filled(db, models.CompetitorDiscoveryQueue, 5):
        print("  ⏭  competitor_discovery_queue al gevuld — overgeslagen")
        return

    run_id = f"run-demo-{uuid.uuid4().hex[:8]}"
    queue_items = [
        # PROPOSED
        models.CompetitorDiscoveryQueue(
            domain="staples.nl", competitor_name="Staples",
            discovery_reason="Grote kantoorartikelen-retailer met brede SKU-overlap in inkt, papier en kantoorartikelen.",
            discovery_method="PATTERN",
            categories=["Ink & Toner", "Paper", "Office Supplies"],
            confidence=0.95, status="PROPOSED", run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="bol.com", competitor_name="Bol.com",
            discovery_reason="Grootste Nederlandse marketplace met uitgebreid kantoorartikelen-assortiment.",
            discovery_method="KEYWORD",
            categories=["Ink & Toner", "Paper", "Electronics"],
            confidence=0.90, status="PROPOSED", run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="papierlandschaft.de", competitor_name="Papierlandschaft",
            discovery_reason="Gespecialiseerde papier-retailer actief in Benelux-grensregio.",
            discovery_method="KEYWORD",
            categories=["Paper", "Office Supplies"],
            confidence=0.72, status="PROPOSED", run_id=run_id,
        ),
        # APPROVED
        models.CompetitorDiscoveryQueue(
            domain="viking.nl", competitor_name="Viking Direct",
            discovery_reason="B2B kantoorartikelen-specialist met directe overlap in ink/toner en kantoorbenodigdheden.",
            discovery_method="CATEGORY",
            categories=["Ink & Toner", "Paper", "Office Supplies", "Furniture"],
            confidence=0.92, status="APPROVED",
            approved_by="analyst", approved_at=datetime.utcnow() - timedelta(days=5),
            run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="tonerdump.nl", competitor_name="TonerDump",
            discovery_reason="Gespecialiseerde inkt/toner-retailer met compatible en OEM-assortiment.",
            discovery_method="OEM",
            categories=["Ink & Toner"],
            confidence=0.88, status="APPROVED",
            approved_by="pricing_manager", approved_at=datetime.utcnow() - timedelta(days=4),
            run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="quantore.nl", competitor_name="Quantore",
            discovery_reason="Groothandel kantoorartikelen — directe concurrent in papier en kantoorbenodigdheden.",
            discovery_method="PATTERN",
            categories=["Paper", "Office Supplies"],
            confidence=0.85, status="APPROVED",
            approved_by="analyst", approved_at=datetime.utcnow() - timedelta(days=3),
            run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="amazon.nl", competitor_name="Amazon NL",
            discovery_reason="Groeiende presence van Amazon in NL markt voor kantoorartikelen.",
            discovery_method="PATTERN",
            categories=["Ink & Toner", "Electronics"],
            confidence=0.87, status="APPROVED",
            approved_by="admin", approved_at=datetime.utcnow() - timedelta(days=2),
            run_id=run_id,
        ),
        # REJECTED
        models.CompetitorDiscoveryQueue(
            domain="inkjetwarehouse.co.uk", competitor_name="InkJet Warehouse UK",
            discovery_reason="UK-gebaseerde inkt-retailer — weinig aanwezigheid in NL markt.",
            discovery_method="OEM",
            categories=["Ink & Toner"],
            confidence=0.61, status="REJECTED",
            approved_by="analyst", approved_at=datetime.utcnow() - timedelta(days=6),
            run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="coolblue.nl", competitor_name="Coolblue",
            discovery_reason="Sterk in printers en randapparatuur.",
            discovery_method="KEYWORD",
            categories=["Printers", "Electronics"],
            confidence=0.82, status="PROPOSED", run_id=run_id,
        ),
        models.CompetitorDiscoveryQueue(
            domain="bechtle.com", competitor_name="Bechtle",
            discovery_reason="IT-retailer met sterk assortiment printers en OEM-cartridges.",
            discovery_method="OEM",
            categories=["Printers", "Ink & Toner"],
            confidence=0.78, status="PROPOSED", run_id=run_id,
        ),
    ]
    db.add_all(queue_items)
    db.flush()
    print(f"  ✅ {len(queue_items)} discovery-queue-items aangemaakt")


def backfill_profiles(db) -> None:
    if _already_filled(db, models.CompetitorProfile, 3):
        print("  ⏭  competitor_profile al gevuld — overgeslagen")
        return

    profiles = [
        models.CompetitorProfile(
            competitor_name="Viking Direct", domain="viking.nl",
            assortment_size=32, category_breadth=4,
            top_brands=["HP", "Canon", "Epson", "Brother", "Esselte"],
            top_categories=["Ink & Toner", "Paper", "Office Supplies", "Furniture"],
            price_segment="MIDDEN", premium_share_pct=0.20, budget_share_pct=0.35,
            avg_price_index=0.98, price_change_frequency=2.3,
            last_price_change_date=TODAY - timedelta(days=2),
            avg_delivery_days=2.0, in_stock_rate=0.94,
            functional_overlap_score=0.82, relevance_label="HIGH", traffic_light="green",
            run_date=TODAY,
        ),
        models.CompetitorProfile(
            competitor_name="TonerDump", domain="tonerdump.nl",
            assortment_size=18, category_breadth=1,
            top_brands=["HP", "Canon", "Compatible", "Xerox", "Lexmark"],
            top_categories=["Ink & Toner"],
            price_segment="BUDGET", premium_share_pct=0.05, budget_share_pct=0.65,
            avg_price_index=0.88, price_change_frequency=4.1,
            last_price_change_date=TODAY - timedelta(days=1),
            avg_delivery_days=3.5, in_stock_rate=0.87,
            functional_overlap_score=0.65, relevance_label="HIGH", traffic_light="green",
            run_date=TODAY,
        ),
        models.CompetitorProfile(
            competitor_name="Quantore", domain="quantore.nl",
            assortment_size=21, category_breadth=2,
            top_brands=["Hammermill", "Xerox", "Navigator", "IQ", "Excellent"],
            top_categories=["Paper", "Office Supplies"],
            price_segment="MIDDEN", premium_share_pct=0.15, budget_share_pct=0.40,
            avg_price_index=0.96, price_change_frequency=1.5,
            last_price_change_date=TODAY - timedelta(days=4),
            avg_delivery_days=2.5, in_stock_rate=0.92,
            functional_overlap_score=0.60, relevance_label="HIGH", traffic_light="green",
            run_date=TODAY,
        ),
        models.CompetitorProfile(
            competitor_name="Amazon NL", domain="amazon.nl",
            assortment_size=45, category_breadth=4,
            top_brands=["HP", "Epson", "Canon", "Samsung", "Generic"],
            top_categories=["Ink & Toner", "Electronics", "Paper", "Printers"],
            price_segment="MIDDEN", premium_share_pct=0.30, budget_share_pct=0.25,
            avg_price_index=0.95, price_change_frequency=5.8,
            last_price_change_date=TODAY - timedelta(days=1),
            avg_delivery_days=1.0, in_stock_rate=0.97,
            functional_overlap_score=0.75, relevance_label="HIGH", traffic_light="green",
            run_date=TODAY,
        ),
        models.CompetitorProfile(
            competitor_name="Papierlandschaft", domain="papierlandschaft.de",
            assortment_size=8, category_breadth=2,
            top_brands=["IQ", "Navigator", "Steinbeis"],
            top_categories=["Paper", "Office Supplies"],
            price_segment="BUDGET", premium_share_pct=0.05, budget_share_pct=0.55,
            avg_price_index=0.92, price_change_frequency=0.8,
            last_price_change_date=TODAY - timedelta(days=12),
            avg_delivery_days=5.0, in_stock_rate=0.75,
            functional_overlap_score=0.30, relevance_label="MONITOR", traffic_light="orange",
            run_date=TODAY,
        ),
    ]
    db.add_all(profiles)
    db.flush()
    print(f"  ✅ {len(profiles)} concurrenten-profielen aangemaakt")


def backfill_category_scores(db) -> None:
    if _already_filled(db, models.CategoryCompetitorRelevance, 5):
        print("  ⏭  category_competitor_relevance al gevuld — overgeslagen")
        return

    competitors = ["Viking Direct", "TonerDump", "Quantore", "Amazon NL", "Papierlandschaft"]
    categories = ["Ink & Toner", "Paper", "Office Supplies"]

    rows = []
    import random
    random.seed(42)

    for comp in competitors:
        for cat in categories:
            # Sla niet-relevante combinaties over
            if comp == "TonerDump" and cat != "Ink & Toner":
                continue
            if comp == "Papierlandschaft" and cat == "Ink & Toner":
                continue

            rl = round(random.uniform(40, 95), 1)
            ci = round(random.uniform(30, 90), 1)
            auth = round(random.uniform(35, 85), 1)
            ag = round(max(0, 100 - ci), 1)
            pr = round(random.uniform(30, 85), 1)
            tr = round(random.uniform(25, 80), 1)
            opp = round((ag * 0.4 + pr * 0.3 + tr * 0.3), 1)
            comb = round((rl * 0.2 + ci * 0.2 + auth * 0.15 + pr * 0.15 + tr * 0.15 + opp * 0.15), 1)

            if comb >= 65:
                label, tl = "HIGH", "green"
            elif comb >= 35:
                label, tl = "MONITOR", "orange"
            else:
                label, tl = "LOW", "red"

            rows.append(models.CategoryCompetitorRelevance(
                competitor_name=comp, category=cat,
                relevance_score=rl, coverage_index=ci,
                authority_score=auth, assortment_gap_score=ag,
                pricing_relevance_score=pr, traffic_relevance_score=tr,
                opportunity_score=opp, combined_score=comb,
                relevance_label=label, traffic_light=tl,
                relevance_explanation=f"{comp} heeft {ci:.0f}% SKU-coverage in '{cat}'.",
                opportunity_explanation=f"Opportunity score {opp:.0f} — {100-ci:.0f}% ontbreekt.",
                missing_brands=[], missing_product_types=[], missing_price_segments=[],
                run_date=TODAY,
            ))

    db.add_all(rows)
    db.flush()
    print(f"  ✅ {len(rows)} categorie-scorerijen aangemaakt")


def backfill_ai_matches(db) -> None:
    if _already_filled(db, models.AiMatchResult, 10):
        print("  ⏭  ai_match_result al gevuld — overgeslagen")
        return

    # Haal de eerste 20 producten op
    products = db.query(models.DimProduct).limit(20).all()
    competitors = ["Viking Direct", "TonerDump", "Quantore", "Amazon NL"]
    match_types = ["Exact", "Sterk", "Functioneel", "Categorie_Alternatief", "Geen_Match"]
    statuses = ["PENDING", "APPROVED", "APPROVED", "PENDING", "REJECTED"]

    import random, itertools
    random.seed(77)

    rows = []
    combos = list(itertools.product(products[:10], competitors))[:20]

    for product, comp in combos:
        mt = random.choice(match_types)
        conf = {
            "Exact": random.uniform(0.88, 0.98),
            "Sterk": random.uniform(0.70, 0.85),
            "Functioneel": random.uniform(0.50, 0.68),
            "Categorie_Alternatief": random.uniform(0.30, 0.48),
            "Geen_Match": random.uniform(0.05, 0.22),
        }[mt]
        st = random.choice(statuses)

        own_price = float(product.current_price) if product.current_price else 10.0
        comp_price = round(own_price * random.uniform(0.80, 1.25), 2)
        diff = round((comp_price / own_price - 1) * 100, 2)

        rows.append(models.AiMatchResult(
            own_sku_id=product.sku_id,
            competitor_name=comp,
            competitor_sku=f"{comp[:3].upper()}-{product.sku_id}",
            match_type=mt,
            confidence=round(conf, 3),
            explanation_nl=f"Match-type '{mt}' met {comp} voor {product.product_name}.",
            ean_match=(mt == "Exact"),
            brand_match=(mt in ("Exact", "Sterk")),
            product_type_match=(mt in ("Exact", "Sterk", "Functioneel")),
            price_segment_match=(mt != "Geen_Match"),
            competitor_price=comp_price,
            own_price=own_price,
            price_diff_pct=diff,
            status=st,
            approved_by="analyst" if st in ("APPROVED", "REJECTED") else None,
            approved_at=datetime.utcnow() - timedelta(days=random.randint(1, 5)) if st != "PENDING" else None,
            run_date=TODAY,
        ))

    db.add_all(rows)
    db.flush()
    print(f"  ✅ {len(rows)} AI-matchresultaten aangemaakt")


def backfill_strategy_results(db) -> None:
    if _already_filled(db, models.CompetitorStrategyResult, 3):
        print("  ⏭  competitor_strategy_result al gevuld — overgeslagen")
        return

    strategie_data = [
        ("Viking Direct", "EVERYDAY_LOW_PRICE", "Altijd-Laagste-Prijs", 0.78,
         "Structureel ≥80% van de tijd onder marktgemiddelde met lage prijsvolatiliteit.",
         "Handhaaf eigen PCIS-gewogen referentieprijs; volg niet blind.", None, False),
        ("TonerDump", "MARKET_SHARE_ATTACK", "Marktaandeeloffensief", 0.72,
         "Sterke neerwaartse trend in ink/toner categorie met hoge wijzigingsfrequentie (4.1×/week).",
         "Alert actief — overweeg tijdelijke match voor strategische SKU's.", "EVERYDAY_LOW_PRICE", True),
        ("Quantore", "MARGIN_PROTECTION", "Margebescherming", 0.65,
         "Zeer stabiele prijs in papier-categorie; nauwelijks reactie op marktbewegingen.",
         "Kans om margeruimte te benutten; verhoog prijs met index.", None, False),
        ("Amazon NL", "PROMOTION_DRIVEN", "Promotiegedreven", 0.80,
         "Frequente promotie-dips in ink & electronics gevolgd door prijsherstel.",
         "Monitor promotiecycli; vermijd structurele prijsverlaging.", "PRICE_FOLLOWER", True),
        ("Papierlandschaft", "PRICE_FOLLOWER", "Prijsvolger", 0.55,
         "Geen dominante strategie; volgt marktgemiddelde met lage aanpassingsfrequentie.",
         "Gebruik als referentiesignaal; concurrent volgt toch.", None, False),
    ]

    rows = []
    for comp, stype, slabel, conf, expl, aanbeveling, prev, changed in strategie_data:
        rows.append(models.CompetitorStrategyResult(
            competitor_name=comp,
            run_date=TODAY,
            strategy_type=stype,
            strategy_label_nl=slabel,
            confidence=conf,
            explanation_nl=expl,
            recommended_action_nl=aanbeveling,
            period_days=30,
            data_points=30,
            previous_strategy_type=prev,
            strategy_changed=changed,
        ))

    db.add_all(rows)
    db.flush()
    print(f"  ✅ {len(rows)} strategie-resultaten aangemaakt")


def backfill_assortment_gaps(db) -> None:
    if _already_filled(db, models.AssortmentGap, 5):
        print("  ⏭  assortment_gap al gevuld — overgeslagen")
        return

    gaps = [
        # Ink & Toner
        models.AssortmentGap(
            category="Ink & Toner", competitor_name="Viking Direct",
            gap_type="MERK", gap_value="Lexmark",
            opportunity_score=78.0,
            explanation_nl="Viking Direct heeft Lexmark inkt breed in het assortiment; wij niet.",
            competitor_has=True, potential_revenue_eur=12500.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Ink & Toner", competitor_name="TonerDump",
            gap_type="PRODUCTTYPE", gap_value="Compatible XXL Cartridges",
            opportunity_score=85.0,
            explanation_nl="TonerDump scoort sterk op compatible XXL-varianten die wij niet aanbieden.",
            competitor_has=True, potential_revenue_eur=18000.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Ink & Toner", competitor_name="Amazon NL",
            gap_type="PRIJSSEGMENT", gap_value="Premium OEM (> €35)",
            opportunity_score=62.0,
            explanation_nl="Amazon biedt premium OEM cartridges boven €35 die wij missen.",
            competitor_has=True, potential_revenue_eur=9200.0, run_date=TODAY,
        ),
        # Paper
        models.AssortmentGap(
            category="Paper", competitor_name="Quantore",
            gap_type="MERK", gap_value="Steinbeis Recycled",
            opportunity_score=71.0,
            explanation_nl="Quantore verkoopt Steinbeis recycled papier breed — groeiend segment.",
            competitor_has=True, potential_revenue_eur=14000.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Paper", competitor_name="Papierlandschaft",
            gap_type="OEM_KANS", gap_value="Huismerk A3 Papier",
            opportunity_score=58.0,
            explanation_nl="Papierlandschaft heeft huismerk A3 papier dat wij niet in eigen label aanbieden.",
            competitor_has=True, potential_revenue_eur=6800.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Paper", competitor_name="Viking Direct",
            gap_type="PRODUCTTYPE", gap_value="Milieucertificeerd Papier (FSC)",
            opportunity_score=74.0,
            explanation_nl="Viking Direct heeft breed FSC-gecertificeerd papierassortiment; kans voor ons.",
            competitor_has=True, potential_revenue_eur=11500.0, run_date=TODAY,
        ),
        # Office Supplies
        models.AssortmentGap(
            category="Office Supplies", competitor_name="Viking Direct",
            gap_type="MERK", gap_value="Leitz",
            opportunity_score=68.0,
            explanation_nl="Leitz ordners en opbergsystemen ontbreken grotendeels in ons assortiment.",
            competitor_has=True, potential_revenue_eur=8900.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Office Supplies", competitor_name="Amazon NL",
            gap_type="PRIJSSEGMENT", gap_value="Budget Kantoorartikelen (< €5)",
            opportunity_score=55.0,
            explanation_nl="Amazon heeft breed aanbod budget-kantoorartikelen onder €5 — volume-kans.",
            competitor_has=True, potential_revenue_eur=5500.0, run_date=TODAY,
        ),
        models.AssortmentGap(
            category="Office Supplies", competitor_name="Quantore",
            gap_type="PRODUCTTYPE", gap_value="Ergonomische Bureau-accessoires",
            opportunity_score=63.0,
            explanation_nl="Quantore verkoopt ergonomische bureau-accessoires — groeiend thuiswerk-segment.",
            competitor_has=True, potential_revenue_eur=7300.0, run_date=TODAY,
        ),
    ]

    db.add_all(gaps)
    db.flush()
    print(f"  ✅ {len(gaps)} assortimentsgaten aangemaakt")


def main() -> None:
    print("\n" + "=" * 60)
    print("  Backfill Competition Intelligence Engine 2.0")
    print("=" * 60)

    db = SessionLocal()
    try:
        backfill_discovery_runs(db)
        backfill_discovery_queue(db)
        backfill_profiles(db)
        backfill_category_scores(db)
        backfill_ai_matches(db)
        backfill_strategy_results(db)
        backfill_assortment_gaps(db)
        db.commit()
        print("\n✅ Backfill Competition Intelligence Engine 2.0 voltooid")
    except Exception as exc:
        db.rollback()
        print(f"\n❌ Fout tijdens backfill: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
