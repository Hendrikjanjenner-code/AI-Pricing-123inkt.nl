"""
Backfill script — Cost, Marketing, Operational Complexity, Procurement, Economic, BCG Transition, Reports.
Run once: python artifacts/api-server/backfill_intelligence.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import (
    FactCostDaily, FactMarketingCostDaily, FactOperationalComplexityDaily,
    FactProcurementForecastDaily, FactEconomicSignalDaily,
    FactBcgTransition, FactManagementReport, DimProduct,
)
from sqlalchemy import func
from datetime import date

db = SessionLocal()


def already_seeded(model, col=None) -> bool:
    try:
        count = db.query(func.count(model.id)).scalar()
        return bool(count and count > 0)
    except Exception:
        return False


def seed_cost_and_derived():
    """Kosten, marketing en OCS voor alle SKU's."""
    if already_seeded(FactCostDaily):
        print("⏭  FactCostDaily al gevuld — overgeslagen")
    else:
        from engine.cost_engine import run_cost_engine
        n = run_cost_engine(db)
        print(f"✅ FactCostDaily: {n} records")

    if already_seeded(FactMarketingCostDaily):
        print("⏭  FactMarketingCostDaily al gevuld — overgeslagen")
    else:
        from engine.marketing_efficiency import run_marketing_engine
        n = run_marketing_engine(db)
        print(f"✅ FactMarketingCostDaily: {n} records")

    if already_seeded(FactOperationalComplexityDaily):
        print("⏭  FactOperationalComplexityDaily al gevuld — overgeslagen")
    else:
        from engine.operational_complexity import run_operational_complexity_engine
        n = run_operational_complexity_engine(db)
        print(f"✅ FactOperationalComplexityDaily: {n} records")


def seed_procurement():
    if already_seeded(FactProcurementForecastDaily):
        print("⏭  FactProcurementForecastDaily al gevuld — overgeslagen")
        return
    from engine.procurement_forecasting import run_procurement_engine
    n = run_procurement_engine(db)
    print(f"✅ FactProcurementForecastDaily: {n} records")


def seed_economic():
    if already_seeded(FactEconomicSignalDaily):
        print("⏭  FactEconomicSignalDaily al gevuld — overgeslagen")
        return
    from engine.economic_intelligence import seed_economic_signals
    n = seed_economic_signals(db)
    print(f"✅ FactEconomicSignalDaily: {n} records")


def seed_bcg_transitions():
    if already_seeded(FactBcgTransition):
        print("⏭  FactBcgTransition al gevuld — overgeslagen")
        return
    from engine.bcg_transition_engine import seed_bcg_transitions as _seed
    n = _seed(db)
    print(f"✅ FactBcgTransition: {n} records")


def seed_reports():
    if already_seeded(FactManagementReport):
        print("⏭  FactManagementReport al gevuld — overgeslagen")
        return
    from engine.reporting_engine import run_reporting_engine
    n = run_reporting_engine(db)
    print(f"✅ FactManagementReport: {n} records")


if __name__ == "__main__":
    print("🚀 Backfill Intelligence Engine starten…")
    seed_cost_and_derived()
    seed_procurement()
    seed_economic()
    seed_bcg_transitions()
    seed_reports()
    print("🎉 Backfill voltooid!")
    db.close()
