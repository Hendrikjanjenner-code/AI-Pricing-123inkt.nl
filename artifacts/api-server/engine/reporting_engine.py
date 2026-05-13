"""Executive Reporting Engine — dagelijkse/wekelijkse/maandelijkse managementrapportages."""
from __future__ import annotations
from datetime import date, timedelta
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models import (
    FactManagementReport, FactCostDaily, FactEconomicSignalDaily,
    FactBcgTransition, FactProcurementForecastDaily, FactMarketingCostDaily,
    FactPricingRecommendationDaily,
)


def _kpi(value, delta=None, label="", unit="", format_="number"):
    return {"waarde": value, "delta": delta, "label": label, "eenheid": unit, "format": format_}


def generate_daily_report(db: Session, report_date: date | None = None) -> Dict[str, Any]:
    d = report_date or date.today()

    # Kosten data
    cost_recs = db.query(FactCostDaily).filter(FactCostDaily.date == d).all()
    critical_margin = [r for r in cost_recs if r.cost_signal == "MARGIN_CRITICAL"]
    avg_margin = (
        sum(float(r.net_margin_pct or 0) for r in cost_recs) / len(cost_recs)
        if cost_recs else 0
    )

    # Economische signalen
    eco_signals = (
        db.query(FactEconomicSignalDaily)
        .filter(FactEconomicSignalDaily.valid_until >= d)
        .filter(FactEconomicSignalDaily.severity.in_(["HOOG", "KRITIEK"]))
        .all()
    )

    # Procurement
    proc_recs = db.query(FactProcurementForecastDaily).filter(FactProcurementForecastDaily.date == d).all()
    urgent_buy = [r for r in proc_recs if r.signal_code in ("BUY_NOW", "URGENT_BUY")]

    # Aanbevelingen
    recs = (
        db.query(FactPricingRecommendationDaily)
        .filter(FactPricingRecommendationDaily.date == d)
        .all()
    )
    pending_recs = [r for r in recs if r.approval_status == "pending"]

    kpis = {
        "gemiddelde_netto_marge": _kpi(round(avg_margin, 1), None, "Gem. netto marge", "%", "percent"),
        "kritieke_marge_skus": _kpi(len(critical_margin), None, "SKU's kritieke marge", "stuks"),
        "open_aanbevelingen": _kpi(len(pending_recs), None, "Open prijsaanbevelingen", "stuks"),
        "economische_alerts": _kpi(len(eco_signals), None, "Hoge economische risico's", "stuks"),
        "inkoop_kansen": _kpi(len(urgent_buy), None, "Urgente inkoopkansen", "stuks"),
    }

    alerts = []
    for r in critical_margin[:3]:
        alerts.append({
            "code": "MARGIN_CRITICAL",
            "ernst": "KRITIEK",
            "bericht": f"{r.sku_id} — netto marge {r.net_margin_pct:.1f}%",
        })
    for s in eco_signals[:2]:
        alerts.append({
            "code": s.signal_code,
            "ernst": s.severity,
            "bericht": s.signal_name,
        })

    insights = [
        {"sectie": "Marges", "tekst": f"Gemiddelde netto marge is {avg_margin:.1f}%. {len(critical_margin)} SKU's zijn kritiek."},
        {"sectie": "Economie", "tekst": f"{len(eco_signals)} economische signalen vereisen aandacht."},
        {"sectie": "Procurement", "tekst": f"{len(urgent_buy)} SKU's hebben urgente inkoopkansen."},
    ]

    return {
        "report_type": "DAGELIJKS",
        "report_date": d,
        "period_start": d,
        "period_end": d,
        "title_nl": f"Dagelijkse Managementrapportage — {d.strftime('%d %B %Y')}",
        "summary_nl": (
            f"Vandaag zijn {len(pending_recs)} prijsaanbevelingen open. "
            f"Gemiddelde netto marge: {avg_margin:.1f}%. "
            f"{len(eco_signals)} economische risico's actief."
        ),
        "kpis_json": json.dumps(kpis, default=str),
        "alerts_json": json.dumps(alerts, default=str),
        "insights_json": json.dumps(insights, default=str),
        "recommendations_json": json.dumps([
            {"prioriteit": "HOOG", "actie": r.signal_label_nl or r.signal_code}
            for r in urgent_buy[:3]
        ], default=str),
    }


def generate_weekly_report(db: Session, report_date: date | None = None) -> Dict[str, Any]:
    d = report_date or date.today()
    week_start = d - timedelta(days=7)

    bcg_changes = (
        db.query(FactBcgTransition)
        .filter(FactBcgTransition.date >= week_start)
        .all()
    )
    marketing_recs = db.query(FactMarketingCostDaily).filter(FactMarketingCostDaily.date == d).all()
    avg_roas = (
        sum(float(r.roas or 0) for r in marketing_recs) / len(marketing_recs)
        if marketing_recs else 0
    )

    kpis = {
        "bcg_transities": _kpi(len(bcg_changes), None, "BCG-wijzigingen deze week", "stuks"),
        "gemiddelde_roas": _kpi(round(avg_roas, 2), None, "Gemiddelde ROAS", "×"),
        "positieve_transities": _kpi(
            len([b for b in bcg_changes if b.to_classification == "STAR"]),
            None, "Transities naar STAR", "stuks"
        ),
    }

    return {
        "report_type": "WEKELIJKS",
        "report_date": d,
        "period_start": week_start,
        "period_end": d,
        "title_nl": f"Wekelijkse Managementrapportage — week {d.isocalendar()[1]} {d.year}",
        "summary_nl": (
            f"Deze week {len(bcg_changes)} BCG-classificatiewijzigingen. "
            f"Gemiddelde ROAS: {avg_roas:.2f}×."
        ),
        "kpis_json": json.dumps(kpis, default=str),
        "alerts_json": json.dumps([], default=str),
        "insights_json": json.dumps([
            {"sectie": "BCG", "tekst": f"{len(bcg_changes)} BCG transities gedectecteerd deze week."},
            {"sectie": "Marketing", "tekst": f"Gemiddelde ROAS {avg_roas:.2f}× over alle SKU's."},
        ], default=str),
        "recommendations_json": json.dumps([], default=str),
    }


def generate_monthly_report(db: Session, report_date: date | None = None) -> Dict[str, Any]:
    d = report_date or date.today()
    month_start = d.replace(day=1)

    proc_recs = db.query(FactProcurementForecastDaily).filter(FactProcurementForecastDaily.date == d).all()
    high_fmr = [r for r in proc_recs if (r.future_margin_risk_score or 0) > 0.65]
    avg_fmr = sum(float(r.future_margin_risk_score or 0) for r in proc_recs) / len(proc_recs) if proc_recs else 0

    cost_recs = db.query(FactCostDaily).filter(FactCostDaily.date == d).all()
    avg_net = sum(float(r.net_margin_pct or 0) for r in cost_recs) / len(cost_recs) if cost_recs else 0

    kpis = {
        "gemiddelde_netto_marge": _kpi(round(avg_net, 1), -0.8, "Gem. netto marge", "%", "percent"),
        "toekomstig_margerisico": _kpi(len(high_fmr), None, "SKU's hoog margerisico", "stuks"),
        "gem_future_margin_risk": _kpi(round(avg_fmr * 100, 1), None, "Gem. FMR score", "%", "percent"),
    }

    return {
        "report_type": "MAANDELIJKS",
        "report_date": d,
        "period_start": month_start,
        "period_end": d,
        "title_nl": f"Maandrapportage — {d.strftime('%B %Y')}",
        "summary_nl": (
            f"Maandelijkse analyse: gemiddelde netto marge {avg_net:.1f}%. "
            f"{len(high_fmr)} SKU's met hoog toekomstig margerisico."
        ),
        "kpis_json": json.dumps(kpis, default=str),
        "alerts_json": json.dumps([], default=str),
        "insights_json": json.dumps([
            {"sectie": "Marge", "tekst": f"Gem. netto marge {avg_net:.1f}% — trend monitoren."},
            {"sectie": "Procurement", "tekst": f"{len(high_fmr)} SKU's tonen hoog toekomstig margerisico."},
        ], default=str),
        "recommendations_json": json.dumps([], default=str),
    }


def upsert_report(db: Session, data: Dict[str, Any]) -> FactManagementReport:
    existing = (
        db.query(FactManagementReport)
        .filter(
            FactManagementReport.report_date == data["report_date"],
            FactManagementReport.report_type == data["report_type"],
        )
        .first()
    )
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    obj = FactManagementReport(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def run_reporting_engine(db: Session, report_date: date | None = None) -> int:
    d = report_date or date.today()
    daily = generate_daily_report(db, d)
    weekly = generate_weekly_report(db, d)
    monthly = generate_monthly_report(db, d)
    for data in (daily, weekly, monthly):
        upsert_report(db, data)
    return 3
