"""
Seed de 4 nieuwe Cost Change & Break-even tabellen met demo data.
Veilig om meerdere keren te draaien — controleert of al gevuld is.
"""
import random
from datetime import date, datetime
from database import SessionLocal
import models
from models import (
    DimProduct, FactCostChangeDaily, FactBreakEvenAnalysisDaily,
    FactPricePassThroughDaily, FactMarketingVsDiscountDaily,
    FactBcgClassificationDaily,
)
from engine.cost_change_engine import calculate_ppfs, calculate_mps
from engine.break_even_engine import (
    calculate_margin_per_unit, calculate_break_even_units,
    calculate_break_even_traffic, calculate_required_conversion_uplift,
    calculate_beds, generate_break_even_explanation_nl,
)
from engine.price_pass_through_engine import compute_ppfs_record
from engine.marketing_margin_engine import (
    calculate_meds, simulate_price_reduction_scenario,
    simulate_seo_scenario, simulate_sea_scenario,
)

random.seed(99)
db = SessionLocal()
TODAY = date.today()

# Demo scenarios per SKU (kostprijswijziging %)
DEMO_COST_CHANGES = {
    "INK001": {"pct": 15.0, "type": "SUPPLIER",   "scenario": "Inkoopprijs HP +15%"},
    "INK002": {"pct": 12.0, "type": "SUPPLIER",   "scenario": "Compatibele cartridge +12%"},
    "INK003": {"pct": 8.0,  "type": "TRANSPORT",  "scenario": "Transportkosten stijging"},
    "INK004": {"pct": 5.0,  "type": "CURRENCY",   "scenario": "Valuta-effect USD/EUR"},
    "INK005": {"pct": 18.0, "type": "SUPPLIER",   "scenario": "Epson prijsverhoging"},
    "INK006": {"pct": 10.0, "type": "SURCHARGE",  "scenario": "Brother toeslag"},
    "OFF001": {"pct": 3.0,  "type": "SUPPLIER",   "scenario": "Kleine verhoging"},
    "OFF002": {"pct": 6.0,  "type": "FULFILMENT", "scenario": "Fulfilment kosten omhoog"},
    "OFF003": {"pct": 4.0,  "type": "SUPPLIER",   "scenario": "3M prijsaanpassing"},
    "OFF004": {"pct": 7.0,  "type": "TRANSPORT",  "scenario": "Post-it transport"},
    "PAP001": {"pct": 20.0, "type": "SUPPLIER",   "scenario": "Papierprijsschok (+20%)"},
    "PAP002": {"pct": 22.0, "type": "SUPPLIER",   "scenario": "Bulk papier verhoging"},
    "PAP003": {"pct": 9.0,  "type": "CURRENCY",   "scenario": "Franse import valuta"},
    "PKG001": {"pct": 25.0, "type": "TRANSPORT",  "scenario": "Containervracht +25%"},
    "PKG002": {"pct": 11.0, "type": "SUPPLIER",   "scenario": "Karton prijsstijging"},
}

# Break-even scenario's
BE_SCENARIOS = {
    "INK001": {"new_price_factor": 0.90, "scenario": "PRICE_REDUCTION"},   # -10%
    "INK002": {"new_price_factor": 0.85, "scenario": "PROMOTION"},          # -15%
    "PAP001": {"new_price_factor": 0.80, "scenario": "PRICE_REDUCTION"},   # -20%
    "PAP002": {"new_price_factor": 0.88, "scenario": "BUNDLE"},             # -12%
    "PKG001": {"new_price_factor": 0.92, "scenario": "CATEGORY_PROMO"},    # -8%
    "OFF001": {"new_price_factor": 0.95, "scenario": "LAUNCH_PROMO"},      # -5%
}


def already_seeded():
    return db.query(FactCostChangeDaily).count() > 0


def seed_cost_changes():
    prods = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()}

    for sku_id, change in DEMO_COST_CHANGES.items():
        prod = prods.get(sku_id)
        if not prod:
            continue

        cp = float(prod.cost_price or 5.0)
        sp = float(prod.current_price or cp * 1.5)
        prev_cp = round(cp / (1 + change["pct"] / 100), 4)

        # Transportkosten etc.
        transport = round(sp * 0.04, 4)
        fulfil = round(sp * 0.05, 4)
        mkt = round(sp * 0.03, 4)
        ops = round(sp * 0.02, 4)
        total_unit = round(cp + transport + fulfil + mkt + ops, 4)

        gross_margin = round((sp - cp) / sp * 100, 2) if sp > 0 else 0
        net_margin = round((sp - total_unit) / sp * 100, 2) if sp > 0 else 0
        contrib = round(sp - total_unit, 4)

        # PPFS score
        ppfs_data = calculate_ppfs(sku_id, prod.category or "", change["pct"], db)
        mps_data = calculate_mps(net_margin, change["pct"], ppfs_data["ppfs_score"])

        rec = FactCostChangeDaily(
            date=TODAY,
            sku_id=sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            previous_cost_price=prev_cp,
            current_cost_price=cp,
            cost_change_pct=change["pct"],
            cost_change_type=change["type"],
            transport_cost=transport,
            fulfillment_cost=fulfil,
            marketing_cost=mkt,
            operational_cost=ops,
            total_unit_cost=total_unit,
            current_selling_price=sp,
            gross_margin=gross_margin,
            net_margin=net_margin,
            contribution_margin=contrib,
            ppfs_score=ppfs_data["ppfs_score"],
            mps_score=mps_data["mps_score"],
            severity=mps_data["severity"],
            aanbeveling=ppfs_data["recommendation"],
            reason_nl=ppfs_data["toelichting_nl"],
        )
        db.add(rec)

    db.commit()
    count = db.query(FactCostChangeDaily).count()
    print(f"  ✅ FactCostChangeDaily: {count} records")


def seed_break_even():
    prods = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()}

    for sku_id, be in BE_SCENARIOS.items():
        prod = prods.get(sku_id)
        if not prod:
            continue

        cp = float(prod.cost_price or 5.0)
        sp = float(prod.current_price or cp * 1.5)
        new_price = round(sp * be["new_price_factor"], 4)
        price_change_pct = round((new_price - sp) / sp * 100, 2)

        old_margin = calculate_margin_per_unit(sp, cp)
        new_margin = calculate_margin_per_unit(new_price, cp)
        margin_loss = round(old_margin - new_margin, 4)

        # Demo: gemiddeld 30 units/dag
        current_units = random.randint(20, 60)
        be_units = calculate_break_even_units(old_margin, new_margin, current_units)
        be_units_pct = (be_units / current_units * 100) if current_units > 0 and be_units != float("inf") else 999
        be_traffic = calculate_break_even_traffic(be_units, 0.025)
        be_conv = calculate_required_conversion_uplift(be_units, current_units * 40)

        beds = calculate_beds(be_units_pct, current_units, new_margin)
        aanbeveling = "REDUCE_PRICE" if beds["beds_label"] == "HAALBAAR" else "MAINTAIN_PRICE"
        toelichting = generate_break_even_explanation_nl(
            be["scenario"], price_change_pct, be_units_pct if be_units_pct < 999 else 999,
            beds["beds_label"], aanbeveling
        )

        rec = FactBreakEvenAnalysisDaily(
            date=TODAY,
            sku_id=sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            scenario_type=be["scenario"],
            current_price=sp,
            proposed_price=new_price,
            price_change_pct=price_change_pct,
            current_margin_per_unit=round(old_margin, 4),
            new_margin_per_unit=round(new_margin, 4),
            margin_loss_per_unit=margin_loss,
            current_units_sold=current_units,
            break_even_extra_units=be_units if be_units != float("inf") else None,
            break_even_extra_units_pct=round(be_units_pct, 1) if be_units_pct < 999 else None,
            break_even_extra_revenue=round(be_units * new_price, 2) if be_units != float("inf") else None,
            break_even_extra_traffic=be_traffic if be_traffic != float("inf") else None,
            required_conversion_uplift=round(be_conv, 4) if be_conv != float("inf") else None,
            break_even_difficulty_score=beds["beds_score"],
            beds_label=beds["beds_label"],
            waarschuwing=beds["waarschuwing"],
            aanbeveling=aanbeveling,
            toelichting_nl=toelichting,
        )
        db.add(rec)

    db.commit()
    count = db.query(FactBreakEvenAnalysisDaily).count()
    print(f"  ✅ FactBreakEvenAnalysisDaily: {count} records")


def seed_ppfs():
    prods = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()

    for prod in prods:
        cost_change_pct = DEMO_COST_CHANGES.get(prod.sku_id, {}).get("pct", random.uniform(3.0, 15.0))
        record_data = compute_ppfs_record(prod, cost_change_pct, db, TODAY)

        rec = FactPricePassThroughDaily(
            date=record_data["date"],
            sku_id=record_data["sku_id"],
            sku_name=record_data["sku_name"],
            category=record_data["category"],
            supplier_cost_change_pct=record_data["supplier_cost_change_pct"],
            proposed_price_change_pct=record_data["proposed_price_change_pct"],
            pass_through_ratio=record_data["pass_through_ratio"],
            ppfs_score=record_data["ppfs_score"],
            ppfs_label=record_data["ppfs_label"],
            elasticity_score=record_data["elasticity_score"],
            pricing_power_score=record_data["pricing_power_score"],
            competition_pressure=record_data["competition_pressure"],
            bcg_factor=record_data["bcg_factor"],
            demand_factor=record_data["demand_factor"],
            conversion_health=record_data["conversion_health"],
            recommendation=record_data["recommendation"],
            reason_code=record_data["reason_code"],
            toelichting_nl=record_data["toelichting_nl"],
        )
        db.add(rec)

    db.commit()
    count = db.query(FactPricePassThroughDaily).count()
    print(f"  ✅ FactPricePassThroughDaily: {count} records")


def seed_meds():
    prods = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()
    scenarios = ["PRICE_REDUCTION", "PUSH_SEO", "PUSH_SEA", "COMBINED"]

    for prod in prods:
        sp = float(prod.current_price or 10.0)
        cp = float(prod.cost_price or sp * 0.6)
        current_margin_pct = ((sp - cp) / sp * 100) if sp > 0 else 30.0
        current_units = random.randint(15, 80)
        current_revenue = sp * current_units
        roas = round(random.uniform(2.0, 6.0), 2)
        current_traffic = int(current_units / 0.025)
        conversion_rate = 0.025

        # Sla het meest representatieve scenario op (SEO vs discount)
        sc_a = simulate_price_reduction_scenario(prod, -10.0, current_units, current_revenue, current_margin_pct, roas)
        sc_b = simulate_seo_scenario(prod, 500.0, current_units, current_revenue, current_margin_pct, current_traffic, conversion_rate)

        meds = calculate_meds(
            sc_b["expected_margin_eur"],
            sc_a["expected_margin_eur"],
            sc_b["expected_roas"],
            None,
        )

        rec = FactMarketingVsDiscountDaily(
            date=TODAY,
            sku_id=prod.sku_id,
            sku_name=prod.product_name,
            category=prod.category,
            scenario_type="VERGELIJKING",
            expected_revenue=sc_b["expected_revenue"],
            expected_margin=sc_b["expected_margin"],
            expected_margin_eur=sc_b["expected_margin_eur"],
            expected_traffic=sc_b["expected_traffic"],
            expected_conversion=sc_b["expected_conversion"],
            expected_roas=sc_b["expected_roas"],
            expected_extra_units=sc_b["expected_units"] - current_units,
            meds_score=meds["meds_score"],
            drs_score=round(random.uniform(0.3, 0.9), 3),
            recommended_strategy=meds["recommendation"],
            toelichting_nl=meds["toelichting_nl"],
        )
        db.add(rec)

    db.commit()
    count = db.query(FactMarketingVsDiscountDaily).count()
    print(f"  ✅ FactMarketingVsDiscountDaily: {count} records")


if __name__ == "__main__":
    print("🚀 Backfill Cost Change & Break-even Intelligence…")
    if already_seeded():
        print("⏭  Tabellen al gevuld — overgeslagen")
    else:
        seed_cost_changes()
        seed_break_even()
        seed_ppfs()
        seed_meds()
    print("🎉 Klaar!")
    db.close()
