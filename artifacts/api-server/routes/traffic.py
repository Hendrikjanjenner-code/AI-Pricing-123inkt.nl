"""
Traffic & Demand Intelligence — API routes.

Endpoints:
  GET  /api/traffic                   — dashboard KPI's + signalen
  GET  /api/traffic/sku/{sku_id}      — SKU traffic detail
  GET  /api/traffic/categorie/{cat}   — categorie traffic
  POST /api/traffic/berekenen         — traffic engine uitvoeren
  POST /api/traffic/import            — CSV import stub

  GET  /api/conversie/signalen        — conversie alerts
"""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import auth as auth_utils
import models
import metrics as metrics_lib
from engine.traffic_engine import run_traffic_engine
from engine.conversion_monitoring import (
    SIGNAL_LABELS_NL, SIGNAL_PRIORITY, SIGNAL_KLEUR, ADVIES_PER_SIGNAAL,
    MOGELIJKE_OORZAKEN, classify_conversion_cause, get_conversion_cause_nl,
)
from engine.traffic_bcg_overlay import apply_traffic_to_bcg
from engine.traffic_promotion_overlay import apply_traffic_to_promotion_advice
from engine.traffic_pricing_overlay import apply_traffic_to_pricing_advice

router = APIRouter(tags=["traffic"])
conversie_router = APIRouter(tags=["conversie"])


# ─── Hulpfuncties ─────────────────────────────────────────────────────────────

def _latest_intel(db: Session, entity_type: str = "SKU") -> list[models.FactTrafficIntelligenceDaily]:
    today = date.today()
    rows = db.query(models.FactTrafficIntelligenceDaily).filter_by(
        date=today, entity_type=entity_type
    ).all()
    if not rows:
        latest = db.query(models.FactTrafficIntelligenceDaily.date).filter(
            models.FactTrafficIntelligenceDaily.entity_type == entity_type
        ).order_by(models.FactTrafficIntelligenceDaily.date.desc()).first()
        if latest:
            rows = db.query(models.FactTrafficIntelligenceDaily).filter_by(
                date=latest[0], entity_type=entity_type
            ).all()
    return rows


def _traffic_today(db: Session, entity_id: str, entity_type: str = "SKU") -> list[models.FactTrafficDaily]:
    today = date.today()
    cutoff = today - timedelta(days=30)
    return db.query(models.FactTrafficDaily).filter(
        models.FactTrafficDaily.entity_id == entity_id,
        models.FactTrafficDaily.entity_type == entity_type,
        models.FactTrafficDaily.date >= cutoff,
    ).order_by(models.FactTrafficDaily.date).all()


def _intel_record(rows: list, entity_id: str) -> models.FactTrafficIntelligenceDaily | None:
    return next((r for r in rows if r.entity_id == entity_id), None)


def _signal_dict(r: models.FactTrafficIntelligenceDaily) -> dict:
    return {
        "entity_id":    r.entity_id,
        "entity_naam":  r.entity_name,
        "signaal":      r.reason_code,
        "signaal_nl":   SIGNAL_LABELS_NL.get(r.reason_code or "", r.reason_code or ""),
        "prioriteit":   SIGNAL_PRIORITY.get(r.reason_code or "", "laag"),
        "kleur":        SIGNAL_KLEUR.get(r.reason_code or "", "#94a3b8"),
        "advies":       ADVIES_PER_SIGNAAL.get(r.reason_code or "", ""),
        "uitleg":       r.explanation_nl,
        "crs":          round(r.conversion_risk_score or 0, 3),
        "tos":          round(r.traffic_opportunity_score or 0, 3),
        "dss":          round(r.demand_signal_score or 0, 3),
    }


# ─── GET /api/traffic ─────────────────────────────────────────────────────────

@router.get("/api/traffic")
def get_traffic_dashboard(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    sku_rows = _latest_intel(db, "SKU")

    if not sku_rows:
        return {
            "totale_sessies": 0,
            "conversieratio": 0,
            "omzet_per_bezoeker": 0,
            "marge_per_bezoeker": 0,
            "sku_met_conversiedaling": 0,
            "sku_met_hoge_search_gap": 0,
            "traffic_opportunities": 0,
            "signalen": [],
            "sku_overzicht": [],
            "search_gap_top": [],
        }

    today = date.today()
    cutoff30 = today - timedelta(days=30)
    all_traffic = db.query(models.FactTrafficDaily).filter(
        models.FactTrafficDaily.date >= cutoff30,
        models.FactTrafficDaily.entity_type == "SKU",
    ).all()

    totale_sessies = sum(r.sessions or 0 for r in all_traffic)
    totale_orders = sum(r.orders or 0 for r in all_traffic)
    totale_rev = sum(float(r.revenue or 0) for r in all_traffic)
    totale_margin = sum(float(r.margin or 0) for r in all_traffic)

    conv_rate = round(totale_orders / totale_sessies, 4) if totale_sessies > 0 else 0
    rpv = round(totale_rev / totale_sessies, 4) if totale_sessies > 0 else 0
    mpv = round(totale_margin / totale_sessies, 4) if totale_sessies > 0 else 0

    conv_dalend = sum(1 for r in sku_rows if (r.conversion_risk_score or 0) >= 0.60)
    hoge_gap = sum(1 for r in sku_rows if (r.search_gap_score or 0) >= 0.55)
    opportunities = sum(1 for r in sku_rows if (r.traffic_opportunity_score or 0) >= 0.55)

    # Signalen (gesorteerd op CRS + TOS)
    signaal_rijen = [r for r in sku_rows if r.reason_code and r.reason_code != "NO_SIGNAL"]
    signaal_rijen.sort(key=lambda r: (r.conversion_risk_score or 0) + (r.traffic_opportunity_score or 0), reverse=True)
    signalen = [_signal_dict(r) for r in signaal_rijen[:10]]

    # SKU overzicht
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    sku_overzicht = []
    for r in sorted(sku_rows, key=lambda x: (x.conversion_risk_score or 0) + (x.traffic_opportunity_score or 0), reverse=True):
        p = products.get(r.entity_id)
        sku_overzicht.append({
            "sku_id":    r.entity_id,
            "naam":      r.entity_name,
            "categorie": p.category if p else "",
            "dss":  round(r.demand_signal_score or 0, 3),
            "chs":  round(r.conversion_health_score or 0, 3),
            "tos":  round(r.traffic_opportunity_score or 0, 3),
            "crs":  round(r.conversion_risk_score or 0, 3),
            "sgs":  round(r.search_gap_score or 0, 3),
            "traffic_growth":    round(r.traffic_growth or 0, 3),
            "conversion_trend":  round(r.conversion_trend or 0, 3),
            "signaal":    r.reason_code,
            "signaal_nl": SIGNAL_LABELS_NL.get(r.reason_code or "", ""),
            "kleur":      SIGNAL_KLEUR.get(r.reason_code or "", "#94a3b8"),
        })

    # Search gap top 10
    search_gap_top = sorted(sku_overzicht, key=lambda x: x["sgs"], reverse=True)[:10]

    return {
        "totale_sessies":            totale_sessies,
        "conversieratio":            conv_rate,
        "omzet_per_bezoeker":        rpv,
        "marge_per_bezoeker":        mpv,
        "sku_met_conversiedaling":   conv_dalend,
        "sku_met_hoge_search_gap":   hoge_gap,
        "traffic_opportunities":     opportunities,
        "totaal_skus":               len(sku_rows),
        "run_date":                  str(sku_rows[0].date),
        "signalen":                  signalen,
        "sku_overzicht":             sku_overzicht,
        "search_gap_top":            search_gap_top,
    }


# ─── GET /api/traffic/sku/{sku_id} ───────────────────────────────────────────

@router.get("/api/traffic/sku/{sku_id}")
def get_traffic_sku_detail(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    sku_rows = _latest_intel(db, "SKU")
    intel = _intel_record(sku_rows, sku_id)

    product = db.query(models.DimProduct).filter_by(sku_id=sku_id).first()
    if not product:
        raise HTTPException(404, f"SKU {sku_id} niet gevonden")

    traffic_rows = _traffic_today(db, sku_id, "SKU")
    search_rows = db.query(models.FactSearchDemandDaily).filter_by(
        entity_id=sku_id
    ).order_by(models.FactSearchDemandDaily.search_volume.desc()).all()

    pcis = db.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).order_by(
        models.SkuCompetitionScore.run_date.desc()
    ).first()
    elast = db.query(models.SkuElasticity).filter_by(sku_id=sku_id).order_by(
        models.SkuElasticity.run_date.desc()
    ).first()
    bcg_record = db.query(models.FactBcgClassificationDaily).filter_by(
        entity_id=sku_id, entity_type="SKU"
    ).order_by(models.FactBcgClassificationDaily.date.desc()).first()

    # Aggregeer traffic
    tot_sess = sum(r.sessions or 0 for r in traffic_rows)
    tot_ord = sum(r.orders or 0 for r in traffic_rows)
    tot_pv = sum(r.pageviews or 0 for r in traffic_rows)
    tot_atc = sum(r.add_to_cart or 0 for r in traffic_rows)
    tot_rev = sum(float(r.revenue or 0) for r in traffic_rows)
    tot_margin = sum(float(r.margin or 0) for r in traffic_rows)
    avg_bounce = sum(r.bounce_rate or 0 for r in traffic_rows) / len(traffic_rows) if traffic_rows else 0.55

    cr = round(tot_ord / tot_sess, 4) if tot_sess > 0 else 0
    atc_r = round(tot_atc / tot_sess, 4) if tot_sess > 0 else 0
    rpv = round(tot_rev / tot_sess, 4) if tot_sess > 0 else 0
    mpv = round(tot_margin / tot_sess, 4) if tot_sess > 0 else 0

    # Trend data
    trend = [
        {
            "datum": str(r.date),
            "sessies": r.sessions or 0,
            "orders": r.orders or 0,
            "conversie": round((r.orders or 0) / max(r.sessions or 1, 1), 4),
            "pageviews": r.pageviews or 0,
            "revenue": float(r.revenue or 0),
        }
        for r in traffic_rows[-14:]
    ]

    # BCG overlay
    bcg_overlay = apply_traffic_to_bcg(bcg_record, intel) if bcg_record and intel else {}

    # Promotieadvies
    cps = pcis.price_index if pcis and pcis.price_index else 1.0
    promo_advies = apply_traffic_to_promotion_advice(
        dss=float(intel.demand_signal_score or 0) if intel else 0,
        chs=float(intel.conversion_health_score or 0) if intel else 0,
        tos=float(intel.traffic_opportunity_score or 0) if intel else 0,
        crs=float(intel.conversion_risk_score or 0) if intel else 0,
        sgs=float(intel.search_gap_score or 0) if intel else 0,
        sessions=tot_sess,
        margin_pct=float(metrics_lib.margin_ratio(product.current_price, product.cost_price)),
        stock_quantity=product.stock_quantity or 0,
        price_index=float(cps),
        reason_code=intel.reason_code or "NO_SIGNAL" if intel else "NO_SIGNAL",
    ) if intel else {}

    # Prijsadvies
    cis_rows = db.query(models.CompetitorInfluenceScore).filter_by(sku_id=sku_id).all()
    avg_csrs = sum(float(r.csrs_score or 0) for r in cis_rows) / len(cis_rows) if cis_rows else 0.5

    pricing_advies = apply_traffic_to_pricing_advice(
        dss=float(intel.demand_signal_score or 0) if intel else 0,
        chs=float(intel.conversion_health_score or 0) if intel else 0,
        crs=float(intel.conversion_risk_score or 0) if intel else 0,
        traffic_growth=float(intel.traffic_growth or 0) if intel else 0,
        conversion_trend=float(intel.conversion_trend or 0) if intel else 0,
        sessions=tot_sess,
        price_index=float(cps),
        pcis_score=float(pcis.pcis_score or 0.5) if pcis else 0.5,
        own_elasticity=float(elast.own_price_elasticity or -1.5) if elast else -1.5,
        csrs_score=avg_csrs,
    ) if intel else {}

    return {
        "sku_id": sku_id,
        "naam": product.product_name,
        "categorie": product.category,
        "is_private_label": bool(product.is_private_label),
        "traffic": {
            "pageviews": tot_pv,
            "sessies": tot_sess,
            "orders": tot_ord,
            "conversieratio": cr,
            "add_to_cart_rate": atc_r,
            "omzet_per_bezoeker": rpv,
            "marge_per_bezoeker": mpv,
            "bounce_rate": round(avg_bounce, 3),
        },
        "scores": {
            "dss": round(float(intel.demand_signal_score or 0), 3) if intel else 0,
            "chs": round(float(intel.conversion_health_score or 0), 3) if intel else 0,
            "tos": round(float(intel.traffic_opportunity_score or 0), 3) if intel else 0,
            "crs": round(float(intel.conversion_risk_score or 0), 3) if intel else 0,
            "sgs": round(float(intel.search_gap_score or 0), 3) if intel else 0,
            "traffic_growth": round(float(intel.traffic_growth or 0), 3) if intel else 0,
            "conversion_trend": round(float(intel.conversion_trend or 0), 3) if intel else 0,
        },
        "signaal": {
            "code": intel.reason_code if intel else None,
            "label": SIGNAL_LABELS_NL.get(intel.reason_code or "", "") if intel else "",
            "uitleg": intel.explanation_nl if intel else "",
            "kleur": SIGNAL_KLEUR.get(intel.reason_code or "", "#94a3b8") if intel else "#94a3b8",
        },
        "trend": trend,
        "search_demand": [
            {
                "keyword": r.keyword,
                "type": r.keyword_type,
                "volume": r.search_volume,
                "impressies": r.impressions,
                "klikken": r.clicks,
                "ctr": round(r.ctr or 0, 4),
                "positie": round(r.average_position or 10, 1),
                "trend": round(r.trend_index or 0, 3),
                "concurrentie": round(r.competition_level or 0, 3),
                "cpc": float(r.cpc_estimate or 0),
                "bron": r.source,
            }
            for r in search_rows[:10]
        ],
        "concurrentie": {
            "pcis_score": round(float(pcis.pcis_score or 0), 3) if pcis else None,
            "price_index": round(float(pcis.price_index or 1), 3) if pcis and pcis.price_index else None,
            "competition_class": pcis.competition_class if pcis else None,
        },
        "elasticiteit": {
            "own": round(elast.own_price_elasticity or 0, 3) if elast else None,
        },
        "bcg": {
            "hybrid_class": bcg_record.hybrid_bcg_class if bcg_record else None,
            "pricing_strategy": bcg_record.pricing_strategy if bcg_record else None,
            "overlay": bcg_overlay,
        },
        "promotie_advies": promo_advies,
        "pricing_advies": pricing_advies,
    }


# ─── GET /api/traffic/categorie/{category} ────────────────────────────────────

@router.get("/api/traffic/categorie/{category}")
def get_traffic_categorie(
    category: str,
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    today = date.today()
    cutoff30 = today - timedelta(days=30)

    products = db.query(models.DimProduct).filter_by(category=category).all()
    if not products:
        raise HTTPException(404, f"Categorie '{category}' niet gevonden")

    sku_ids = [p.sku_id for p in products]
    traffic_rows = db.query(models.FactTrafficDaily).filter(
        models.FactTrafficDaily.entity_id.in_(sku_ids),
        models.FactTrafficDaily.date >= cutoff30,
    ).all()

    sku_rows = _latest_intel(db, "SKU")
    cat_intel = [r for r in sku_rows if r.entity_id in sku_ids]

    tot_sess = sum(r.sessions or 0 for r in traffic_rows)
    tot_orders = sum(r.orders or 0 for r in traffic_rows)
    tot_pv = sum(r.pageviews or 0 for r in traffic_rows)
    tot_rev = sum(float(r.revenue or 0) for r in traffic_rows)
    tot_margin = sum(float(r.margin or 0) for r in traffic_rows)
    avg_cr = round(tot_orders / tot_sess, 4) if tot_sess > 0 else 0

    avg_dss = sum(float(r.demand_signal_score or 0) for r in cat_intel) / len(cat_intel) if cat_intel else 0
    avg_chs = sum(float(r.conversion_health_score or 0) for r in cat_intel) / len(cat_intel) if cat_intel else 0
    avg_sgs = sum(float(r.search_gap_score or 0) for r in cat_intel) / len(cat_intel) if cat_intel else 0

    return {
        "categorie": category,
        "totaal_skus": len(products),
        "traffic": {
            "sessies": tot_sess,
            "pageviews": tot_pv,
            "orders": tot_orders,
            "conversieratio": avg_cr,
            "omzet": round(tot_rev, 2),
            "marge": round(tot_margin, 2),
        },
        "scores": {
            "dss": round(avg_dss, 3),
            "chs": round(avg_chs, 3),
            "sgs": round(avg_sgs, 3),
        },
        "sku_breakdown": [
            {
                "sku_id": r.entity_id,
                "naam": r.entity_name,
                "dss": round(r.demand_signal_score or 0, 3),
                "chs": round(r.conversion_health_score or 0, 3),
                "crs": round(r.conversion_risk_score or 0, 3),
                "sgs": round(r.search_gap_score or 0, 3),
                "signaal": r.reason_code,
                "signaal_nl": SIGNAL_LABELS_NL.get(r.reason_code or "", ""),
                "kleur": SIGNAL_KLEUR.get(r.reason_code or "", "#94a3b8"),
            }
            for r in cat_intel
        ],
    }


# ─── POST /api/traffic/berekenen ──────────────────────────────────────────────

@router.post("/api/traffic/berekenen")
def berekenen(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    processed, skipped = run_traffic_engine(db)
    return {"status": "voltooid", "verwerkt": processed, "overgeslagen": skipped, "datum": str(date.today())}


@router.post("/api/traffic/import")
def import_traffic(_=Depends(auth_utils.get_current_user)):
    return {"status": "stub", "message": "CSV-import nog niet geïmplementeerd. Gebruik de database direct."}


# ─── GET /api/conversie/signalen ─────────────────────────────────────────────

@conversie_router.get("/api/conversie/signalen")
def get_conversie_signalen(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    sku_rows = _latest_intel(db, "SKU")
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    pcis_map = {r.sku_id: r for r in db.query(models.SkuCompetitionScore).all()}
    inv_map = {r.sku_id: r.quantity_on_hand for r in db.query(models.FactInventoryDaily).filter_by(
        date=date.today()
    ).all()}
    cis_map: dict[str, list] = {}
    for r in db.query(models.CompetitorInfluenceScore).all():
        cis_map.setdefault(r.sku_id, []).append(r)

    signalen = []
    for r in sku_rows:
        p = products.get(r.entity_id)
        pcis = pcis_map.get(r.entity_id)
        cis_list = cis_map.get(r.entity_id, [])
        avg_csrs = sum(float(c.csrs_score or 0) for c in cis_list) / len(cis_list) if cis_list else 0.5
        stock = inv_map.get(r.entity_id, 0)

        price_index = float(pcis.price_index or 1.0) if pcis and pcis.price_index else 1.0
        oorzaak = ""
        if r.reason_code == "CONVERSION_DROP_DETECTED":
            oorzaak = classify_conversion_cause(
                price_index, avg_csrs, stock or 0,
                0.60, float(r.conversion_trend or 0)
            )

        signalen.append({
            "sku_id":          r.entity_id,
            "naam":            r.entity_name,
            "categorie":       p.category if p else "",
            "signaal":         r.reason_code,
            "signaal_nl":      SIGNAL_LABELS_NL.get(r.reason_code or "", ""),
            "prioriteit":      SIGNAL_PRIORITY.get(r.reason_code or "", "laag"),
            "kleur":           SIGNAL_KLEUR.get(r.reason_code or "", "#94a3b8"),
            "advies":          ADVIES_PER_SIGNAAL.get(r.reason_code or "", ""),
            "oorzaak":         get_conversion_cause_nl(oorzaak) if oorzaak else "",
            "crs":             round(r.conversion_risk_score or 0, 3),
            "tos":             round(r.traffic_opportunity_score or 0, 3),
            "dss":             round(r.demand_signal_score or 0, 3),
            "traffic_growth":  round(r.traffic_growth or 0, 3),
            "conv_trend":      round(r.conversion_trend or 0, 3),
            "price_index":     round(price_index, 3),
            "uitleg":          r.explanation_nl,
        })

    # Sorteer: hoge prioriteit eerst, dan CRS
    prio_order = {"hoog": 0, "gemiddeld": 1, "laag": 2}
    signalen.sort(key=lambda s: (prio_order.get(s["prioriteit"], 2), -s["crs"]))

    return {
        "signalen": signalen,
        "totaal": len(signalen),
        "hoge_prioriteit": sum(1 for s in signalen if s["prioriteit"] == "hoog"),
        "run_date": str(sku_rows[0].date) if sku_rows else str(date.today()),
    }
