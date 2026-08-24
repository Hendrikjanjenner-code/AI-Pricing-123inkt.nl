"""
Competitor Monitoring routes — /api/monitoring/...
Monitoring van concurrentieprijzen, voorraad en alerts.
"""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from database import get_db
from auth import get_current_user
from models import FactMonitoringAlert, DimCompetitor, DimProduct, User
from datetime import date, datetime, timedelta

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/alerts")
def get_monitoring_alerts(
    sku_id: str = Query(None),
    alert_type: str = Query(None),
    severity: str = Query(None),
    resolved: bool = Query(None),
    dagen: int = Query(30),
    hierarchy_node_ids: str = Query(None),
    brands: str = Query(None),
    statuses: str = Query(None),
    sku_query: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal monitoring-alerts op, gefilterd en gesorteerd op datum."""
    vanaf = date.today() - timedelta(days=dagen)
    q = db.query(FactMonitoringAlert).filter(FactMonitoringAlert.date >= vanaf)

    # Globale filtercontext (hiërarchie + merk): beperk tot alerts op de
    # gefilterde SKU-set (own_sku_id). Lege selectie ≠ geen filter.
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    if sku_q is not None:
        q = q.filter(FactMonitoringAlert.own_sku_id.in_(sku_q.scalar_subquery()))

    if sku_id:
        q = q.filter(FactMonitoringAlert.own_sku_id == sku_id)
    if alert_type:
        q = q.filter(FactMonitoringAlert.alert_type == alert_type)
    if severity:
        q = q.filter(FactMonitoringAlert.severity == severity)
    if resolved is not None:
        q = q.filter(FactMonitoringAlert.resolved == resolved)

    totaal = q.count()
    alerts = q.order_by(desc(FactMonitoringAlert.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    concurrenten = {c.competitor_id: c.competitor_name for c in db.query(DimCompetitor).all()}
    producten = {p.sku_id: p.product_name for p in db.query(DimProduct).all()}

    # Samenvatting per type (respecteert de globale filtercontext)
    type_counts = {}
    sum_q = db.query(FactMonitoringAlert).filter(
        FactMonitoringAlert.date >= vanaf, FactMonitoringAlert.resolved == False)
    if sku_q is not None:
        sum_q = sum_q.filter(FactMonitoringAlert.own_sku_id.in_(sku_q.scalar_subquery()))
    for a in sum_q.all():
        type_counts[a.alert_type] = type_counts.get(a.alert_type, 0) + 1

    return {
        "alerts": [
            {
                "alert_id": a.alert_id,
                "date": str(a.date),
                "own_sku_id": a.own_sku_id,
                "product_naam": producten.get(a.own_sku_id, a.own_sku_id) if a.own_sku_id else None,
                "concurrent": concurrenten.get(a.competitor_id, str(a.competitor_id)) if a.competitor_id else None,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "resolved": a.resolved,
                "created_at": str(a.created_at),
            }
            for a in alerts
        ],
        "totaal": totaal,
        "page": page,
        "page_size": page_size,
        "samenvatting": type_counts,
    }


@router.post("/resolve/{alert_id}")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Markeer een alert als opgelost."""
    alert = db.query(FactMonitoringAlert).filter(FactMonitoringAlert.alert_id == alert_id).first()
    if not alert:
        return {"fout": "Alert niet gevonden"}
    alert.resolved = True
    db.commit()
    return {"status": "opgelost", "alert_id": alert_id}


@router.post("/run")
def run_monitoring(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Voer monitoring-run uit: vergelijk huidige met vorige concurrent-data
    en genereer alerts.
    """
    from services.monitoring_engine import generate_monitoring_alerts, save_alerts
    from models import FactCompetitorOfferDaily, CompetitorInfluenceScore

    vandaag = date.today()
    gisteren = vandaag - timedelta(days=1)

    # Haal huidige en vorige aanbiedingen op
    huidige = db.query(FactCompetitorOfferDaily).filter(
        FactCompetitorOfferDaily.date == vandaag
    ).all()
    vorige = db.query(FactCompetitorOfferDaily).filter(
        FactCompetitorOfferDaily.date == gisteren
    ).all()

    # CSRS scores
    csrs_map = {
        s.competitor_name: s.csrs_score
        for s in db.query(CompetitorInfluenceScore).all()
    }

    # Groepeer per SKU
    from collections import defaultdict
    huidig_per_sku: dict = defaultdict(list)
    vorig_per_sku: dict = defaultdict(list)

    for o in huidige:
        huidig_per_sku[o.own_sku_id].append({
            "competitor_id": o.competitor_id,
            "price": float(o.competitor_price_inc_vat) if o.competitor_price_inc_vat else None,
            "in_stock": o.in_stock,
            "delivery_days": o.delivery_days,
            "product_url": o.product_url,
        })
    for o in vorige:
        vorig_per_sku[o.own_sku_id].append({
            "competitor_id": o.competitor_id,
            "price": float(o.competitor_price_inc_vat) if o.competitor_price_inc_vat else None,
            "in_stock": o.in_stock,
            "delivery_days": o.delivery_days,
            "product_url": o.product_url,
        })

    alle_alerts = []
    for sku_id in set(list(huidig_per_sku.keys()) + list(vorig_per_sku.keys())):
        alerts = generate_monitoring_alerts(
            sku_id=sku_id,
            current_offers=huidig_per_sku.get(sku_id, []),
            previous_offers=vorig_per_sku.get(sku_id, []),
            csrs_scores={},
        )
        alle_alerts.extend(alerts)

    save_alerts(db, alle_alerts)
    return {"status": "uitgevoerd", "alerts_gegenereerd": len(alle_alerts)}


@router.get("/sku/{sku_id}")
def get_sku_monitoring(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Monitoring-overzicht voor één SKU: alerts + prijstrend."""
    from services.monitoring_engine import calculate_price_trend
    from models import FactCompetitorOfferDaily

    product = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not product:
        return {"fout": "SKU niet gevonden"}

    # Alerts
    alerts = (
        db.query(FactMonitoringAlert)
        .filter(FactMonitoringAlert.own_sku_id == sku_id)
        .order_by(desc(FactMonitoringAlert.created_at))
        .limit(20)
        .all()
    )

    # Prijshistorie per concurrent
    aanbiedingen = (
        db.query(FactCompetitorOfferDaily)
        .filter(FactCompetitorOfferDaily.own_sku_id == sku_id)
        .order_by(FactCompetitorOfferDaily.date)
        .all()
    )

    concurrenten = {c.competitor_id: c.competitor_name for c in db.query(DimCompetitor).all()}

    # Groepeer prijzen per concurrent
    prijs_per_concurrent: dict = {}
    for a in aanbiedingen:
        naam = concurrenten.get(a.competitor_id, str(a.competitor_id))
        if naam not in prijs_per_concurrent:
            prijs_per_concurrent[naam] = []
        if a.competitor_price_inc_vat:
            prijs_per_concurrent[naam].append(float(a.competitor_price_inc_vat))

    trends = {
        naam: calculate_price_trend(prijzen)
        for naam, prijzen in prijs_per_concurrent.items()
    }

    return {
        "sku_id": sku_id,
        "product_naam": product.product_name,
        "alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "date": str(a.date),
                "resolved": a.resolved,
            }
            for a in alerts
        ],
        "prijstrends": trends,
    }
