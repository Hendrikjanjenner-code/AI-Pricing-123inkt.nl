"""
Demo data seeder.
Creates a realistic dataset of products, categories, sales, prices,
competitor prices, inventory, substitutions, and pricing recommendations.
Only runs if the database is empty.
"""
import os
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


def seed_users_only():
    """
    Create the 4 demo user accounts if no users exist yet.
    Always called on startup so login works on a fresh empty DB.
    """
    db = SessionLocal()
    try:
        if db.query(models.User).count() > 0:
            return
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
    except Exception:
        db.rollback()
    finally:
        db.close()


def ensure_owner_admin():
    """
    Idempotently create/update a real admin account from environment config.

    Reads OWNER_ADMIN_EMAIL (plain env) and OWNER_ADMIN_PASSWORD (secret).
    Runs on every startup so the account exists in whatever environment has the
    config set (dev and production). Secrets are global, so the same password is
    available in production after a redeploy. The plaintext password is never
    stored in source. No-op when either value is missing. Never deletes data.
    Login is by username, so username is set to the email address.
    """
    email = os.environ.get("OWNER_ADMIN_EMAIL", "").strip()
    password = os.environ.get("OWNER_ADMIN_PASSWORD", "")
    if not email or not password:
        return
    db = SessionLocal()
    try:
        user = (
            db.query(models.User)
            .filter((models.User.username == email) | (models.User.email == email))
            .first()
        )
        if user is not None:
            user.username = email
            user.email = email
            user.hashed_password = auth_utils.hash_password(password)
            user.role = "admin"
            user.is_active = True
        else:
            db.add(
                models.User(
                    username=email,
                    email=email,
                    full_name=email.split("@")[0],
                    hashed_password=auth_utils.hash_password(password),
                    role="admin",
                    is_active=True,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.getLogger("uvicorn.error").exception(
            "ensure_owner_admin: failed to create/update owner admin account"
        )
    finally:
        db.close()


def seed_database():
    db = SessionLocal()
    try:
        # Guard on business data, not users — seed_users_only() runs before this
        # so User.count() > 0 would always short-circuit when SEED_DEMO_DATA=true.
        if db.query(models.DimProduct).count() > 0:
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
        # Idempotent: sla users over die al bestaan (seed_users_only draait eerder)
        existing_usernames = {u.username for u in db.query(models.User).all()}
        db.add_all([u for u in users if u.username not in existing_usernames])
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
                exported=False,
                model_version="v1.0.0",
            ))

        db.commit()

        # ── Competition Intelligence scores ───────────────────────────────
        # Pre-computed PCIS scores per SKU.
        # Columns: sku_id, comparability, price_sensitivity, substitution,
        #          comp_relevance, price_reliability, basket_dep, strategic_imp,
        #          pcis, class, price_index, comp_used, comp_excl, excl_reasons
        COMPETITION_SCORES = [
            ("INK001", 0.85, 0.62, 0.70, 0.75, 0.78, 0.05, 0.38, 0.72, "Strong",   0.97, 3, 1, {"COMPETITOR_IGNORED_OUTLIER": 1}),
            ("INK002", 0.80, 0.72, 0.90, 0.75, 0.80, 0.05, 0.15, 0.76, "Strong",   0.99, 3, 0, {}),
            ("INK003", 0.83, 0.58, 0.70, 0.75, 0.76, 0.05, 0.32, 0.70, "Strong",   0.97, 3, 1, {"COMPETITOR_IGNORED_OUTLIER": 1}),
            ("INK004", 0.78, 0.68, 0.90, 0.75, 0.79, 0.05, 0.12, 0.74, "Strong",   0.98, 2, 0, {}),
            ("INK005", 0.72, 0.55, 0.68, 0.50, 0.72, 0.05, 0.35, 0.62, "Influence",1.02, 2, 1, {"COMPETITOR_IGNORED_OUT_OF_STOCK": 1}),
            ("INK006", 0.80, 0.75, 0.10, 0.75, 0.82, 0.05, 0.52, 0.65, "Influence",0.96, 3, 0, {}),
            ("OFF001", 0.65, 0.55, 0.05, 0.50, 0.68, 0.10, 0.22, 0.48, "Influence",1.01, 2, 0, {}),
            ("OFF002", 0.45, 0.38, 0.05, 0.25, 0.55, 0.10, 0.28, 0.35, "Monitor",  1.03, 1, 0, {}),
            ("OFF003", 0.55, 0.52, 0.05, 0.50, 0.65, 0.10, 0.18, 0.44, "Monitor",  0.99, 2, 0, {}),
            ("OFF004", 0.58, 0.50, 0.05, 0.50, 0.62, 0.10, 0.25, 0.47, "Influence",1.00, 2, 1, {"COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE": 1}),
            ("PAP001", 0.88, 0.90, 0.05, 0.75, 0.85, 0.05, 0.42, 0.82, "Strong",   0.96, 3, 0, {}),
            ("PAP002", 0.85, 0.88, 0.05, 0.75, 0.82, 0.05, 0.45, 0.81, "Strong",   0.95, 3, 1, {"COMPETITOR_IGNORED_BAD_MATCH": 1}),
            ("PAP003", 0.60, 0.55, 0.05, 0.50, 0.65, 0.05, 0.32, 0.54, "Influence",1.04, 2, 0, {}),
            ("PKG001", 0.65, 0.62, 0.05, 0.50, 0.70, 0.05, 0.28, 0.57, "Influence",0.97, 2, 0, {}),
            ("PKG002", 0.68, 0.65, 0.05, 0.50, 0.68, 0.05, 0.35, 0.58, "Influence",0.98, 2, 1, {"COMPETITOR_IGNORED_OUTLIER": 1}),
            ("CLN001", 0.48, 0.45, 0.05, 0.50, 0.60, 0.82, 0.22, 0.44, "Monitor",  1.00, 2, 0, {}),
            ("CLN002", 0.45, 0.42, 0.05, 0.50, 0.58, 0.78, 0.20, 0.43, "Monitor",  1.01, 2, 0, {}),
            ("CAN001", 0.55, 0.50, 0.05, 0.25, 0.62, 0.88, 0.28, 0.52, "Influence",0.96, 1, 0, {}),
            ("CAN002", 0.50, 0.45, 0.05, 0.25, 0.58, 0.82, 0.18, 0.48, "Influence",0.97, 1, 0, {}),
            ("ELC001", 0.92, 0.85, 0.05, 0.75, 0.88, 0.05, 0.38, 0.78, "Strong",   0.94, 3, 1, {"COMPETITOR_IGNORED_OUTLIER": 1}),
            ("ELC002", 0.90, 0.82, 0.05, 0.75, 0.85, 0.05, 0.42, 0.76, "Strong",   0.95, 3, 0, {}),
            ("FRN001", 0.35, 0.15, 0.05, 0.25, 0.52, 0.05, 0.58, 0.32, "Monitor",  0.98, 1, 0, {}),
            ("FRN002", 0.32, 0.12, 0.05, 0.25, 0.48, 0.05, 0.62, 0.30, "Monitor",  0.99, 1, 0, {}),
            ("PRT001", 0.88, 0.85, 0.05, 0.75, 0.85, 0.05, 0.55, 0.74, "Strong",   0.96, 3, 1, {"COMPETITOR_IGNORED_BAD_DELIVERY": 1}),
            ("PRT002", 0.85, 0.82, 0.05, 0.75, 0.82, 0.05, 0.48, 0.71, "Strong",   0.95, 3, 0, {}),
            ("CLR001", 0.15, 0.12, 0.05, 0.25, 0.35, 0.02, 0.08, 0.14, "Ignore",   1.25, 0, 2, {"COMPETITOR_IGNORED_LOW_RELEVANCE": 2}),
        ]

        for row in COMPETITION_SCORES:
            sku_id, comp, ps, sub, cr, pr, bd, si, pcis, cls, pi, cu, ce, er = row
            p = next((prod for prod in PRODUCTS if prod[0] == sku_id), None)
            ref_price = round(float(p[12]) / pi, 4) if p and pi else None  # ref = current / price_index
            db.add(models.SkuCompetitionScore(
                sku_id=sku_id,
                run_date=today,
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

        # ── A/B Test experiment ───────────────────────────────────────────
        # 13 SKUs in AI group, 13 in CONTROL group.
        # AI group: receives AI-recommended prices (higher margin/revenue).
        # CONTROL group: prices unchanged (baseline performance).
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

        # sku_id, group, bl_price, curr_price, bl_units, curr_units, bl_conv, curr_conv
        AB_SKUS = [
            # AI group — prices adjusted per recommendation
            ("INK001", "AI",   18.99, 18.49,  14, 15, 0.0480, 0.0510),
            ("INK003", "AI",   16.99, 16.49,  10, 11, 0.0420, 0.0455),
            ("INK005", "AI",   21.99, 22.49,   8,  8, 0.0350, 0.0348),
            ("OFF001", "AI",    4.99,  5.29,  24, 23, 0.0620, 0.0610),
            ("PAP001", "AI",    4.49,  4.29,  75, 82, 0.0820, 0.0870),
            ("PKG001", "AI",   14.99, 14.49,  12, 13, 0.0390, 0.0415),
            ("CLN001", "AI",    3.99,  3.99,  21, 21, 0.0680, 0.0682),
            ("CAN001", "AI",   12.99, 12.49,  14, 15, 0.0510, 0.0540),
            ("ELC001", "AI",    8.99,  8.49,  20, 22, 0.0720, 0.0785),
            ("FRN001", "AI",  189.00,185.00,   1,  1, 0.0085, 0.0088),
            ("PRT001", "AI",  129.00,124.00,   2,  3, 0.0120, 0.0145),
            ("PAP003", "AI",    6.99,  6.99,   9,  9, 0.0340, 0.0342),
            ("PKG002", "AI",   18.99, 17.99,  17, 19, 0.0480, 0.0520),
            # CONTROL group — prices unchanged
            ("INK002", "CONTROL", 7.49,  7.49,  11, 11, 0.0520, 0.0519),
            ("INK004", "CONTROL", 5.99,  5.99,   9,  9, 0.0490, 0.0491),
            ("INK006", "CONTROL",49.99, 49.99,   6,  6, 0.0310, 0.0309),
            ("OFF002", "CONTROL", 6.49,  6.49,  11, 11, 0.0430, 0.0430),
            ("PAP002", "CONTROL",19.99, 19.99,  54, 54, 0.0780, 0.0779),
            ("CLN002", "CONTROL", 3.49,  3.49,  18, 18, 0.0650, 0.0650),
            ("CAN002", "CONTROL", 4.99,  4.99,  11, 11, 0.0470, 0.0470),
            ("ELC002", "CONTROL", 9.99,  9.99,  14, 14, 0.0690, 0.0688),
            ("FRN002", "CONTROL",299.00,299.00,  0,  0, 0.0075, 0.0074),
            ("PRT002", "CONTROL", 59.00, 59.00,  3,  3, 0.0130, 0.0130),
            ("OFF003", "CONTROL", 2.99,  2.99,  29, 29, 0.0750, 0.0749),
            ("OFF004", "CONTROL", 5.49,  5.49,  18, 18, 0.0570, 0.0570),
            ("CLR001", "CONTROL",19.99, 19.99,   0,  0, 0.0045, 0.0045),
        ]

        for row in AB_SKUS:
            sku_id, grp, bl_p, curr_p, bl_u, curr_u, bl_conv, curr_conv = row
            p = next((prod for prod in PRODUCTS if prod[0] == sku_id), None)
            cost = float(p[9]) if p else float(bl_p) * 0.5
            bl_revenue = round(bl_p * bl_u * 30, 2)
            curr_revenue = round(curr_p * curr_u * 30, 2)
            bl_margin = round((bl_p - cost) * bl_u * 30, 2)
            curr_margin = round((curr_p - cost) * curr_u * 30, 2)
            db.add(models.AbTestResult(
                test_id=ab_test.id,
                sku_id=sku_id,
                group_type=grp,
                baseline_price=bl_p,
                current_price=curr_p,
                baseline_units=float(bl_u),
                current_units=float(curr_u),
                baseline_revenue=bl_revenue,
                current_revenue=curr_revenue,
                baseline_margin=bl_margin,
                current_margin=curr_margin,
                baseline_conversion_rate=bl_conv,
                current_conversion_rate=curr_conv,
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
            ("competitor_prices", "concurrent_prijzen_2024_12_01.csv"),
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
