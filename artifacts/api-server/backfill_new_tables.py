"""
One-time backfill: inserts competition scores and A/B test data
into the new tables for existing seeded databases.
Run: python backfill_new_tables.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta, datetime
from database import SessionLocal
import models

PRODUCTS = [
    ("INK001", 18.99, 8.50),
    ("INK002",  7.49, 2.50),
    ("INK003", 16.99, 7.20),
    ("INK004",  5.99, 1.80),
    ("INK005", 21.99, 9.00),
    ("INK006", 49.99,22.00),
    ("OFF001",  4.99, 1.20),
    ("OFF002",  6.49, 2.50),
    ("OFF003",  2.99, 0.80),
    ("OFF004",  5.49, 2.00),
    ("PAP001",  4.49, 1.80),
    ("PAP002", 19.99, 8.00),
    ("PAP003",  6.99, 2.20),
    ("PKG001", 14.99, 6.00),
    ("PKG002", 18.99, 8.00),
    ("CLN001",  3.99, 1.50),
    ("CLN002",  3.49, 1.20),
    ("CAN001", 12.99, 6.00),
    ("CAN002",  4.99, 2.00),
    ("ELC001",  8.99, 3.00),
    ("ELC002",  9.99, 4.00),
    ("FRN001",189.00,80.00),
    ("FRN002",299.00,150.00),
    ("PRT001",129.00,55.00),
    ("PRT002", 59.00,28.00),
    ("CLR001", 19.99,12.00),
]

COMPETITION_SCORES = [
    ("INK001",0.85,0.62,0.70,0.75,0.78,0.05,0.38,0.72,"Strong",  0.97,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("INK002",0.80,0.72,0.90,0.75,0.80,0.05,0.15,0.76,"Strong",  0.99,3,0,{}),
    ("INK003",0.83,0.58,0.70,0.75,0.76,0.05,0.32,0.70,"Strong",  0.97,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("INK004",0.78,0.68,0.90,0.75,0.79,0.05,0.12,0.74,"Strong",  0.98,2,0,{}),
    ("INK005",0.72,0.55,0.68,0.50,0.72,0.05,0.35,0.62,"Influence",1.02,2,1,{"COMPETITOR_IGNORED_OUT_OF_STOCK":1}),
    ("INK006",0.80,0.75,0.10,0.75,0.82,0.05,0.52,0.65,"Influence",0.96,3,0,{}),
    ("OFF001",0.65,0.55,0.05,0.50,0.68,0.10,0.22,0.48,"Influence",1.01,2,0,{}),
    ("OFF002",0.45,0.38,0.05,0.25,0.55,0.10,0.28,0.35,"Monitor", 1.03,1,0,{}),
    ("OFF003",0.55,0.52,0.05,0.50,0.65,0.10,0.18,0.44,"Monitor", 0.99,2,0,{}),
    ("OFF004",0.58,0.50,0.05,0.50,0.62,0.10,0.25,0.47,"Influence",1.00,2,1,{"COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE":1}),
    ("PAP001",0.88,0.90,0.05,0.75,0.85,0.05,0.42,0.82,"Strong",  0.96,3,0,{}),
    ("PAP002",0.85,0.88,0.05,0.75,0.82,0.05,0.45,0.81,"Strong",  0.95,3,1,{"COMPETITOR_IGNORED_BAD_MATCH":1}),
    ("PAP003",0.60,0.55,0.05,0.50,0.65,0.05,0.32,0.54,"Influence",1.04,2,0,{}),
    ("PKG001",0.65,0.62,0.05,0.50,0.70,0.05,0.28,0.57,"Influence",0.97,2,0,{}),
    ("PKG002",0.68,0.65,0.05,0.50,0.68,0.05,0.35,0.58,"Influence",0.98,2,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("CLN001",0.48,0.45,0.05,0.50,0.60,0.82,0.22,0.44,"Monitor", 1.00,2,0,{}),
    ("CLN002",0.45,0.42,0.05,0.50,0.58,0.78,0.20,0.43,"Monitor", 1.01,2,0,{}),
    ("CAN001",0.55,0.50,0.05,0.25,0.62,0.88,0.28,0.52,"Influence",0.96,1,0,{}),
    ("CAN002",0.50,0.45,0.05,0.25,0.58,0.82,0.18,0.48,"Influence",0.97,1,0,{}),
    ("ELC001",0.92,0.85,0.05,0.75,0.88,0.05,0.38,0.78,"Strong",  0.94,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("ELC002",0.90,0.82,0.05,0.75,0.85,0.05,0.42,0.76,"Strong",  0.95,3,0,{}),
    ("FRN001",0.35,0.15,0.05,0.25,0.52,0.05,0.58,0.32,"Monitor", 0.98,1,0,{}),
    ("FRN002",0.32,0.12,0.05,0.25,0.48,0.05,0.62,0.30,"Monitor", 0.99,1,0,{}),
    ("PRT001",0.88,0.85,0.05,0.75,0.85,0.05,0.55,0.74,"Strong",  0.96,3,1,{"COMPETITOR_IGNORED_BAD_DELIVERY":1}),
    ("PRT002",0.85,0.82,0.05,0.75,0.82,0.05,0.48,0.71,"Strong",  0.95,3,0,{}),
    ("CLR001",0.15,0.12,0.05,0.25,0.35,0.02,0.08,0.14,"Ignore",  1.25,0,2,{"COMPETITOR_IGNORED_LOW_RELEVANCE":2}),
]

# sku_id, group, bl_price, curr_price, bl_units, curr_units, bl_conv, curr_conv
AB_SKUS = [
    ("INK001","AI",   18.99,18.49, 14,15,0.0480,0.0510),
    ("INK003","AI",   16.99,16.49, 10,11,0.0420,0.0455),
    ("INK005","AI",   21.99,22.49,  8, 8,0.0350,0.0348),
    ("OFF001","AI",    4.99, 5.29, 24,23,0.0620,0.0610),
    ("PAP001","AI",    4.49, 4.29, 75,82,0.0820,0.0870),
    ("PKG001","AI",   14.99,14.49, 12,13,0.0390,0.0415),
    ("CLN001","AI",    3.99, 3.99, 21,21,0.0680,0.0682),
    ("CAN001","AI",   12.99,12.49, 14,15,0.0510,0.0540),
    ("ELC001","AI",    8.99, 8.49, 20,22,0.0720,0.0785),
    ("FRN001","AI",  189.00,185.00, 1, 1,0.0085,0.0088),
    ("PRT001","AI",  129.00,124.00, 2, 3,0.0120,0.0145),
    ("PAP003","AI",    6.99, 6.99,  9, 9,0.0340,0.0342),
    ("PKG002","AI",   18.99,17.99, 17,19,0.0480,0.0520),
    ("INK002","CONTROL", 7.49, 7.49, 11,11,0.0520,0.0519),
    ("INK004","CONTROL", 5.99, 5.99,  9, 9,0.0490,0.0491),
    ("INK006","CONTROL",49.99,49.99,  6, 6,0.0310,0.0309),
    ("OFF002","CONTROL", 6.49, 6.49, 11,11,0.0430,0.0430),
    ("PAP002","CONTROL",19.99,19.99, 54,54,0.0780,0.0779),
    ("CLN002","CONTROL", 3.49, 3.49, 18,18,0.0650,0.0650),
    ("CAN002","CONTROL", 4.99, 4.99, 11,11,0.0470,0.0470),
    ("ELC002","CONTROL", 9.99, 9.99, 14,14,0.0690,0.0688),
    ("FRN002","CONTROL",299.00,299.00, 0, 0,0.0075,0.0074),
    ("PRT002","CONTROL", 59.00,59.00,  3, 3,0.0130,0.0130),
    ("OFF003","CONTROL", 2.99, 2.99, 29,29,0.0750,0.0749),
    ("OFF004","CONTROL", 5.49, 5.49, 18,18,0.0570,0.0570),
    ("CLR001","CONTROL",19.99,19.99,  0, 0,0.0045,0.0045),
]

def run():
    db = SessionLocal()
    today = date.today()
    try:
        # Skip if already backfilled
        if db.query(models.SkuCompetitionScore).count() > 0:
            print("Competition scores already exist — skipping.")
        else:
            prod_map = {p[0]: p for p in PRODUCTS}
            for row in COMPETITION_SCORES:
                sku_id, comp, ps, sub, cr, pr, bd, si, pcis, cls, pi, cu, ce, er = row
                p = prod_map.get(sku_id)
                ref_price = round(float(p[1]) / pi, 4) if p and pi else None
                db.add(models.SkuCompetitionScore(
                    sku_id=sku_id, run_date=today,
                    product_comparability_score=comp,
                    price_sensitivity_score=ps,
                    substitution_score=sub,
                    competitor_relevance_score=cr,
                    competitor_price_reliability_score=pr,
                    basket_dependency_score=bd,
                    strategic_importance_score=si,
                    pcis_score=pcis,
                    competition_class=cls,
                    reference_price=ref_price,
                    price_index=pi,
                    competitors_used=cu,
                    competitors_excluded=ce,
                    excluded_reasons=er,
                ))
            db.commit()
            print(f"Inserted {len(COMPETITION_SCORES)} competition scores.")

        if db.query(models.AbTest).count() > 0:
            print("A/B tests already exist — skipping.")
        else:
            ab_test = models.AbTest(
                name="AI Pricing Engine vs. Static Pricing — Q1 2026",
                description=(
                    "Evaluates margin uplift, revenue impact, and conversion lift "
                    "when applying AI-recommended prices vs. keeping prices unchanged. "
                    "Split: 50/50 by SKU across all categories."
                ),
                start_date=today - timedelta(days=30),
                end_date=today,
                status="active",
                ai_group_sku_count=13,
                control_group_sku_count=13,
            )
            db.add(ab_test)
            db.commit()

            prod_map = {p[0]: p for p in PRODUCTS}
            for row in AB_SKUS:
                sku_id, grp, bl_p, curr_p, bl_u, curr_u, bl_conv, curr_conv = row
                p = prod_map.get(sku_id)
                cost = float(p[2]) if p else float(bl_p) * 0.5
                db.add(models.AbTestResult(
                    test_id=ab_test.id,
                    sku_id=sku_id,
                    group_type=grp,
                    baseline_price=bl_p,
                    current_price=curr_p,
                    baseline_units=float(bl_u),
                    current_units=float(curr_u),
                    baseline_revenue=round(bl_p * bl_u * 30, 2),
                    current_revenue=round(curr_p * curr_u * 30, 2),
                    baseline_margin=round((bl_p - cost) * bl_u * 30, 2),
                    current_margin=round((curr_p - cost) * curr_u * 30, 2),
                    baseline_conversion_rate=bl_conv,
                    current_conversion_rate=curr_conv,
                ))
            db.commit()
            print(f"Inserted A/B test with {len(AB_SKUS)} SKU results.")

    except Exception as e:
        db.rollback()
        print(f"Backfill failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
    print("Done.")
