"""
Commercial Command Center — /api/command-center/* (§27, §50)

Eén managementdashboard met TODAY / THIS WEEK / FINANCIAL / AI-secties en de
§50-blokken (COMMERCIAL, COMPETITION, PRICING, CUSTOMERS, OPERATIONS, AI,
PLATFORM, BUSINESSCASE). Elke KPI kan doordrillen:
management → category → brand → SKU (via /drilldown).

Alle tenant-gebonden data is shop-gescoped: expliciet via ?shop_id=, anders
valt de scope terug op de default shop (semantic_layer._shop_scope).
Tabellen zonder eigen shop_id (bijv. procurement, monitoring, huismerk)
worden gescoped via een join op DimProduct.sku_id binnen dezelfde shop.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth import get_current_user
from semantic_layer import _shop_scope
import models

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/command-center", tags=["command-center"])


def _f(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


@router.get("/summary")
def command_center_summary(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Any:
    logger.info("command-center API started: /summary user_id=%s", current_user.id)
    sid = _shop_scope(db, shop_id)
    today = date.today()
    week_ago = today - timedelta(days=7)
    prev_week = today - timedelta(days=14)

    Sig = models.IntelligenceSignal
    Opp = models.Opportunity
    Rec = models.FactPricingRecommendationDaily
    Sales = models.FactSalesDaily
    P = models.DimProduct

    # Subquery van SKU's binnen deze shop, voor tabellen zonder eigen shop_id.
    shop_skus = db.query(P.sku_id).filter(P.shop_id == sid).scalar_subquery()

    def sig_count(**filters):
        q = db.query(Sig).filter(Sig.status == "active", Sig.shop_id == sid)
        for k, v in filters.items():
            col = getattr(Sig, k)
            q = q.filter(col.in_(v) if isinstance(v, (list, tuple)) else col == v)
        return q.count()

    # ── TODAY ────────────────────────────────────────────────────────────
    opportunities_open = db.query(Opp).filter(
        Opp.status == "open", Opp.shop_id == sid).count()
    risks = sig_count(severity=["high", "critical"])
    competitor_changes_today = db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.shop_id == sid,
        models.FactCompetitorPriceDaily.date >= today - timedelta(days=1)).count()
    margin_issues = db.query(Sig).filter(
        Sig.status == "active", Sig.shop_id == sid,
        Sig.signal_type.ilike("%margin%")).count()
    supplier_warnings = db.query(models.FactProcurementForecastDaily).filter(
        models.FactProcurementForecastDaily.sku_id.in_(shop_skus),
        models.FactProcurementForecastDaily.date >= week_ago,
        models.FactProcurementForecastDaily.procurement_opportunity_score >= 70).count()
    traffic_changes = db.query(Sig).filter(
        Sig.status == "active", Sig.shop_id == sid, Sig.engine.ilike("%traffic%")).count()
    alerts_open = db.query(models.FactMonitoringAlert).filter(
        models.FactMonitoringAlert.own_sku_id.in_(shop_skus),
        models.FactMonitoringAlert.resolved.is_(False)).count()

    # ── THIS WEEK ────────────────────────────────────────────────────────
    best_opps = (db.query(Opp).filter(Opp.status == "open", Opp.shop_id == sid)
                 .order_by(Opp.priority_score.desc()).limit(5).all())
    pricing_actions = db.query(Rec).filter(
        Rec.shop_id == sid, Rec.approval_status == "pending").count()
    promo_opps = db.query(Opp).filter(
        Opp.status == "open", Opp.shop_id == sid,
        Opp.opportunity_type.ilike("%promo%")).count()
    huismerk_opps = db.query(models.FactPrivateLabelIntelligence).filter(
        models.FactPrivateLabelIntelligence.sku_id.in_(shop_skus),
        models.FactPrivateLabelIntelligence.run_date >= week_ago,
        models.FactPrivateLabelIntelligence.strategic_priority == "hoog").count()
    customer_risks = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.shop_id == sid,
        models.CustomerValueScore.churn_risk >= 0.7).count()

    # ── FINANCIAL ────────────────────────────────────────────────────────
    def sales_window(start, end):
        row = (db.query(func.sum(Sales.revenue), func.sum(Sales.margin))
               .filter(Sales.shop_id == sid, Sales.date >= start, Sales.date < end).first())
        return _f(row[0]), _f(row[1])

    rev_7d, margin_7d = sales_window(week_ago, today + timedelta(days=1))
    rev_prev, margin_prev = sales_window(prev_week, week_ago)
    margin_change_pct = round((margin_7d - margin_prev) / margin_prev * 100, 1) if margin_prev else None
    FC = models.FactForecastDaily
    latest_fc = db.query(func.max(FC.run_date)).filter(FC.shop_id == sid).scalar()
    forecast_rev = _f(db.query(func.sum(FC.forecast_value)).filter(
        FC.shop_id == sid,
        FC.run_date == latest_fc,
        FC.forecast_type == "revenue",
        FC.horizon_days == 30).scalar()) if latest_fc else 0.0

    # ── AI ───────────────────────────────────────────────────────────────
    total_recs = db.query(Rec).filter(Rec.shop_id == sid).count()
    pending_approvals = pricing_actions \
        + db.query(models.Decision).filter(
            models.Decision.shop_id == sid,
            models.Decision.status.in_(["proposed", "in_review"])).count()
    avg_conf = _f(db.query(func.avg(Rec.confidence_score)).filter(Rec.shop_id == sid).scalar())

    # ── §50-blokken ──────────────────────────────────────────────────────
    # DimCompetitor is platform-breed (geen shop_id); tel concurrenten met
    # prijswaarnemingen binnen deze shop.
    main_competitors = db.query(
        func.count(func.distinct(models.FactCompetitorPriceDaily.competitor_name))).filter(
        models.FactCompetitorPriceDaily.shop_id == sid).scalar() or 0
    threats = db.query(Sig).filter(
        Sig.status == "active", Sig.shop_id == sid, Sig.engine.ilike("%compet%"),
        Sig.severity.in_(["high", "critical"])).count()
    margin_opps_eur = _f(db.query(func.sum(Rec.expected_margin_uplift)).filter(
        Rec.shop_id == sid, Rec.approval_status == "pending").scalar())
    switching = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.shop_id == sid).count()

    total_skus = db.query(P).filter(P.shop_id == sid).count()
    skus_with_cost = db.query(P).filter(
        P.shop_id == sid, P.cost_price.isnot(None)).count()
    dq_score = round(skus_with_cost / total_skus, 2) if total_skus else 1.0
    # Platform-brede indicatoren (geen tenantdata): open DQ-issues & connectors.
    dq_open = db.query(models.DataQualityIssue).filter(models.DataQualityIssue.status != "resolved").count()
    connectors_ok = db.query(models.ConnectorConfig).filter(
        models.ConnectorConfig.last_test_status == "ok").count()
    connectors_total = db.query(models.ConnectorConfig).count()

    cost_30d = _f(db.query(func.sum(models.CostUsageRecord.cost_eur)).filter(
        models.CostUsageRecord.shop_id == sid,
        models.CostUsageRecord.occurred_at >= datetime.utcnow() - timedelta(days=30)).scalar())
    measured_value = _f(db.query(func.sum(models.BusinessValueMeasurement.value)).filter(
        models.BusinessValueMeasurement.shop_id == sid,
        models.BusinessValueMeasurement.unit.ilike("%eur%"),
        models.BusinessValueMeasurement.value_label.in_(["REALIZED", "MEASURED"])).scalar())
    roi_pct = round((measured_value - cost_30d) / cost_30d * 100, 1) if cost_30d else None

    stock_risks = db.query(P).filter(
        P.shop_id == sid,
        P.is_active.is_(True),
        P.stock_quantity <= 0).count()

    logger.info("command-center API completed: /summary user_id=%s shop_id=%s", current_user.id, sid)
    return {
        "shop_id": sid,
        "vandaag": {
            "opportunities": opportunities_open,
            "risks": risks,
            "competitor_changes": competitor_changes_today,
            "margin_issues": margin_issues,
            "supplier_warnings": supplier_warnings,
            "traffic_changes": traffic_changes,
            "open_alerts": alerts_open,
        },
        "deze_week": {
            "best_opportunities": [{
                "id": o.id, "titel": o.title_nl, "type": o.opportunity_type,
                "entity_id": o.entity_id, "entity_name": o.entity_name,
                "expected_value_eur": _f(o.expected_value_eur),
                "priority_score": _f(o.priority_score), "urgency": o.urgency,
            } for o in best_opps],
            "pricing_actions": pricing_actions,
            "promotion_opportunities": promo_opps,
            "huismerk_opportunities": huismerk_opps,
            "customer_risks": customer_risks,
        },
        "financieel": {
            "sales_7d": rev_7d,
            "margin_7d": margin_7d,
            "margin_change_pct": margin_change_pct,
            "forecast_revenue": forecast_rev,
        },
        "ai": {
            "recommendations": total_recs,
            "approvals_pending": pending_approvals,
            "avg_confidence": avg_conf,
        },
        "blokken": {
            "commercial": {"sales": rev_7d, "margin": margin_7d,
                           "opportunities": opportunities_open, "risks": risks},
            "competition": {"main_competitors": int(main_competitors),
                            "changes": competitor_changes_today, "threats": threats},
            "pricing": {"recommended_actions": pricing_actions,
                        "margin_opportunities_eur": margin_opps_eur},
            "customers": {"value_scores": switching, "churn_risks": customer_risks,
                          "switching": switching},
            "operations": {"supplier_risks": supplier_warnings, "stock_risks": stock_risks},
            "ai": {"recommendations": total_recs, "confidence": avg_conf,
                   "pending_approvals": pending_approvals},
            "platform": {"data_quality_score": dq_score, "open_dq_issues": dq_open,
                         "integrations_ok": connectors_ok, "integrations_total": connectors_total,
                         "security_status": "RBAC + JWT actief"},
            "businesscase": {"cost_30d_eur": cost_30d,
                             "cost_per_shop_eur": cost_30d,
                             "measured_value_eur": measured_value,
                             "roi_pct": roi_pct},
        },
        "peildatum": str(today),
    }


VALID_KPIS = ("sales", "margin", "recommendations", "opportunities", "risks")


@router.get("/drilldown")
def command_center_drilldown(
    kpi: str = Query(..., description="sales / margin / recommendations / opportunities / risks"),
    level: str = Query("category", description="category / brand / sku"),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Any:
    """KPI-drill-down: management → category → brand → SKU (§27). Shop-gescoped."""
    if kpi not in VALID_KPIS:
        raise HTTPException(400, f"Onbekende kpi; kies uit {VALID_KPIS}")
    if level not in ("category", "brand", "sku"):
        raise HTTPException(400, "level moet category, brand of sku zijn")

    sid = _shop_scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    P = models.DimProduct

    if level == "category":
        group_col = P.category
    elif level == "brand":
        group_col = P.brand
    else:
        group_col = P.sku_id

    def apply_scope(q):
        q = q.filter(P.shop_id == sid)
        if category:
            q = q.filter(P.category == category)
        if brand:
            q = q.filter(P.brand == brand)
        return q

    rows: list[dict] = []

    if kpi in ("sales", "margin"):
        S = models.FactSalesDaily
        metric = func.sum(S.revenue) if kpi == "sales" else func.sum(S.margin)
        q = (db.query(group_col.label("key"),
                      func.coalesce(metric, 0).label("value"),
                      func.sum(S.units_sold).label("units"),
                      func.count(func.distinct(S.sku_id)).label("skus"))
             .join(P, S.sku_id == P.sku_id)
             .filter(S.shop_id == sid, S.date >= since))
        q = apply_scope(q).group_by(group_col).order_by(func.coalesce(metric, 0).desc()).limit(limit)
        rows = [{"key": r.key or "Onbekend", "value": _f(r.value),
                 "units": int(r.units or 0), "sku_count": r.skus} for r in q.all()]
        unit = "EUR"

    elif kpi == "recommendations":
        R = models.FactPricingRecommendationDaily
        q = (db.query(group_col.label("key"),
                      func.count(R.id).label("value"),
                      func.coalesce(func.sum(R.expected_margin_uplift), 0).label("uplift"),
                      func.avg(R.confidence_score).label("conf"))
             .join(P, R.sku_id == P.sku_id)
             .filter(R.shop_id == sid))
        q = apply_scope(q).group_by(group_col).order_by(func.count(R.id).desc()).limit(limit)
        rows = [{"key": r.key or "Onbekend", "value": int(r.value or 0),
                 "expected_margin_uplift": _f(r.uplift),
                 "avg_confidence": _f(r.conf)} for r in q.all()]
        unit = "aantal"

    elif kpi == "opportunities":
        O = models.Opportunity
        q = (db.query(group_col.label("key"),
                      func.count(O.id).label("value"),
                      func.coalesce(func.sum(O.expected_value_eur), 0).label("val_eur"))
             .join(P, O.entity_id == P.sku_id)
             .filter(O.shop_id == sid, O.status == "open"))
        q = apply_scope(q).group_by(group_col).order_by(func.count(O.id).desc()).limit(limit)
        rows = [{"key": r.key or "Onbekend", "value": int(r.value or 0),
                 "expected_value_eur": _f(r.val_eur)} for r in q.all()]
        unit = "aantal"

    else:  # risks
        S = models.IntelligenceSignal
        q = (db.query(group_col.label("key"),
                      func.count(S.id).label("value"))
             .join(P, S.entity_id == P.sku_id)
             .filter(S.shop_id == sid, S.status == "active",
                     S.severity.in_(["high", "critical"])))
        q = apply_scope(q).group_by(group_col).order_by(func.count(S.id).desc()).limit(limit)
        rows = [{"key": r.key or "Onbekend", "value": int(r.value or 0)} for r in q.all()]
        unit = "aantal"

    # SKU-niveau: verrijk met productnaam (binnen dezelfde shop)
    if level == "sku" and rows:
        names = dict(db.query(P.sku_id, P.product_name).filter(
            P.shop_id == sid,
            P.sku_id.in_([r["key"] for r in rows])).all())
        for r in rows:
            r["product_name"] = names.get(r["key"])

    return {
        "kpi": kpi,
        "level": level,
        "shop_id": sid,
        "filter": {"category": category, "brand": brand},
        "periode_dagen": days,
        "unit": unit,
        "rows": rows,
    }
