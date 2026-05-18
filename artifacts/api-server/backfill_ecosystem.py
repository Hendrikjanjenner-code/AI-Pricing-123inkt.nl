"""
Seed de 3 nieuwe Traffic Driver & Basket Intelligence tabellen met demo data.
Veilig om meerdere keren te draaien — controleert of al gevuld is.
"""
import random
from datetime import date
from database import SessionLocal
from models import (
    DimProduct,
    FactSkuEcosystemDaily,
    FactBasketIntelligenceDaily,
    FactTrafficDriverScoreDaily,
)
from engine.traffic_driver_engine import calculate_traffic_driver_score, calculate_entry_product_score
from engine.basket_intelligence import generate_basket_record
from engine.sku_ecosystem_engine import compute_ecosystem_record

random.seed(77)
db = SessionLocal()
TODAY = date.today()

# Demo-profielen per SKU (realistische scenario's)
DEMO_TRAFFIC_PROFILES = {
    "INK001": {
        "seo": 3200, "sea": 1800, "visibility": 0.82, "volume": 45000,
        "landing": 2100, "new_cust": 680, "ctr": 0.072, "trend": 0.85,
        "first_pct": 0.68, "new_first": 0.72, "lp_conv": 0.031,
        "note": "HP 305 toner — kritieke traffic driver, hoog zoekvolume",
    },
    "INK002": {
        "seo": 2100, "sea": 950, "visibility": 0.71, "volume": 28000,
        "landing": 1300, "new_cust": 420, "ctr": 0.065, "trend": 0.78,
        "first_pct": 0.55, "new_first": 0.58, "lp_conv": 0.028,
        "note": "Compatibele cartridge — sterke traffic driver, nieuwe klanten",
    },
    "PAP001": {
        "seo": 800,  "sea": 200,  "visibility": 0.45, "volume": 12000,
        "landing": 400, "new_cust": 90,  "ctr": 0.038, "trend": 0.55,
        "first_pct": 0.22, "new_first": 0.18, "lp_conv": 0.015,
        "note": "A4 papier — lage traffic, sterke basket builder",
    },
    "PAP002": {
        "seo": 950,  "sea": 350,  "visibility": 0.48, "volume": 15000,
        "landing": 600, "new_cust": 110, "ctr": 0.040, "trend": 0.58,
        "first_pct": 0.25, "new_first": 0.20, "lp_conv": 0.018,
        "note": "Bulk papier — hoge basket co-occurrence",
    },
    "OFF001": {
        "seo": 420,  "sea": 180,  "visibility": 0.35, "volume": 8000,
        "landing": 280, "new_cust": 55,  "ctr": 0.030, "trend": 0.42,
        "first_pct": 0.15, "new_first": 0.12, "lp_conv": 0.012,
        "note": "Ordners — lage traffic, hoge basket builder score",
    },
    "OFF002": {
        "seo": 380,  "sea": 150,  "visibility": 0.32, "volume": 6500,
        "landing": 220, "new_cust": 45,  "ctr": 0.028, "trend": 0.40,
        "first_pct": 0.12, "new_first": 0.10, "lp_conv": 0.010,
        "note": "Kantoorbenodigdheden — winkelmandvuller",
    },
    "INK003": {
        "seo": 1800, "sea": 620,  "visibility": 0.62, "volume": 22000,
        "landing": 900, "new_cust": 310, "ctr": 0.058, "trend": 0.70,
        "first_pct": 0.42, "new_first": 0.45, "lp_conv": 0.024,
        "note": "Canon toner — sterk traffic driver",
    },
    "INK004": {
        "seo": 1200, "sea": 480,  "visibility": 0.55, "volume": 18000,
        "landing": 700, "new_cust": 230, "ctr": 0.052, "trend": 0.65,
        "first_pct": 0.35, "new_first": 0.38, "lp_conv": 0.022,
        "note": "Kyocera toner",
    },
    "PKG001": {
        "seo": 280,  "sea": 120,  "visibility": 0.28, "volume": 5000,
        "landing": 180, "new_cust": 30,  "ctr": 0.025, "trend": 0.35,
        "first_pct": 0.08, "new_first": 0.07, "lp_conv": 0.008,
        "note": "Verpakkingsmateriaal — hoge basket co-occurrence",
    },
}


def already_seeded():
    return (
        db.query(FactTrafficDriverScoreDaily).count() > 0
        or db.query(FactBasketIntelligenceDaily).count() > 0
        or db.query(FactSkuEcosystemDaily).count() > 0
    )


def seed_traffic_driver():
    prods = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()}

    for sku_id, prod in prods.items():
        profile = DEMO_TRAFFIC_PROFILES.get(sku_id)
        if profile:
            seo = profile["seo"]
            sea = profile["sea"]
            vis = profile["visibility"]
            vol = profile["volume"]
            lp = profile["landing"]
            nc = profile["new_cust"]
            ctr = profile["ctr"]
            trend = profile["trend"]
            first_pct = profile["first_pct"]
            new_first = profile["new_first"]
            lp_conv = profile["lp_conv"]
            note = profile["note"]
        else:
            rng = random.Random(abs(hash(sku_id)) % 9999)
            seo = rng.randint(100, 1500)
            sea = rng.randint(50, 600)
            vis = rng.uniform(0.20, 0.65)
            vol = rng.randint(2000, 20000)
            lp = rng.randint(80, 800)
            nc = rng.randint(15, 250)
            ctr = rng.uniform(0.020, 0.060)
            trend = rng.uniform(0.30, 0.75)
            first_pct = rng.uniform(0.08, 0.40)
            new_first = rng.uniform(0.06, 0.35)
            lp_conv = rng.uniform(0.008, 0.025)
            note = f"Standaard traffic profiel voor {prod.category}"

        tds_data = calculate_traffic_driver_score(
            seo, sea, vis, vol, lp, nc, ctr, trend, prod.category or ""
        )
        eps = calculate_entry_product_score(first_pct, new_first, lp_conv)

        toelichting = (
            f"{note}. TDS: {tds_data['traffic_driver_score']:.2f} — {tds_data['tds_label']}. "
            f"SEO traffic: {seo:,}, zoekvolume: {vol:,}, nieuwe klanten: {nc}."
        )

        rec = FactTrafficDriverScoreDaily(
            date=TODAY,
            sku_id=sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            seo_traffic=seo,
            sea_traffic=sea,
            direct_traffic=max(10, seo // 8),
            total_traffic=seo + sea + max(10, seo // 8),
            organic_visibility=vis,
            search_volume=vol,
            landing_page_sessions=lp,
            new_customer_entries=nc,
            ctr=ctr,
            first_product_in_session_pct=first_pct,
            new_customer_first_order_pct=new_first,
            traffic_driver_score=tds_data["traffic_driver_score"],
            entry_product_score=eps,
            tds_label=tds_data["tds_label"],
            toelichting_nl=toelichting,
        )
        db.add(rec)

    db.commit()
    count = db.query(FactTrafficDriverScoreDaily).count()
    print(f"  ✅ FactTrafficDriverScoreDaily: {count} records")


def seed_basket_intelligence():
    prods = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()

    for prod in prods:
        record_data = generate_basket_record(prod, db, TODAY)
        rec = FactBasketIntelligenceDaily(**record_data)
        db.add(rec)

    db.commit()
    count = db.query(FactBasketIntelligenceDaily).count()
    print(f"  ✅ FactBasketIntelligenceDaily: {count} records")


def seed_ecosystem():
    prods = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()}

    # Haal TDS en BBS scores op uit eerder geplante records
    tds_recs = {r.sku_id: r for r in db.query(FactTrafficDriverScoreDaily).filter(FactTrafficDriverScoreDaily.date == TODAY).all()}
    bbs_recs = {r.sku_id: r for r in db.query(FactBasketIntelligenceDaily).filter(FactBasketIntelligenceDaily.date == TODAY).all()}

    for sku_id, prod in prods.items():
        tds = float(tds_recs[sku_id].traffic_driver_score) if sku_id in tds_recs else 0.40
        bbs = float(bbs_recs[sku_id].basket_builder_score) if sku_id in bbs_recs else 0.35
        eps = float(tds_recs[sku_id].entry_product_score) if sku_id in tds_recs else 0.30

        record_data = compute_ecosystem_record(prod, tds, bbs, eps, db, TODAY)
        rec = FactSkuEcosystemDaily(**record_data)
        db.add(rec)

    db.commit()
    count = db.query(FactSkuEcosystemDaily).count()
    print(f"  ✅ FactSkuEcosystemDaily: {count} records")


if __name__ == "__main__":
    print("🚀 Backfill Traffic Driver & Basket Intelligence…")
    if already_seeded():
        print("⏭  Tabellen al gevuld — overgeslagen")
    else:
        seed_traffic_driver()
        seed_basket_intelligence()
        seed_ecosystem()
    print("🎉 Klaar!")
    db.close()
