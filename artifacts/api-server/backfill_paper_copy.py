"""
Backfill: Paper_Copy pilot SKU dataset.

Inserts ~15 Paper_Copy SKUs (A4/A3, 70-90 gsm, OEM + private label),
competitor price history for 5 competitors over 30 days,
SKU competition scores, sales/margin history, and substitution pairs.

Result: Pilot Dashboard (/pilot-paper-copy) shows meaningful KPIs including
2-3 price-risk SKUs and 1-2 private-label opportunity SKUs.

Idempotent — skips all inserts if PCP001 already exists in dim_product.

Run:
    python artifacts/api-server/backfill_paper_copy.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import random
from datetime import date, timedelta, datetime
from database import SessionLocal
import models

random.seed(99)

TODAY = date.today()
COMPETITORS = ["Staples", "Office Depot", "Amazon NL", "Coolblue", "Bol.com"]

# ---------------------------------------------------------------------------
# Products  (sku_id, name, brand, is_private_label, is_a_brand,
#            strategy, cost, min_price, max_price, current_price, stock,
#            paper_size, paper_weight_gsm, sheets_per_pack)
# ---------------------------------------------------------------------------
PAPER_SKUS = [
    # ── OEM A-brands ──────────────────────────────────────────────────────
    ("PCP001", "Navigator Universal A4 80g/m² 500 vel",
     "Navigator", False, True,
     "VOLUME_DISCOUNT", 1.75, 1.50,  7.50,  4.89, 3200,
     "A4", 80, 500),
    ("PCP002", "Navigator Universal A4 80g/m² Doos 5x500 vel",
     "Navigator", False, True,
     "VOLUME_DISCOUNT", 8.20, 7.00, 32.00, 21.99,  820,
     "A4", 80, 2500),
    ("PCP003", "Double A Copy Paper A4 80g/m² 500 vel",
     "Double A", False, True,
     "VOLUME_DISCOUNT", 1.70, 1.45,  7.00,  4.49, 2800,
     "A4", 80, 500),
    ("PCP004", "Double A Copy Paper A4 80g/m² Doos 5x500 vel",
     "Double A", False, True,
     "VOLUME_DISCOUNT", 8.00, 6.80, 30.00, 21.49,  680,
     "A4", 80, 2500),
    ("PCP005", "HP Office A4 80g/m² 500 vel",
     "HP", False, True,
     "COMPETITOR_INDEX", 2.10, 1.80,  9.00,  5.29, 1900,
     "A4", 80, 500),
    ("PCP006", "HP Office A4 80g/m² Doos 5x500 vel",
     "HP", False, True,
     "COMPETITOR_INDEX", 9.80, 8.50, 38.00, 23.49,  420,
     "A4", 80, 2500),
    ("PCP007", "Xerox Performer A4 80g/m² 500 vel",
     "Xerox", False, True,
     "VOLUME_DISCOUNT", 1.60, 1.35,  6.50,  4.19, 2600,
     "A4", 80, 500),
    ("PCP008", "Xerox Performer A4 80g/m² Doos 5x500 vel",
     "Xerox", False, True,
     "VOLUME_DISCOUNT", 7.50, 6.50, 28.00, 19.49,  560,
     "A4", 80, 2500),
    ("PCP009", "Steinbeis No.1 Recycled A4 80g/m² 500 vel",
     "Steinbeis", False, True,
     "VOLUME_DISCOUNT", 1.40, 1.20,  6.00,  3.69, 1400,
     "A4", 80, 500),
    ("PCP010", "Navigator Universal A3 80g/m² 500 vel",
     "Navigator", False, True,
     "MARGIN_OPTIMIZATION", 3.80, 3.20, 18.00, 9.99, 780,
     "A3", 80, 500),
    # ── Private-label (123inkt) ────────────────────────────────────────────
    ("PCP011", "123inkt Kopieerpapier A4 80g/m² 500 vel",
     "123inkt", True, False,
     "VOLUME_DISCOUNT", 1.20, 1.00,  6.00,  3.49, 4800,
     "A4", 80, 500),
    ("PCP012", "123inkt Kopieerpapier A4 80g/m² Doos 5x500 vel",
     "123inkt", True, False,
     "VOLUME_DISCOUNT", 5.60, 4.80, 24.00, 14.99, 1200,
     "A4", 80, 2500),
    ("PCP013", "123inkt Premium Kopieerpapier A4 90g/m² 500 vel",
     "123inkt", True, False,
     "MARGIN_OPTIMIZATION", 1.65, 1.40,  8.00,  4.29, 1600,
     "A4", 90, 500),
    ("PCP014", "123inkt Kopieerpapier A3 80g/m² 500 vel",
     "123inkt", True, False,
     "MARGIN_OPTIMIZATION", 3.40, 2.90, 16.00, 8.29, 520,
     "A3", 80, 500),
    ("PCP015", "123inkt Recycled Kopieerpapier A4 75g/m² 500 vel",
     "123inkt", True, False,
     "VOLUME_DISCOUNT", 1.10, 0.95,  5.50,  2.99, 2200,
     "A4", 75, 500),
]

# ---------------------------------------------------------------------------
# Substitution pairs  (a_brand_sku, private_label_sku, strength)
# ---------------------------------------------------------------------------
SUBSTITUTIONS = [
    ("PCP001", "PCP011", 0.72),   # Navigator A4 500sh ↔ 123inkt A4 500sh
    ("PCP002", "PCP012", 0.68),   # Navigator A4 box   ↔ 123inkt A4 box
    ("PCP005", "PCP013", 0.55),   # HP Office A4 500sh ↔ 123inkt Premium 90g
    ("PCP010", "PCP014", 0.48),   # Navigator A3 500sh ↔ 123inkt A3 500sh
    ("PCP009", "PCP015", 0.62),   # Steinbeis Recycled ↔ 123inkt Recycled
]

# ---------------------------------------------------------------------------
# Competition scores  (sku_id, price_index, pcis_score, competition_class)
# price_index = own_price / avg_competitor_price
# <1.0 = we are cheaper; >1.0 = we are more expensive
# ---------------------------------------------------------------------------
# Target: PCP005 and PCP006 are price-risk (price_index > 1.0 AND own > max_comp)
# Most others slightly below or at parity
COMPETITION_SCORES = [
    # sku_id,  pi,    pcis,  class
    ("PCP001", 0.982, 0.81,  "Strong"),
    ("PCP002", 0.975, 0.78,  "Strong"),
    ("PCP003", 0.968, 0.80,  "Strong"),
    ("PCP004", 0.971, 0.77,  "Strong"),
    ("PCP005", 1.043, 0.75,  "Strong"),   # price-risk SKU
    ("PCP006", 1.038, 0.72,  "Strong"),   # price-risk SKU
    ("PCP007", 0.994, 0.76,  "Influence"),
    ("PCP008", 0.988, 0.73,  "Influence"),
    ("PCP009", 0.976, 0.68,  "Influence"),
    ("PCP010", 1.018, 0.64,  "Influence"),
    ("PCP011", 0.970, 0.79,  "Strong"),
    ("PCP012", 0.965, 0.76,  "Strong"),
    ("PCP013", 0.982, 0.70,  "Influence"),
    ("PCP014", 0.974, 0.62,  "Influence"),
    ("PCP015", 0.961, 0.68,  "Influence"),
]

# ---------------------------------------------------------------------------
# Competitor base prices per SKU (day-0 reference)
# These are chosen so that:
#   PCP005 own=5.29 > all 5 competitor prices (max ≈ 5.09)  → price-risk
#   PCP006 own=23.49 > all 5 competitor prices (max ≈ 22.99) → price-risk
#   All others: own_price ≤ some competitor price
# ---------------------------------------------------------------------------
COMPETITOR_BASE: dict[str, dict[str, float]] = {
    "PCP001": {"Staples": 4.99, "Office Depot": 4.89, "Amazon NL": 4.79, "Coolblue": 5.09, "Bol.com": 4.99},
    "PCP002": {"Staples":22.49, "Office Depot":21.99, "Amazon NL":21.49, "Coolblue":22.99, "Bol.com":22.29},
    "PCP003": {"Staples": 4.59, "Office Depot": 4.39, "Amazon NL": 4.29, "Coolblue": 4.79, "Bol.com": 4.49},
    "PCP004": {"Staples":21.99, "Office Depot":21.49, "Amazon NL":20.99, "Coolblue":22.49, "Bol.com":21.79},
    # PCP005: all competitors cheaper than 5.29
    "PCP005": {"Staples": 5.09, "Office Depot": 4.99, "Amazon NL": 4.89, "Coolblue": 5.09, "Bol.com": 4.99},
    # PCP006: all competitors cheaper than 23.49
    "PCP006": {"Staples":22.99, "Office Depot":22.49, "Amazon NL":22.29, "Coolblue":22.99, "Bol.com":22.79},
    "PCP007": {"Staples": 4.29, "Office Depot": 4.19, "Amazon NL": 4.09, "Coolblue": 4.49, "Bol.com": 4.29},
    "PCP008": {"Staples":19.99, "Office Depot":19.49, "Amazon NL":18.99, "Coolblue":20.49, "Bol.com":19.79},
    "PCP009": {"Staples": 3.79, "Office Depot": 3.59, "Amazon NL": 3.49, "Coolblue": 3.89, "Bol.com": 3.69},
    "PCP010": {"Staples":10.29, "Office Depot": 9.79, "Amazon NL": 9.49, "Coolblue":10.49, "Bol.com": 9.99},
    # Private label — competitors don't carry identical sku; lower reference prices
    "PCP011": {"Staples": 3.59, "Office Depot": 3.49, "Amazon NL": 3.39, "Coolblue": 3.69, "Bol.com": 3.59},
    "PCP012": {"Staples":15.49, "Office Depot":14.99, "Amazon NL":14.49, "Coolblue":15.99, "Bol.com":15.29},
    "PCP013": {"Staples": 4.39, "Office Depot": 4.29, "Amazon NL": 4.19, "Coolblue": 4.49, "Bol.com": 4.39},
    "PCP014": {"Staples": 8.49, "Office Depot": 8.29, "Amazon NL": 8.09, "Coolblue": 8.79, "Bol.com": 8.49},
    "PCP015": {"Staples": 3.09, "Office Depot": 2.99, "Amazon NL": 2.89, "Coolblue": 3.19, "Bol.com": 3.09},
}

# ---------------------------------------------------------------------------
# Sales / margin reference per SKU  (units_sold/day, margin_pct)
# ---------------------------------------------------------------------------
SALES_REF: dict[str, tuple[int, float]] = {
    "PCP001": (95, 0.358),
    "PCP002": (28, 0.373),
    "PCP003": (88, 0.351),
    "PCP004": (22, 0.372),
    "PCP005": (41, 0.397),   # high margin but price-risk
    "PCP006": (12, 0.417),
    "PCP007": (72, 0.345),
    "PCP008": (19, 0.361),
    "PCP009": (55, 0.379),
    "PCP010": (18, 0.381),
    "PCP011": (138, 0.657),  # private label — high margin
    "PCP012": (42, 0.627),
    "PCP013": (51, 0.615),
    "PCP014": (16, 0.595),
    "PCP015": (67, 0.633),
}


def _price_jitter(base: float, max_pct: float = 0.02) -> float:
    """Return base price with small random noise (±max_pct%)."""
    return round(base * (1 + random.uniform(-max_pct, max_pct)), 4)


def run(db) -> None:
    # ── Idempotency guard ────────────────────────────────────────────────
    if db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == "PCP001"
    ).first():
        print("  ↳ Paper_Copy SKUs al aanwezig — overgeslagen.")
        return

    print("  Producten aanmaken …")
    for (sku_id, name, brand, is_pl, is_ab, strategy,
         cost, min_p, max_p, curr_p, stock,
         psize, pgsm, sheets) in PAPER_SKUS:
        db.add(models.DimProduct(
            sku_id=sku_id,
            product_name=name,
            brand=brand,
            category="Paper",
            subcategory="Copy Paper",
            product_group="Paper_Copy",
            is_private_label=is_pl,
            is_a_brand=is_ab,
            lifecycle_status="active",
            strategy_type=strategy,
            cost_price=cost,
            min_price=min_p,
            max_price=max_p,
            current_price=curr_p,
            stock_quantity=stock,
            data_quality_score=0.95,
            paper_size=psize,
            paper_weight_gsm=pgsm,
            sheets_per_pack=sheets,
        ))
    db.flush()
    print(f"  ✓ {len(PAPER_SKUS)} Paper_Copy-producten aangemaakt.")

    # ── Category strategy mapping ────────────────────────────────────────
    existing_cat = db.query(models.CategoryStrategyMapping).filter(
        models.CategoryStrategyMapping.category == "Paper",
        models.CategoryStrategyMapping.subcategory == "Copy Paper",
    ).first()
    if not existing_cat:
        db.add(models.CategoryStrategyMapping(
            category="Paper",
            subcategory="Copy Paper",
            strategy_type="VOLUME_DISCOUNT",
            notes="Paper_Copy pilot — volume- en concurrentiestrategie",
            updated_by="system",
        ))

    # ── Substitution pairs ───────────────────────────────────────────────
    print("  Substitutiekoppelingen aanmaken …")
    for (a_sku, pl_sku, strength) in SUBSTITUTIONS:
        exists = db.query(models.MapSubstitution).filter(
            models.MapSubstitution.a_brand_sku == a_sku,
            models.MapSubstitution.private_label_sku == pl_sku,
        ).first()
        if not exists:
            db.add(models.MapSubstitution(
                a_brand_sku=a_sku,
                private_label_sku=pl_sku,
                substitution_strength=strength,
            ))
    print(f"  ✓ {len(SUBSTITUTIONS)} substitutiekoppelingen aangemaakt.")

    # ── Competitor price history (30 days) ──────────────────────────────
    print("  Concurrentieprijzen aanmaken (30 dagen × 15 SKU's × 5 concurrenten) …")
    comp_rows = 0
    for day_offset in range(30, 0, -1):
        d = TODAY - timedelta(days=day_offset)
        for sku_id, bases in COMPETITOR_BASE.items():
            for comp, base_price in bases.items():
                # Small daily drift so price-change detection fires
                price = _price_jitter(base_price, 0.018)
                db.add(models.FactCompetitorPriceDaily(
                    date=d,
                    sku_id=sku_id,
                    competitor_name=comp,
                    price=price,
                    url=f"https://{comp.lower().replace(' ', '')}.nl/{sku_id}",
                ))
                comp_rows += 1
    db.flush()
    print(f"  ✓ {comp_rows} concurrentieprijzen aangemaakt.")

    # ── Own price history (30 days) ──────────────────────────────────────
    print("  Eigen prijsgeschiedenis aanmaken …")
    price_rows = 0
    for (sku_id, _name, _brand, _is_pl, _is_ab, _strategy,
         cost, _min_p, _max_p, curr_p, _stock,
         _psize, _pgsm, _sheets) in PAPER_SKUS:
        for day_offset in range(30, 0, -1):
            d = TODAY - timedelta(days=day_offset)
            db.add(models.FactPriceDaily(
                date=d,
                sku_id=sku_id,
                price=round(curr_p * (1 + random.uniform(-0.005, 0.005)), 4),
                cost_price=cost,
            ))
            price_rows += 1
    print(f"  ✓ {price_rows} eigen prijsrecords aangemaakt.")

    # ── Sales + margin history (30 days) ────────────────────────────────
    print("  Verkoop- & margegeschiedenis aanmaken …")
    sales_rows = 0
    for (sku_id, _name, _brand, _is_pl, _is_ab, _strategy,
         cost, _min_p, _max_p, curr_p, _stock,
         _psize, _pgsm, _sheets) in PAPER_SKUS:
        base_units, base_marge_pct = SALES_REF[sku_id]
        for day_offset in range(30, 0, -1):
            d = TODAY - timedelta(days=day_offset)
            units = max(0, int(base_units * random.uniform(0.75, 1.25)))
            price = curr_p * (1 + random.uniform(-0.003, 0.003))
            revenue = round(units * price, 4)
            total_cost = round(units * cost, 4)
            margin = round(revenue - total_cost, 4)
            margin_pct = round(base_marge_pct * random.uniform(0.92, 1.08), 6)
            db.add(models.FactSalesDaily(
                date=d,
                sku_id=sku_id,
                units_sold=units,
                revenue=revenue,
                cost=total_cost,
                margin=margin,
                margin_pct=margin_pct,
            ))
            sales_rows += 1
    print(f"  ✓ {sales_rows} verkooprecords aangemaakt.")

    # ── SKU competition scores ───────────────────────────────────────────
    print("  SKU competition scores aanmaken …")
    run_date = TODAY - timedelta(days=1)
    for (sku_id, price_index, pcis_score, comp_class) in COMPETITION_SCORES:
        existing_score = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.sku_id == sku_id,
            models.SkuCompetitionScore.run_date == run_date,
        ).first()
        if existing_score:
            continue
        sku_tuple = next(s for s in PAPER_SKUS if s[0] == sku_id)
        curr_p = sku_tuple[9]   # index 9 = current_price (not 10 = stock)
        ref_price = round(curr_p / price_index, 4)
        db.add(models.SkuCompetitionScore(
            sku_id=sku_id,
            run_date=run_date,
            product_comparability_score=0.82,
            price_sensitivity_score=0.78,
            substitution_score=0.10,
            competitor_relevance_score=0.70,
            competitor_price_reliability_score=0.80,
            basket_dependency_score=0.08,
            strategic_importance_score=0.40,
            pcis_score=pcis_score,
            competition_class=comp_class,
            reference_price=ref_price,
            price_index=price_index,
            competitors_used=5,
            competitors_excluded=0,
            excluded_reasons={},
        ))
    print(f"  ✓ {len(COMPETITION_SCORES)} competition scores aangemaakt.")

    db.commit()
    print("\n✅ Paper_Copy backfill voltooid.")


def main() -> int:
    print("Paper_Copy Pilot — backfill dataset")
    print("=" * 50)
    db = SessionLocal()
    try:
        run(db)
        return 0
    except Exception as exc:
        db.rollback()
        print(f"❌ Fout: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
