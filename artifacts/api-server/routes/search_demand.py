"""
Search Demand Intelligence — API routes.

Endpoints:
  GET  /api/search-demand                    — samenvatting per SKU
  GET  /api/search-demand/sku/{sku_id}       — SKU keyword detail
  GET  /api/search-demand/categorie/{cat}    — categorie keyword analyse
  POST /api/search-demand/import             — CSV import stub
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import auth as auth_utils
import models
from engine.search_demand_engine import (
    calculate_external_demand_score,
    calculate_search_gap_score,
    calculate_own_visibility_score,
    calculate_keyword_opportunity_score,
    aggregate_sku_search_demand,
)

router = APIRouter(tags=["search-demand"])

KEYWORD_TYPE_NL = {
    "BRAND":    "Merknaam",
    "GENERIC":  "Generiek",
    "EAN":      "EAN/Barcode",
    "MPN":      "Artikelnummer",
    "CATEGORY": "Categorie",
}

ACTIE_PER_GAP: dict[str, str] = {
    "hoog":      "SEO/SEA investering aanbevolen",
    "gemiddeld": "Content optimalisatie overwegen",
    "laag":      "Geen urgente actie nodig",
}


def _gap_label(sgs: float) -> str:
    if sgs >= 0.60:
        return "hoog"
    if sgs >= 0.35:
        return "gemiddeld"
    return "laag"


# ─── GET /api/search-demand ───────────────────────────────────────────────────

@router.get("/api/search-demand")
def get_search_demand_overview(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    search_rows = db.query(models.FactSearchDemandDaily).all()
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    intel_rows = db.query(models.FactTrafficIntelligenceDaily).filter_by(
        entity_type="SKU"
    ).order_by(models.FactTrafficIntelligenceDaily.date.desc()).all()

    # Deduplicate: neem meest recente per SKU
    seen: set[str] = set()
    intel_map: dict[str, models.FactTrafficIntelligenceDaily] = {}
    for r in intel_rows:
        if r.entity_id not in seen:
            seen.add(r.entity_id)
            intel_map[r.entity_id] = r

    # Groepeer keywords per SKU
    sku_keywords: dict[str, list] = {}
    for r in search_rows:
        sku_keywords.setdefault(r.entity_id, []).append(r)

    items = []
    for sku_id, kws in sku_keywords.items():
        agg = aggregate_sku_search_demand(kws)
        p = products.get(sku_id)
        intel = intel_map.get(sku_id)

        eds = calculate_external_demand_score(
            agg["total_volume"], agg["avg_trend"], agg["avg_competition"]
        )
        ovs = calculate_own_visibility_score(
            agg["total_impressions"], agg["total_clicks"],
            agg["avg_ctr"], agg["avg_position"], agg["total_volume"]
        )
        sgs = calculate_search_gap_score(eds, ovs)

        items.append({
            "sku_id":           sku_id,
            "naam":             p.product_name if p else sku_id,
            "categorie":        p.category if p else "",
            "total_volume":     agg["total_volume"],
            "avg_trend":        round(agg["avg_trend"], 3),
            "eigen_impressies": agg["total_impressions"],
            "eigen_klikken":    agg["total_clicks"],
            "avg_positie":      round(agg["avg_position"], 1),
            "avg_cpc":          round(agg["avg_cpc"], 2),
            "keyword_count":    len(kws),
            "eds":              round(eds, 3),
            "ovs":              round(ovs, 3),
            "sgs":              round(sgs, 3),
            "gap_label":        _gap_label(sgs),
            "actie":            ACTIE_PER_GAP[_gap_label(sgs)],
            "traffic_intel_sgs": round(float(intel.search_gap_score or 0), 3) if intel else None,
        })

    # Sorteer op SGS (hoogste gap eerst)
    items.sort(key=lambda x: x["sgs"], reverse=True)

    # Totaaltellingen
    keyword_types: dict[str, int] = {}
    for r in search_rows:
        t = KEYWORD_TYPE_NL.get(r.keyword_type or "", r.keyword_type or "Onbekend")
        keyword_types[t] = keyword_types.get(t, 0) + 1

    return {
        "items": items,
        "totaal_keywords": len(search_rows),
        "totaal_volume": sum(r.search_volume or 0 for r in search_rows),
        "keyword_types": keyword_types,
        "gemiddelde_sgs": round(sum(i["sgs"] for i in items) / len(items), 3) if items else 0,
        "hoge_gap_count": sum(1 for i in items if i["sgs"] >= 0.60),
    }


# ─── GET /api/search-demand/sku/{sku_id} ─────────────────────────────────────

@router.get("/api/search-demand/sku/{sku_id}")
def get_search_demand_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    search_rows = db.query(models.FactSearchDemandDaily).filter_by(
        entity_id=sku_id
    ).order_by(models.FactSearchDemandDaily.search_volume.desc()).all()

    if not search_rows:
        raise HTTPException(404, f"Geen search demand data voor SKU {sku_id}")

    product = db.query(models.DimProduct).filter_by(sku_id=sku_id).first()
    agg = aggregate_sku_search_demand(search_rows)

    eds = calculate_external_demand_score(agg["total_volume"], agg["avg_trend"], agg["avg_competition"])
    ovs = calculate_own_visibility_score(agg["total_impressions"], agg["total_clicks"], agg["avg_ctr"], agg["avg_position"], agg["total_volume"])
    sgs = calculate_search_gap_score(eds, ovs)

    keywords = []
    for r in search_rows:
        kos = calculate_keyword_opportunity_score(r.search_volume or 0, r.competition_level or 0.5, float(r.cpc_estimate or 0), r.average_position or 10)
        keywords.append({
            "keyword":      r.keyword,
            "type":         r.keyword_type,
            "type_nl":      KEYWORD_TYPE_NL.get(r.keyword_type or "", "Onbekend"),
            "volume":       r.search_volume,
            "impressies":   r.impressions,
            "klikken":      r.clicks,
            "ctr":          round(r.ctr or 0, 4),
            "positie":      round(r.average_position or 10, 1),
            "trend":        round(r.trend_index or 0, 3),
            "concurrentie": round(r.competition_level or 0, 3),
            "cpc":          float(r.cpc_estimate or 0),
            "bron":         r.source,
            "kos":          round(kos, 3),
        })

    return {
        "sku_id": sku_id,
        "naam": product.product_name if product else sku_id,
        "categorie": product.category if product else "",
        "aggregaat": {
            "total_volume":     agg["total_volume"],
            "eigen_impressies": agg["total_impressions"],
            "eigen_klikken":    agg["total_clicks"],
            "avg_positie":      round(agg["avg_position"], 1),
            "avg_cpc":          round(agg["avg_cpc"], 2),
        },
        "scores": {
            "eds": round(eds, 3),
            "ovs": round(ovs, 3),
            "sgs": round(sgs, 3),
            "gap_label": _gap_label(sgs),
        },
        "actie": ACTIE_PER_GAP[_gap_label(sgs)],
        "keywords": keywords,
    }


# ─── GET /api/search-demand/categorie/{category} ─────────────────────────────

@router.get("/api/search-demand/categorie/{category}")
def get_search_demand_categorie(
    category: str,
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    products = db.query(models.DimProduct).filter_by(category=category).all()
    if not products:
        raise HTTPException(404, f"Categorie '{category}' niet gevonden")

    sku_ids = [p.sku_id for p in products]
    search_rows = db.query(models.FactSearchDemandDaily).filter(
        models.FactSearchDemandDaily.entity_id.in_(sku_ids)
    ).all()

    total_volume = sum(r.search_volume or 0 for r in search_rows)
    avg_trend = sum(r.trend_index or 0 for r in search_rows) / len(search_rows) if search_rows else 0
    total_impressions = sum(r.impressions or 0 for r in search_rows)
    total_clicks = sum(r.clicks or 0 for r in search_rows)

    return {
        "categorie": category,
        "totaal_keywords": len(search_rows),
        "total_volume": total_volume,
        "avg_trend": round(avg_trend, 3),
        "eigen_impressies": total_impressions,
        "eigen_klikken": total_clicks,
    }


@router.post("/api/search-demand/import")
def import_search_demand(_=Depends(auth_utils.get_current_user)):
    return {"status": "stub", "message": "CSV-import beschikbaar via /api/traffic/import"}
