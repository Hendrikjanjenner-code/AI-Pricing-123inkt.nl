"""
Demo data seeder.
Creates a realistic dataset of products, categories, sales, prices,
competitor prices, inventory, substitutions, and pricing recommendations.
Only runs if the database is empty.
"""
import random
from datetime import date, timedelta, datetime
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import auth as auth_utils

random.seed(42)


CATEGORIES = [
    ("Ink & Toner", "Cartridges", "SUBSTITUTION_PORTFOLIO"),
    ("Ink & Toner", "Compatible Cartridges", "SUBSTITUTION_PORTFOLIO"),
    ("Office Supplies", "Pens & Pencils", "REPEAT_PURCHASE"),
    ("Office Supplies", "Filing & Binders", "MARGIN_OPTIMIZATION"),
    ("Paper", "Copy Paper", "VOLUME_DISCOUNT"),
    ("Paper", "Specialty Paper", "MARGIN_OPTIMIZATION"),
    ("Packaging", "Bubble Wrap", "VOLUME_DISCOUNT"),
    ("Packaging", "Cardboard Boxes", "VOLUME_DISCOUNT"),
    ("Cleaning", "Floor Cleaning", "REPEAT_PURCHASE"),
    ("Cleaning", "Surface Cleaners", "REPEAT_PURCHASE"),
    ("Canteen Supplies", "Coffee & Tea", "REPEAT_PURCHASE"),
    ("Canteen Supplies", "Cups & Disposables", "BASKET_BUILDER"),
    ("Electronics", "Cables & Adapters", "COMPETITOR_INDEX"),
    ("Electronics", "Storage & USB", "COMPETITOR_INDEX"),
    ("Furniture", "Office Chairs", "LOW_VELOCITY"),
    ("Furniture", "Desks", "LOW_VELOCITY"),
    ("Printers", "Laser Printers", "COMPETITOR_INDEX"),
    ("Printers", "Inkjet Printers", "COMPETITOR_INDEX"),
]

BRANDS = ["HP", "Canon", "Epson", "Brother", "123inkt", "Avery", "Staples", "3M", "Fellowes", "IKEA"]
COMPETITORS = ["Amazon", "Staples Online", "OfficeDepot", "Viking Direct"]

PRODUCTS = [
    # Ink & Toner SKUs with A-brand and private label pairs
    ("INK001", "HP 364 Black Ink Cartridge", "HP", "Ink & Toner", "Cartridges", True, False, "active", "SUBSTITUTION_PORTFOLIO", 8.50, 7.00, 25.00, 18.99, 450),
    ("INK002", "123inkt Black Ink Cartridge HP 364 Compatible", "123inkt", "Ink & Toner", "Compatible Cartridges", False, True, "active", "SUBSTITUTION_PORTFOLIO", 2.50, 2.00, 12.00, 7.49, 380),
    ("INK003", "Canon PG-545 Black Ink Cartridge", "Canon", "Ink & Toner", "Cartridges", True, False, "active", "SUBSTITUTION_PORTFOLIO", 7.20, 6.00, 22.00, 16.99, 320),
    ("INK004", "123inkt Canon PG-545 Compatible Black", "123inkt", "Ink & Toner", "Compatible Cartridges", False, True, "active", "SUBSTITUTION_PORTFOLIO", 1.80, 1.50, 10.00, 5.99, 290),
    ("INK005", "Epson T2991 Black Ink Cartridge", "Epson", "Ink & Toner", "Cartridges", True, False, "active", "SUBSTITUTION_PORTFOLIO", 9.00, 8.00, 28.00, 21.99, 280),
    ("INK006", "Brother TN-2420 Black Toner Cartridge", "Brother", "Ink & Toner", "Cartridges", True, False, "active", "COMPETITOR_INDEX", 22.00, 18.00, 65.00, 49.99, 190),
    # Office Supplies
    ("OFF001", "Staedtler Ballpoint Pen Pack 10", "Staedtler", "Office Supplies", "Pens & Pencils", False, False, "active", "REPEAT_PURCHASE", 1.20, 1.00, 8.00, 4.99, 800),
    ("OFF002", "Avery Lever Arch File A4 Blue", "Avery", "Office Supplies", "Filing & Binders", False, False, "active", "MARGIN_OPTIMIZATION", 2.50, 2.00, 12.00, 6.49, 350),
    ("OFF003", "Scotch Magic Tape 33m", "3M", "Office Supplies", "Filing & Binders", False, False, "active", "REPEAT_PURCHASE", 0.80, 0.60, 5.00, 2.99, 950),
    ("OFF004", "Post-it Notes 76x76mm Yellow Pack 6", "3M", "Office Supplies", "Pens & Pencils", False, False, "active", "REPEAT_PURCHASE", 2.00, 1.50, 10.00, 5.49, 600),
    # Paper
    ("PAP001", "Double A Copy Paper A4 80g 500 sheets", "Double A", "Paper", "Copy Paper", False, False, "active", "VOLUME_DISCOUNT", 1.80, 1.50, 8.00, 4.49, 2500),
    ("PAP002", "Navigator Copy Paper A4 80g Box 5 Reams", "Navigator", "Paper", "Copy Paper", False, False, "active", "VOLUME_DISCOUNT", 8.00, 7.00, 28.00, 19.99, 1800),
    ("PAP003", "Clairefontaine Coloured Paper A4 80g Red", "Clairefontaine", "Paper", "Specialty Paper", False, False, "active", "MARGIN_OPTIMIZATION", 2.20, 1.80, 10.00, 6.99, 300),
    # Packaging
    ("PKG001", "Jiffy Bubble Wrap Roll 50m x 100cm", "Jiffy", "Packaging", "Bubble Wrap", False, False, "active", "VOLUME_DISCOUNT", 6.00, 5.00, 25.00, 14.99, 400),
    ("PKG002", "Standard Cardboard Box 60x40x40cm Pack 10", "123inkt", "Packaging", "Cardboard Boxes", False, True, "active", "VOLUME_DISCOUNT", 8.00, 7.00, 30.00, 18.99, 550),
    # Cleaning
    ("CLN001", "Flash Floor Cleaner Lemon 2L", "Flash", "Cleaning", "Floor Cleaning", False, False, "active", "REPEAT_PURCHASE", 1.50, 1.20, 7.00, 3.99, 700),
    ("CLN002", "Dettol Surface Spray 750ml", "Dettol", "Cleaning", "Surface Cleaners", False, False, "active", "REPEAT_PURCHASE", 1.20, 1.00, 6.00, 3.49, 600),
    # Canteen
    ("CAN001", "Douwe Egberts Ground Coffee 1kg", "Douwe Egberts", "Canteen Supplies", "Coffee & Tea", False, False, "active", "REPEAT_PURCHASE", 6.00, 5.00, 22.00, 12.99, 450),
    ("CAN002", "Disposable Coffee Cups 8oz Pack 50", "123inkt", "Canteen Supplies", "Cups & Disposables", False, True, "active", "BASKET_BUILDER", 2.00, 1.50, 9.00, 4.99, 380),
    # Electronics
    ("ELC001", "USB-C to USB-A Cable 1m", "Belkin", "Electronics", "Cables & Adapters", False, False, "active", "COMPETITOR_INDEX", 3.00, 2.50, 15.00, 8.99, 650),
    ("ELC002", "SanDisk USB Flash Drive 32GB", "SanDisk", "Electronics", "Storage & USB", False, False, "active", "COMPETITOR_INDEX", 4.00, 3.50, 18.00, 9.99, 480),
    # Furniture
    ("FRN001", "Ergonomic Office Chair Black Mesh", "Fellowes", "Furniture", "Office Chairs", False, False, "active", "LOW_VELOCITY", 80.00, 70.00, 350.00, 189.00, 25),
    ("FRN002", "Height Adjustable Desk 160x80cm", "IKEA", "Furniture", "Desks", False, False, "active", "LOW_VELOCITY", 150.00, 120.00, 600.00, 299.00, 15),
    # Printers
    ("PRT001", "HP LaserJet Pro M15w", "HP", "Printers", "Laser Printers", True, False, "active", "COMPETITOR_INDEX", 55.00, 50.00, 200.00, 129.00, 80),
    ("PRT002", "Canon PIXMA TS305 Inkjet Printer", "Canon", "Printers", "Inkjet Printers", True, False, "active", "COMPETITOR_INDEX", 28.00, 25.00, 95.00, 59.00, 110),
    # Stock clearance
    ("CLR001", "Sony Xperia Ear Piece (EOL)", "Sony", "Electronics", "Cables & Adapters", False, False, "end_of_life", "STOCK_CLEARANCE", 12.00, 10.00, 45.00, 19.99, 5),
]


def seed_database():
    db = SessionLocal()
    try:
        if db.query(models.User).count() > 0:
            return  # Already seeded

        # ── Users ──────────────────────────────────────────────────────────
        users = [
            models.User(username="admin", email="admin@pricing.local", full_name="System Admin",
                        hashed_password=auth_utils.hash_password("admin123"), role="admin", is_active=True),
            models.User(username="pricing_manager", email="manager@pricing.local", full_name="Sarah van den Berg",
                        hashed_password=auth_utils.hash_password("manager123"), role="pricing_manager", is_active=True),
            models.User(username="analyst", email="analyst@pricing.local", full_name="Jan de Vries",
                        hashed_password=auth_utils.hash_password("analyst123"), role="analyst", is_active=True),
            models.User(username="viewer", email="viewer@pricing.local", full_name="Lisa Smit",
                        hashed_password=auth_utils.hash_password("viewer123"), role="viewer", is_active=True),
        ]
        db.add_all(users)
        db.commit()

        # ── Categories ────────────────────────────────────────────────────
        seen_cats = set()
        for cat, sub, strategy in CATEGORIES:
            if cat not in seen_cats:
                db.add(models.DimCategory(name=cat, default_strategy=strategy))
                seen_cats.add(cat)
        db.commit()

        # ── Category Strategy Mappings ────────────────────────────────────
        for cat, sub, strategy in CATEGORIES:
            db.add(models.CategoryStrategyMapping(
                category=cat,
                subcategory=sub,
                strategy_type=strategy,
                updated_by="admin",
            ))
        db.commit()

        # ── Products ──────────────────────────────────────────────────────
        for row in PRODUCTS:
            sku_id, name, brand, cat, subcat, is_pl, is_ab, lifecycle, strategy, cost, min_p, max_p, curr, stock = row
            db.add(models.DimProduct(
                sku_id=sku_id,
                product_name=name,
                brand=brand,
                category=cat,
                subcategory=subcat,
                is_private_label=is_pl,
                is_a_brand=is_ab,
                lifecycle_status=lifecycle,
                strategy_type=strategy,
                cost_price=cost,
                min_price=min_p,
                max_price=max_p,
                current_price=curr,
                stock_quantity=stock,
                data_quality_score=random.uniform(0.75, 1.0),
            ))
        db.commit()

        # ── Substitution mappings ─────────────────────────────────────────
        substitutions = [
            ("INK001", "INK002"),
            ("INK003", "INK004"),
        ]
        for a_brand, pl in substitutions:
            db.add(models.MapSubstitution(
                a_brand_sku=a_brand,
                private_label_sku=pl,
                substitution_strength=0.85,
            ))
        db.commit()

        # ── Historical fact data (90 days) ───────────────────────────────
        today = date.today()
        skus = [p[0] for p in PRODUCTS]
        sku_base_prices = {p[0]: p[12] for p in PRODUCTS}  # current_price
        sku_cost_prices = {p[0]: p[9] for p in PRODUCTS}   # cost_price
        sku_stock = {p[0]: p[13] for p in PRODUCTS}         # stock_quantity

        for sku_id in skus:
            base_price = sku_base_prices[sku_id]
            cost = sku_cost_prices[sku_id]
            base_stock = sku_stock[sku_id]
            base_units = max(1, int(base_stock * 0.03))  # ~3% of stock sold daily

            for day_offset in range(90, 0, -1):
                d = today - timedelta(days=day_offset)
                # Price with small daily noise
                price = base_price * random.uniform(0.97, 1.03)
                units = max(0, int(base_units * random.uniform(0.6, 1.4)))
                revenue = price * units
                margin_per_unit = price - cost
                margin = margin_per_unit * units
                margin_pct = (margin_per_unit / price) if price > 0 else 0
                stock = max(0, base_stock - day_offset * base_units // 2)

                db.add(models.FactPriceDaily(date=d, sku_id=sku_id, price=round(price, 4), cost_price=cost))
                db.add(models.FactSalesDaily(date=d, sku_id=sku_id, units_sold=units,
                                              revenue=round(revenue, 4), cost=round(cost * units, 4),
                                              margin=round(margin, 4), margin_pct=round(margin_pct, 4)))
                db.add(models.FactInventoryDaily(date=d, sku_id=sku_id,
                                                  stock_quantity=stock,
                                                  days_of_stock=stock / base_units if base_units > 0 else None))

                # Competitor prices (not for all SKUs)
                if random.random() > 0.3:
                    for comp in random.sample(COMPETITORS, k=random.randint(1, 3)):
                        comp_price = price * random.uniform(0.92, 1.08)
                        db.add(models.FactCompetitorPriceDaily(
                            date=d, sku_id=sku_id,
                            competitor_name=comp,
                            price=round(comp_price, 4),
                        ))

        db.commit()

        # ── Basket affinity (canteen pairs) ───────────────────────────────
        db.add(models.FactBasketAffinity(sku_id_a="CAN001", sku_id_b="CAN002", affinity_score=0.82, co_purchase_count=342))
        db.add(models.FactBasketAffinity(sku_id_a="CAN002", sku_id_b="CAN001", affinity_score=0.82, co_purchase_count=342))
        db.add(models.FactBasketAffinity(sku_id_a="PRT001", sku_id_b="INK006", affinity_score=0.91, co_purchase_count=580))
        db.add(models.FactBasketAffinity(sku_id_a="PRT002", sku_id_b="INK003", affinity_score=0.88, co_purchase_count=410))
        db.commit()

        # ── Pricing recommendations (today) ──────────────────────────────
        # Seed pre-built recommendations so the dashboard is populated immediately
        strategy_recs = [
            ("INK001", 18.49, -2.6, 0.82, "COMPETITOR_PRICE_PRESSURE", "SUBSTITUTION_PORTFOLIO", "ok", "pending"),
            ("INK002", 6.99, -6.7, 0.76, "PRIVATE_LABEL_SUBSTITUTION_OPPORTUNITY", "SUBSTITUTION_PORTFOLIO", "ok", "approved"),
            ("INK003", 16.49, -2.9, 0.78, "COMPETITOR_PRICE_PRESSURE", "SUBSTITUTION_PORTFOLIO", "ok", "pending"),
            ("INK004", 5.49, -8.3, 0.74, "PRIVATE_LABEL_SUBSTITUTION_OPPORTUNITY", "SUBSTITUTION_PORTFOLIO", "ok", "approved"),
            ("INK005", 22.99, 4.6, 0.69, "MARGIN_UPSIDE_PRICE_INCREASE", "SUBSTITUTION_PORTFOLIO", "warning", "pending"),
            ("INK006", 47.99, -4.0, 0.85, "COMPETITOR_PRICE_PRESSURE", "COMPETITOR_INDEX", "ok", "approved"),
            ("OFF001", 5.29, 6.0, 0.72, "MARGIN_UPSIDE_PRICE_INCREASE", "REPEAT_PURCHASE", "ok", "pending"),
            ("OFF002", 6.99, 7.7, 0.68, "MARGIN_UPSIDE_PRICE_INCREASE", "MARGIN_OPTIMIZATION", "ok", "pending"),
            ("OFF003", 3.19, 6.7, 0.75, "MARGIN_UPSIDE_PRICE_INCREASE", "REPEAT_PURCHASE", "warning", "pending"),
            ("PAP001", 4.29, -4.5, 0.88, "COMPETITOR_PRICE_PRESSURE", "VOLUME_DISCOUNT", "ok", "approved"),
            ("PAP002", 18.99, -5.0, 0.85, "COMPETITOR_PRICE_PRESSURE", "VOLUME_DISCOUNT", "ok", "pending"),
            ("PKG001", 14.49, -3.3, 0.80, "COMPETITOR_PRICE_PRESSURE", "VOLUME_DISCOUNT", "ok", "pending"),
            ("PKG002", 17.99, -5.3, 0.78, "COMPETITOR_PRICE_PRESSURE", "VOLUME_DISCOUNT", "ok", "approved"),
            ("CLN001", 3.99, 0.0, 0.82, "REPEAT_PURCHASE_PRICE_STABILITY", "REPEAT_PURCHASE", "ok", "approved"),
            ("CLN002", 3.49, 0.0, 0.80, "REPEAT_PURCHASE_PRICE_STABILITY", "REPEAT_PURCHASE", "ok", "pending"),
            ("CAN001", 12.49, -3.8, 0.83, "COMPETITOR_PRICE_PRESSURE", "REPEAT_PURCHASE", "ok", "approved"),
            ("CAN002", 4.79, -4.0, 0.77, "BASKET_BUILDER_KEEP_COMPETITIVE", "BASKET_BUILDER", "ok", "pending"),
            ("ELC001", 8.49, -5.6, 0.88, "COMPETITOR_PRICE_PRESSURE", "COMPETITOR_INDEX", "ok", "approved"),
            ("ELC002", 9.49, -5.0, 0.87, "COMPETITOR_PRICE_PRESSURE", "COMPETITOR_INDEX", "ok", "pending"),
            ("FRN001", 185.00, -2.1, 0.61, "LOW_VELOCITY_MARGIN_PROTECTION", "LOW_VELOCITY", "warning", "pending"),
            ("FRN002", 295.00, -1.3, 0.58, "KEEP_PRICE_LOW_CONFIDENCE", "LOW_VELOCITY", "warning", "pending"),
            ("PRT001", 124.00, -3.9, 0.86, "COMPETITOR_PRICE_PRESSURE", "COMPETITOR_INDEX", "ok", "approved"),
            ("PRT002", 56.50, -4.2, 0.83, "COMPETITOR_PRICE_PRESSURE", "COMPETITOR_INDEX", "ok", "pending"),
            ("CLR001", 15.99, -20.0, 0.90, "STOCK_CLEARANCE_DISCOUNT", "STOCK_CLEARANCE", "ok", "approved"),
        ]

        sku_prices_map = {p[0]: p[12] for p in PRODUCTS}  # current price

        for row in strategy_recs:
            sku_id, rec_price, chg_pct, conf, reason, strategy, safety, approval = row
            curr_p = sku_prices_map.get(sku_id, rec_price)
            cost = sku_cost_prices.get(sku_id, curr_p * 0.5)
            units = max(1, int(sku_stock.get(sku_id, 50) * 0.03))
            margin_pu = rec_price - cost
            margin_uplift = margin_pu * units - (curr_p - cost) * units

            approved_by = None
            if approval == "approved":
                approved_by = random.choice(["pricing_manager", "admin"])

            db.add(models.FactPricingRecommendationDaily(
                date=today,
                sku_id=sku_id,
                current_price=curr_p,
                recommended_price=rec_price,
                recommended_change_pct=chg_pct,
                expected_units=float(units),
                expected_revenue=round(rec_price * units, 2),
                expected_margin=round(margin_pu * units, 2),
                expected_margin_uplift=round(margin_uplift, 2),
                confidence_score=conf,
                reason_code=reason,
                strategy_type=strategy,
                safety_status=safety,
                approval_status=approval,
                approved_by=approved_by,
                pushed_to_priceshape=False,
                model_version="v1.0.0",
            ))

        db.commit()

        # ── Model run record ──────────────────────────────────────────────
        db.add(models.ModelRun(
            started_at=datetime.utcnow() - timedelta(minutes=8),
            completed_at=datetime.utcnow() - timedelta(minutes=2),
            status="completed",
            skus_processed=len(PRODUCTS),
            skus_skipped=0,
            model_version="v1.0.0",
        ))
        db.commit()

        # ── Import job history ─────────────────────────────────────────────
        for upload_type, filename in [
            ("products", "product_master_2024_q4.csv"),
            ("sales", "sales_history_90days.csv"),
            ("competitor_prices", "priceshape_export_2024_12_01.csv"),
            ("inventory", "stock_levels_current.csv"),
        ]:
            db.add(models.ImportJob(
                upload_type=upload_type,
                filename=filename,
                status="completed",
                rows_processed=random.randint(100, 5000),
                rows_failed=random.randint(0, 5),
                uploaded_by="admin",
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 7)),
                completed_at=datetime.utcnow() - timedelta(days=random.randint(1, 7)),
            ))
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
    finally:
        db.close()
