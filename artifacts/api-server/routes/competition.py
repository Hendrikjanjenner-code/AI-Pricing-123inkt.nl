"""
Competition Intelligence Engine 2.0 — API routes.

Alle eindpunten voor de Competition Intelligence module:
- Bestaande PCIS/SKU-routes (backward compatible)
- Nieuwe discovery, profiling, categorie-scores, AI-matching,
  assortimentsgap, strategie en management-intelligence routes.
"""
from typing import Optional
from datetime import date, timedelta
from fastapi import APIRouter, Body, Depends, Query, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils
from engine import competition_intelligence
from routes.global_filters import sku_filter_query

router = APIRouter(prefix="/api/competition", tags=["competition"])


# ── Bestaande: Summary ────────────────────────────────────────────────────────

@router.get("/summary")
def get_competition_summary(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Shop-SKU's en de globale filtercontext als SQL-subquery's — nooit als
    # gematerialiseerde IN-lijst (parameterlimiet bij brede selecties).
    shop_skus_sq = (db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid)
                    .scalar_subquery())
    scores_q = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id.in_(shop_skus_sq))
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    if _sku_q is not None:
        scores_q = scores_q.filter(
            models.SkuCompetitionScore.sku_id.in_(_sku_q.scalar_subquery()))
    scores = scores_q.all()
    if not scores:
        return {
            "total_skus_scored": 0, "avg_pcis": 0,
            "critical_count": 0, "strong_count": 0,
            "influence_count": 0, "monitor_count": 0, "ignore_count": 0,
            "avg_price_index": 1.0, "total_competitors_excluded": 0,
            "downward_pressure_count": 0, "upward_opportunity_count": 0,
            "excluded_by_reason": {}, "last_run_date": None,
        }

    avg_pcis = sum(s.pcis_score or 0 for s in scores) / len(scores)
    class_counts: dict = {}
    for s in scores:
        c = s.competition_class or "Ignore"
        class_counts[c] = class_counts.get(c, 0) + 1

    price_indexed = [s for s in scores if s.price_index is not None]
    avg_pi = sum(s.price_index for s in price_indexed) / len(price_indexed) if price_indexed else 1.0
    total_excluded = sum(s.competitors_excluded or 0 for s in scores)

    # Uitsluitingen per reden over de laatste scoring-run
    last_run = max((s.run_date for s in scores if s.run_date), default=None)
    excluded_by_reason: dict = {}
    for s in scores:
        if last_run is not None and s.run_date != last_run:
            continue
        for reason, cnt in (s.excluded_reasons or {}).items():
            excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + (cnt or 0)
    downward = sum(1 for s in price_indexed if s.price_index < 0.97)
    upward = sum(1 for s in price_indexed if s.price_index > 1.03)

    return {
        "total_skus_scored": len(scores),
        "avg_pcis": round(avg_pcis, 4),
        "critical_count": class_counts.get("Critical", 0),
        "strong_count": class_counts.get("Strong", 0),
        "influence_count": class_counts.get("Influence", 0),
        "monitor_count": class_counts.get("Monitor", 0),
        "ignore_count": class_counts.get("Ignore", 0),
        "avg_price_index": round(avg_pi, 4),
        "total_competitors_excluded": total_excluded,
        "downward_pressure_count": downward,
        "upward_opportunity_count": upward,
        "excluded_by_reason": excluded_by_reason,
        "last_run_date": last_run.isoformat() if last_run else None,
    }


# ── Bestaande: SKU-lijst ──────────────────────────────────────────────────────

@router.get("/skus")
def list_competition_skus(
    competition_class: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("pcis_score"),
    sort_dir: Optional[str] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Begrens tot SKU's van deze shop en de globale filtercontext — als
    # SQL-subquery's, nooit als gematerialiseerde IN-lijst.
    shop_skus_sq = (db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid)
                    .scalar_subquery())
    q = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id.in_(shop_skus_sq))
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    if _sku_q is not None:
        q = q.filter(
            models.SkuCompetitionScore.sku_id.in_(_sku_q.scalar_subquery()))
    if competition_class:
        q = q.filter(models.SkuCompetitionScore.competition_class == competition_class)
    if category:
        cat_skus_sq = (db.query(models.DimProduct.sku_id)
                       .filter(models.DimProduct.category == category,
                               models.DimProduct.shop_id == sid)
                       .scalar_subquery())
        q = q.filter(models.SkuCompetitionScore.sku_id.in_(cat_skus_sq))

    total = q.count()
    col_map = {
        "pcis_score": models.SkuCompetitionScore.pcis_score,
        "price_index": models.SkuCompetitionScore.price_index,
        "product_comparability_score": models.SkuCompetitionScore.product_comparability_score,
        "price_sensitivity_score": models.SkuCompetitionScore.price_sensitivity_score,
    }
    sort_col = col_map.get(sort_by or "pcis_score", models.SkuCompetitionScore.pcis_score)
    q = q.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    sku_ids_page = [s.sku_id for s in items]
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids_page)).all()
    }
    return {
        "items": [_score_out(s, products.get(s.sku_id)) for s in items],
        "total": total, "page": page, "page_size": page_size,
    }


# ── Bestaande: SKU-detail ─────────────────────────────────────────────────────

@router.get("/skus/{sku_id}")
def get_sku_competition_detail(
    sku_id: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(404, "SKU niet gevonden voor deze winkel")
    score = (
        db.query(models.SkuCompetitionScore)
        .filter(models.SkuCompetitionScore.sku_id == sku_id)
        .order_by(models.SkuCompetitionScore.run_date.desc())
        .first()
    )

    recent_date = date.today() - timedelta(days=14)
    comp_prices = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(
            models.FactCompetitorPriceDaily.sku_id == sku_id,
            models.FactCompetitorPriceDaily.shop_id == sid,
            models.FactCompetitorPriceDaily.date >= recent_date,
        )
        .order_by(
            models.FactCompetitorPriceDaily.date.desc(),
            models.FactCompetitorPriceDaily.observed_at.desc().nulls_last(),
            models.FactCompetitorPriceDaily.id.desc(),
        )
        .all()
    )

    from services import import_settings as imps
    imp_settings = imps.get_settings(db)

    seen: set = set()
    competitor_detail = []
    ref_price = float(score.reference_price) if score and score.reference_price else None
    for c in comp_prices:
        if c.competitor_name not in seen:
            seen.add(c.competitor_name)
            price = float(c.price) if c.price else None
            is_excluded = False
            exclusion_reason = None
            if c.in_stock is False:
                # Niet-leverbare concurrent telt niet mee in de referentieprijs;
                # onbekende voorraad (None) telt wél mee (§task-116).
                is_excluded = True
                exclusion_reason = "COMPETITOR_IGNORED_OUT_OF_STOCK"
            elif imps.delivery_excluded(imp_settings, c.delivery_days):
                # Onwerkbaar lange levertijd telt niet mee in de referentieprijs;
                # onbekende levertijd (None) telt wél mee (§task-174).
                is_excluded = True
                exclusion_reason = "COMPETITOR_IGNORED_BAD_DELIVERY"
            elif ref_price and price:
                deviation = abs(price - ref_price) / (ref_price + 0.001)
                if deviation > 0.30:
                    is_excluded = True
                    exclusion_reason = "COMPETITOR_IGNORED_OUTLIER"
            competitor_detail.append({
                "competitor_name": c.competitor_name,
                "price": price,
                "date": c.date.isoformat() if c.date else None,
                "in_stock": c.in_stock,  # True/False/None (None = onbekend)
                "delivery_days": c.delivery_days,
                "currency": c.currency,
                "observed_at": c.observed_at.isoformat() if c.observed_at else None,
                "is_excluded": is_excluded,
                "exclusion_reason": exclusion_reason,
                "price_vs_own_pct": (
                    round((price / float(product.current_price) - 1) * 100, 2)
                    if price and product and product.current_price else None
                ),
                "price_vs_reference_pct": (
                    round((price / ref_price - 1) * 100, 2)
                    if price and ref_price else None
                ),
            })

    return {
        "sku_id": sku_id,
        "product": _product_brief(product),
        "competition_score": _score_out(score, product) if score else None,
        "competitor_detail": competitor_detail,
    }


# ── Bestaande: Charts ─────────────────────────────────────────────────────────

@router.get("/charts/pcis-distribution")
def get_pcis_distribution(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_skus_sq = (db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid)
                    .scalar_subquery())
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    out = []
    for cls in classes:
        q = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.competition_class == cls,
            models.SkuCompetitionScore.sku_id.in_(shop_skus_sq),
        )
        if _sku_q is not None:
            q = q.filter(models.SkuCompetitionScore.sku_id.in_(
                _sku_q.scalar_subquery()))
        out.append({"class": cls, "count": q.count()})
    return out


@router.get("/charts/price-index-by-category")
def get_price_index_by_category(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_skus_sq = (db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid)
                    .scalar_subquery())
    scores_q = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.price_index.isnot(None),
        models.SkuCompetitionScore.sku_id.in_(shop_skus_sq),
    )
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    if _sku_q is not None:
        scores_q = scores_q.filter(
            models.SkuCompetitionScore.sku_id.in_(_sku_q.scalar_subquery()))
    scores = scores_q.all()
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([s.sku_id for s in scores])
        ).all()
    }
    category_data: dict = {}
    for score in scores:
        p = products.get(score.sku_id)
        cat = (p.category if p else None) or "Unknown"
        category_data.setdefault(cat, []).append(float(score.price_index))
    return [
        {
            "category": cat,
            "avg_price_index": round(sum(indices) / len(indices), 4),
            "sku_count": len(indices),
        }
        for cat, indices in sorted(category_data.items())
    ]


@router.get("/charts/sub-scores-by-class")
def get_sub_scores_by_class(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_skus_sq = (db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid)
                    .scalar_subquery())
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    result = []
    for cls in classes:
        rows_q = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.competition_class == cls,
            models.SkuCompetitionScore.sku_id.in_(shop_skus_sq),
        )
        if _sku_q is not None:
            rows_q = rows_q.filter(models.SkuCompetitionScore.sku_id.in_(
                _sku_q.scalar_subquery()))
        rows = rows_q.all()
        if not rows:
            continue
        n = len(rows)
        result.append({
            "class": cls, "count": n,
            "avg_product_comparability": round(sum(r.product_comparability_score or 0 for r in rows) / n, 3),
            "avg_price_sensitivity": round(sum(r.price_sensitivity_score or 0 for r in rows) / n, 3),
            "avg_substitution": round(sum(r.substitution_score or 0 for r in rows) / n, 3),
            "avg_competitor_relevance": round(sum(r.competitor_relevance_score or 0 for r in rows) / n, 3),
            "avg_price_reliability": round(sum(r.competitor_price_reliability_score or 0 for r in rows) / n, 3),
            "avg_basket_dependency": round(sum(r.basket_dependency_score or 0 for r in rows) / n, 3),
            "avg_strategic_importance": round(sum(r.strategic_importance_score or 0 for r in rows) / n, 3),
        })
    return result


# ── NIEUW: Dashboard ──────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_competition_dashboard(
    category: Optional[str] = Query(None),
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Top-10 concurrenten per categorie met alle 7 scores, verkeerslicht,
    strategie-label en laatste prijswijziging — shop-gefilterd.

    Globale filtercontext (taak #263): bij een actieve hiërarchie-/merkselectie
    worden alleen categorieën met producten in de gefilterde SKU-set getoond,
    en alleen concurrenten die op die SKU's zijn waargenomen.
    """
    sid = _scope(db, shop_id)
    q = db.query(models.CategoryCompetitorRelevance).filter(
        models.CategoryCompetitorRelevance.shop_id == sid
    )
    if category:
        q = q.filter(models.CategoryCompetitorRelevance.category == category)
    _sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    if _sku_q is not None:
        # Gecorreleerd EXISTS: houd een (categorie, concurrent)-rij alleen als
        # de concurrent is waargenomen op een gefilterde SKU die zelf in die
        # categorie valt. Twee losse predicaten zouden een concurrent-rij voor
        # categorie B kunnen behouden puur omdat hij in categorie A op een
        # geselecteerde SKU is gezien.
        from sqlalchemy import exists, and_
        F = models.FactCompetitorPriceDaily
        P = models.DimProduct
        CCR = models.CategoryCompetitorRelevance
        q = q.filter(exists().where(and_(
            F.competitor_name == CCR.competitor_name,
            F.shop_id == sid,
            F.sku_id.in_(_sku_q.scalar_subquery()),
            P.sku_id == F.sku_id,
            P.shop_id == sid,
            P.category == CCR.category,
        )))
    rows = q.order_by(
        models.CategoryCompetitorRelevance.category,
        models.CategoryCompetitorRelevance.combined_score.desc(),
    ).all()

    # Groepeer per categorie en neem top-10
    categories: dict = {}
    for row in rows:
        cat_items = categories.setdefault(row.category, [])
        if len(cat_items) < 10:
            cat_items.append(_category_score_out(row))

    # Haal profielen en strategieën op — shop-gefilterd
    profielen = {
        p.competitor_name: p
        for p in db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.shop_id == sid
        ).all()
    }
    strategieen = {
        s.competitor_name: s
        for s in db.query(models.CompetitorStrategyResult)
        .filter(models.CompetitorStrategyResult.shop_id == sid)
        .order_by(
            models.CompetitorStrategyResult.competitor_name,
            models.CompetitorStrategyResult.run_date.desc(),
        )
        .all()
    }

    # Verrijk per concurrent
    result = []
    for cat, items in categories.items():
        for item in items:
            naam = item["competitor_name"]
            profiel = profielen.get(naam)
            strategie = strategieen.get(naam)
            item["assortment_size"] = profiel.assortment_size if profiel else None
            item["price_segment"] = profiel.price_segment if profiel else None
            item["last_price_change_date"] = (
                profiel.last_price_change_date.isoformat()
                if profiel and profiel.last_price_change_date else None
            )
            item["strategy_type"] = strategie.strategy_type if strategie else None
            item["strategy_label_nl"] = strategie.strategy_label_nl if strategie else None
            item["strategy_confidence"] = strategie.confidence if strategie else None
        result.append({"category": cat, "competitors": items})

    return {
        "categories": result,
        "total_categories": len(result),
        "filter_category": category,
        "shop_id": sid,
    }


# ── NIEUW: Discovery ──────────────────────────────────────────────────────────

@router.get("/discovery")
def list_discovery_queue(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Legacy-rijen (shop_id NULL, van vóór shop-scoping) horen bij de default shop.
    q = db.query(models.CompetitorDiscoveryQueue).filter(
        _shop_or_legacy(models.CompetitorDiscoveryQueue.shop_id, sid, db))
    if status:
        q = q.filter(models.CompetitorDiscoveryQueue.status == status)
    total = q.count()
    items = (
        q.order_by(
            models.CompetitorDiscoveryQueue.confidence.desc(),
            models.CompetitorDiscoveryQueue.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_discovery_out(i) for i in items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/discovery/run")
def trigger_discovery_run(
    categories: Optional[list[str]] = None,
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Start een nieuwe discovery-run (synchronous voor de pilot).

    min_confidence weggelaten = per-shop instelling uit competition_setting."""
    from engine.competitor_discovery import run_discovery
    sid = _scope(db, shop_id)
    result = run_discovery(db, categories=categories,
                           min_confidence=min_confidence, shop_id=sid)
    return {"status": "completed", **result}

@router.get("/settings")
def get_competition_settings(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Effectieve competition-instellingen voor een shop (defaults gemerged)."""
    from services import competition_settings as cs
    sid = _scope(db, shop_id)
    return {"shop_id": sid, "settings": cs.get_settings(db, sid)}
@router.post("/discovery/{item_id}/approve")
def approve_discovery_item(
    item_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    sid = _scope(db, shop_id)
    item = db.query(models.CompetitorDiscoveryQueue).filter(
        models.CompetitorDiscoveryQueue.id == item_id,
        _shop_or_legacy(models.CompetitorDiscoveryQueue.shop_id, sid, db),
    ).first()
    if not item:
        raise HTTPException(404, "Discovery-item niet gevonden")
    item.status = "APPROVED"
    item.approved_by = current_user.username
    from datetime import datetime
    item.approved_at = datetime.utcnow()
    db.commit()
    return {"status": "approved", "id": item_id}


@router.post("/discovery/{item_id}/reject")
def reject_discovery_item(
    item_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    sid = _scope(db, shop_id)
    item = db.query(models.CompetitorDiscoveryQueue).filter(
        models.CompetitorDiscoveryQueue.id == item_id,
        _shop_or_legacy(models.CompetitorDiscoveryQueue.shop_id, sid, db),
    ).first()
    if not item:
        raise HTTPException(404, "Discovery-item niet gevonden")
    item.status = "REJECTED"
    item.approved_by = current_user.username
    from datetime import datetime
    item.approved_at = datetime.utcnow()
    db.commit()
    return {"status": "rejected", "id": item_id}


# ── NIEUW: Concurrenten (profielen) ──────────────────────────────────────────

@router.get("/competitors")
def list_competitors(
    relevance_label: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    q = db.query(models.CompetitorProfile).filter(
        models.CompetitorProfile.shop_id == sid
    )
    if relevance_label:
        q = q.filter(models.CompetitorProfile.relevance_label == relevance_label)
    # Globale filtercontext (taak #263): alleen concurrenten die zijn
    # waargenomen op de gefilterde SKU-set — als SQL-subquery.
    _gf_sq = _filtered_competitor_names_sq(db, sid, hierarchy_node_ids, brands)
    if _gf_sq is not None:
        q = q.filter(models.CompetitorProfile.competitor_name.in_(_gf_sq))
    total = q.count()
    items = (
        q.order_by(models.CompetitorProfile.functional_overlap_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    seen = _seen_info_bulk(db, sid, [p.competitor_name for p in items])
    return {
        "items": [_profile_out(p) | seen[p.competitor_name] for p in items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/competitors/{competitor_name}")
def get_competitor_profile(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    competitor_name = _canon(competitor_name)
    profile = (
        db.query(models.CompetitorProfile)
        .filter(models.CompetitorProfile.competitor_name == competitor_name,
                models.CompetitorProfile.shop_id == sid)
        .first()
    )
    if not profile:
        raise HTTPException(404, f"Concurrent '{competitor_name}' niet gevonden")

    # Haal categoriescores op (shop-gefilterd)
    cat_scores = (
        db.query(models.CategoryCompetitorRelevance)
        .filter(models.CategoryCompetitorRelevance.competitor_name == competitor_name,
                models.CategoryCompetitorRelevance.shop_id == sid)
        .order_by(models.CategoryCompetitorRelevance.combined_score.desc())
        .all()
    )

    # Haal strategie op (shop-gefilterd)
    strategie = (
        db.query(models.CompetitorStrategyResult)
        .filter(models.CompetitorStrategyResult.competitor_name == competitor_name,
                models.CompetitorStrategyResult.shop_id == sid)
        .order_by(models.CompetitorStrategyResult.run_date.desc())
        .first()
    )

    return {
        "profile": _profile_out(profile) | _seen_info(db, sid, profile.competitor_name),
        "category_scores": [_category_score_out(r) for r in cat_scores],
        "strategy": _strategy_out(strategie) if strategie else None,
    }


# ── NIEUW: Categorie Analyse ──────────────────────────────────────────────────

@router.get("/categories")
def list_category_scores(
    category: Optional[str] = Query(None),
    relevance_label: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    q = db.query(models.CategoryCompetitorRelevance).filter(
        models.CategoryCompetitorRelevance.shop_id == sid)
    if category:
        q = q.filter(models.CategoryCompetitorRelevance.category == category)
    if relevance_label:
        q = q.filter(models.CategoryCompetitorRelevance.relevance_label == relevance_label)
    total = q.count()
    items = (
        q.order_by(
            models.CategoryCompetitorRelevance.category,
            models.CategoryCompetitorRelevance.combined_score.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_category_score_out(r) for r in items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/categories/{category_name}")
def get_category_detail(
    category_name: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    rows = (
        db.query(models.CategoryCompetitorRelevance)
        .filter(models.CategoryCompetitorRelevance.category == category_name,
                models.CategoryCompetitorRelevance.shop_id == sid)
        .order_by(models.CategoryCompetitorRelevance.combined_score.desc())
        .all()
    )
    if not rows:
        raise HTTPException(404, f"Categorie '{category_name}' niet gevonden")

    # Assortimentsgaten
    gaps = (
        db.query(models.AssortmentGap)
        .filter(models.AssortmentGap.category == category_name)
        .order_by(models.AssortmentGap.opportunity_score.desc())
        .limit(20)
        .all()
    )

    return {
        "category": category_name,
        "competitors": [_category_score_out(r) for r in rows],
        "assortment_gaps": [_gap_out(g) for g in gaps],
        "total_competitors": len(rows),
        "high_count": sum(1 for r in rows if r.relevance_label == "HIGH"),
        "monitor_count": sum(1 for r in rows if r.relevance_label == "MONITOR"),
        "avg_coverage_index": round(sum(r.coverage_index or 0 for r in rows) / len(rows), 1) if rows else 0,
        "avg_opportunity_score": round(sum(r.opportunity_score or 0 for r in rows) / len(rows), 1) if rows else 0,
    }


# ── NIEUW: AI Matching ────────────────────────────────────────────────────────

@router.get("/ai-matching")
def list_ai_matches(
    match_type: Optional[str] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    status: Optional[str] = Query(None),
    sku_id: Optional[str] = Query(None),
    suspect: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Shop-scope: sku_id is globaal uniek (één shop per SKU), dus begrenzen op
    # SKU's van deze shop is sluitend; de shop_id-kolomfilter sluit daarnaast
    # mislabelde rijen uit (legacy-rijen dragen de default shop_id).
    from services.competition_settings import default_shop_id
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    q = db.query(models.AiMatchResult).filter(
        models.AiMatchResult.own_sku_id.in_(shop_sku_ids),
        or_(models.AiMatchResult.shop_id == sid,
            models.AiMatchResult.shop_id == default_shop_id(db),
            models.AiMatchResult.shop_id.is_(None)),
    )
    if match_type:
        q = q.filter(models.AiMatchResult.match_type == match_type)
    if min_confidence > 0:
        q = q.filter(models.AiMatchResult.confidence >= min_confidence)
    if status:
        q = q.filter(models.AiMatchResult.status == status)
    if sku_id:
        q = q.filter(models.AiMatchResult.own_sku_id == sku_id)
    suspect_threshold = competition_intelligence.suspicious_match_threshold_pct(db)
    if suspect:
        # Verdachte matches: |prijsverschil| > drempel en nog PENDING
        q = q.filter(
            models.AiMatchResult.status == "PENDING",
            models.AiMatchResult.price_diff_pct.isnot(None),
            (models.AiMatchResult.price_diff_pct > suspect_threshold)
            | (models.AiMatchResult.price_diff_pct < -suspect_threshold),
        )

    total = q.count()
    items = (
        q.order_by(models.AiMatchResult.confidence.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Verrijk met productnamen
    sku_ids = [i.own_sku_id for i in items]
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids)).all()
    }

    return {
        "items": [_match_out(m, products.get(m.own_sku_id)) for m in items],
        "total": total, "page": page, "page_size": page_size,
        "suspect_threshold_pct": suspect_threshold,
    }


def _verify_match_shop(db: Session, match_id: int, sid: int) -> models.AiMatchResult:
    """Haal een AiMatchResult op en verifieer dat het bij de opgegeven shop hoort."""
    match = db.query(models.AiMatchResult).filter(models.AiMatchResult.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match niet gevonden")
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == match.own_sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(404, "Match niet gevonden")
    return match


@router.post("/ai-matching/{match_id}/approve")
def approve_match(
    match_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    sid = _scope(db, shop_id)
    match = _verify_match_shop(db, match_id, sid)
    match.status = "APPROVED"
    match.approved_by = current_user.username
    from datetime import datetime
    match.approved_at = datetime.utcnow()
    db.commit()
    return {"status": "approved", "id": match_id}


@router.post("/ai-matching/{match_id}/reject")
def reject_match(
    match_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    sid = _scope(db, shop_id)
    match = _verify_match_shop(db, match_id, sid)
    match.status = "REJECTED"
    match.approved_by = current_user.username
    from datetime import datetime
    match.approved_at = datetime.utcnow()
    db.commit()
    return {"status": "rejected", "id": match_id}


# ── NIEUW: Assortiment Gap ────────────────────────────────────────────────────

@router.get("/assortment-gap")
def list_assortment_gaps(
    category: Optional[str] = Query(None),
    gap_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.AssortmentGap)
    if category:
        q = q.filter(models.AssortmentGap.category == category)
    if gap_type:
        q = q.filter(models.AssortmentGap.gap_type == gap_type)
    total = q.count()
    items = (
        q.order_by(models.AssortmentGap.opportunity_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_gap_out(g) for g in items],
        "total": total, "page": page, "page_size": page_size,
    }


# ── NIEUW: Strategie Analyse (verbeterd) ──────────────────────────────────────

@router.get("/strategies")
def get_competitor_strategies(
    lookback_days: int = Query(30, ge=7, le=180),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Herkent per concurrent de prijsstrategie uit de ECHTE concurrentprijs-
    historie in de PriceShape-feed (fact_competitor_price_daily). Betrouwbare
    herkenning vereist meerdere dagen historie; bij te weinig historie wordt een
    waarschuwing meegegeven (`low_history`). Shop-gefilterd.
    """
    from engine.competitor_strategy_engine import analyseer_alle_concurrenten
    sid = _scope(db, shop_id)
    since = date.today() - timedelta(days=lookback_days)
    rijen = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(models.FactCompetitorPriceDaily.date >= since,
                models.FactCompetitorPriceDaily.shop_id == sid)
        .order_by(
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date,
        )
        .all()
    )
    prijsdata: dict = {}
    for r in rijen:
        naam = r.competitor_name or "Onbekend"
        if r.price is None:
            continue
        prijsdata.setdefault(naam, []).append((r.date, float(r.price)))

    if not prijsdata:
        return {
            "strategieen": [],
            "periode": "Geen concurrentprijs-historie",
            "lookback_days": lookback_days,
            "totaal_concurrenten": 0,
            "source": "feed",
            "low_history": True,
            "history_notice": (
                "Er is nog geen concurrentprijs-historie uit de PriceShape-feed. "
                "Synchroniseer de feed en draai een modelrun om strategie-herkenning "
                "op te bouwen."
            ),
        }

    # Historiediepte = grootste aantal unieke datums over alle concurrenten.
    max_dagen = max(len({d for d, _ in reeks}) for reeks in prijsdata.values())
    # Betrouwbare classificatie vereist minstens ~5 datapunten (zie engine).
    MIN_DAGEN = 5
    low_history = max_dagen < MIN_DAGEN

    resultaten = analyseer_alle_concurrenten(prijsdata)
    out = {
        "strategieen": resultaten,
        "periode": f"{since.isoformat()} – {date.today().isoformat()}",
        "lookback_days": lookback_days,
        "totaal_concurrenten": len(resultaten),
        "source": "feed",
        "history_days": max_dagen,
        "low_history": low_history,
    }
    if low_history:
        out["history_notice"] = (
            f"Beperkte historie: slechts {max_dagen} dag(en) concurrentprijs-data "
            f"beschikbaar (aanbevolen ≥ {MIN_DAGEN}). De herkende strategieën zijn "
            "indicatief en worden betrouwbaarder naarmate de feed langer draait."
        )
    return out


# ── NIEUW: Management Intelligence ────────────────────────────────────────────

@router.get("/management")
def get_management_intelligence(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    from engine.management_intelligence import build_management_insights
    insights = build_management_insights(db, category=category)
    return {
        "insights": insights,
        "total_categories": len(insights),
        "filter_category": category,
    }


# ── NIEUW: Discovery Log ──────────────────────────────────────────────────────

@router.get("/discovery-log")
def list_discovery_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    scoped = db.query(models.CompetitorDiscoveryRun).filter(
        _shop_or_legacy(models.CompetitorDiscoveryRun.shop_id, sid, db))
    total = scoped.count()
    items = (
        scoped
        .order_by(models.CompetitorDiscoveryRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_run_out(r) for r in items],
        "total": total, "page": page, "page_size": page_size,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_out(s: models.SkuCompetitionScore, product=None) -> dict:
    return {
        "id": s.id, "sku_id": s.sku_id,
        "product_name": product.product_name if product else s.sku_id,
        "category": product.category if product else None,
        "brand": product.brand if product else None,
        "ean": product.ean if product else None,
        "oem_code": product.oem_code if product else None,
        "run_date": s.run_date.isoformat() if s.run_date else None,
        "product_comparability_score": s.product_comparability_score,
        "price_sensitivity_score": s.price_sensitivity_score,
        "substitution_score": s.substitution_score,
        "competitor_relevance_score": s.competitor_relevance_score,
        "competitor_price_reliability_score": s.competitor_price_reliability_score,
        "basket_dependency_score": s.basket_dependency_score,
        "strategic_importance_score": s.strategic_importance_score,
        "pcis_score": s.pcis_score,
        "competition_class": s.competition_class,
        "reference_price": float(s.reference_price) if s.reference_price else None,
        "price_index": s.price_index,
        "current_price": float(product.current_price) if product and product.current_price else None,
        "competitors_used": s.competitors_used,
        "competitors_excluded": s.competitors_excluded,
        "excluded_reasons": s.excluded_reasons or {},
    }


def _product_brief(p) -> dict:
    if not p:
        return {}
    return {
        "sku_id": p.sku_id, "product_name": p.product_name,
        "brand": p.brand, "category": p.category, "subcategory": p.subcategory,
        "is_private_label": p.is_private_label, "is_a_brand": p.is_a_brand,
        "lifecycle_status": p.lifecycle_status,
        "current_price": float(p.current_price) if p.current_price else None,
        "cost_price": float(p.cost_price) if p.cost_price else None,
        "min_price": float(p.min_price) if p.min_price else None,
        "max_price": float(p.max_price) if p.max_price else None,
        "stock_quantity": p.stock_quantity,
    }


_RECENT_UNSEEN_DAYS = 3


def _seen_info_bulk(db: Session, sid: int, names: list[str]) -> dict[str, dict]:
    """"Recent niet gezien"-markering — SHOP-gescoped uit de waarnemingsdata.

    Verdwenen concurrenten worden nooit verwijderd (last-known-good); ze
    worden alleen gemarkeerd als hun laatste waarneming binnen déze shop
    ≥ 3 dagen achterloopt op de nieuwste waarneming binnen dezelfde shop.
    Referentie is dus niet 'vandaag' (een stilgevallen feed zou anders ineens
    álle concurrenten als verdwenen aanmerken) en niet een andere shop (een
    waarneming in shop A zegt niets over shop B).
    """
    from sqlalchemy import func
    if not names:
        return {}
    F = models.FactCompetitorPriceDaily
    latest = (db.query(func.max(F.date))
              .filter(F.shop_id == sid).scalar())
    seen_by_name: dict[str, object] = {}
    for chunk in (names[i:i + 1000] for i in range(0, len(names), 1000)):
        seen_by_name.update(dict(
            db.query(F.competitor_name, func.max(F.date))
            .filter(F.shop_id == sid, F.competitor_name.in_(chunk))
            .group_by(F.competitor_name).all()))
    out = {}
    for n in names:
        last_seen = seen_by_name.get(n)
        out[n] = {
            "last_seen_date": last_seen.isoformat() if last_seen else None,
            "recently_unseen": bool(
                last_seen is not None and latest is not None
                and (latest - last_seen).days >= _RECENT_UNSEEN_DAYS),
        }
    return out


def _seen_info(db: Session, sid: int, competitor_name: str) -> dict:
    return _seen_info_bulk(db, sid, [competitor_name]).get(
        competitor_name,
        {"last_seen_date": None, "recently_unseen": False})


def _profile_out(p: models.CompetitorProfile) -> dict:
    return {
        "id": p.id,
        "competitor_name": p.competitor_name,
        "domain": p.domain,
        "assortment_size": p.assortment_size,
        "category_breadth": p.category_breadth,
        "top_brands": p.top_brands or [],
        "top_categories": p.top_categories or [],
        "price_segment": p.price_segment,
        "premium_share_pct": p.premium_share_pct,
        "budget_share_pct": p.budget_share_pct,
        "avg_price_index": p.avg_price_index,
        "price_change_frequency": p.price_change_frequency,
        "last_price_change_date": p.last_price_change_date.isoformat() if p.last_price_change_date else None,
        "avg_delivery_days": p.avg_delivery_days,
        "in_stock_rate": p.in_stock_rate,
        "functional_overlap_score": p.functional_overlap_score,
        "relevance_label": p.relevance_label,
        "traffic_light": p.traffic_light,
        "run_date": p.run_date.isoformat() if p.run_date else None,
    }


def _category_score_out(r: models.CategoryCompetitorRelevance) -> dict:
    return {
        "id": r.id,
        "competitor_name": r.competitor_name,
        "category": r.category,
        "relevance_score": r.relevance_score,
        "coverage_index": r.coverage_index,
        "authority_score": r.authority_score,
        "assortment_gap_score": r.assortment_gap_score,
        "pricing_relevance_score": r.pricing_relevance_score,
        "traffic_relevance_score": r.traffic_relevance_score,
        "opportunity_score": r.opportunity_score,
        "combined_score": r.combined_score,
        "relevance_label": r.relevance_label,
        "traffic_light": r.traffic_light,
        "relevance_explanation": r.relevance_explanation,
        "opportunity_explanation": r.opportunity_explanation,
        "missing_brands": r.missing_brands or [],
        "run_date": r.run_date.isoformat() if r.run_date else None,
    }


def _match_out(m: models.AiMatchResult, product=None) -> dict:
    return {
        "id": m.id,
        "own_sku_id": m.own_sku_id,
        "product_name": product.product_name if product else m.own_sku_id,
        "category": product.category if product else None,
        "ean": product.ean if product else None,
        "oem_code": product.oem_code if product else None,
        "competitor_name": m.competitor_name,
        "competitor_sku": m.competitor_sku,
        "competitor_url": m.competitor_url,
        "match_type": m.match_type,
        "confidence": m.confidence,
        "explanation_nl": m.explanation_nl,
        "ean_match": m.ean_match,
        "mpn_match": m.mpn_match,
        "oem_match": m.oem_match,
        "brand_match": m.brand_match,
        "product_type_match": m.product_type_match,
        "price_segment_match": m.price_segment_match,
        "competitor_price": float(m.competitor_price) if m.competitor_price else None,
        "own_price": float(m.own_price) if m.own_price else None,
        "price_diff_pct": m.price_diff_pct,
        "status": m.status,
        "approved_by": m.approved_by,
        "run_date": m.run_date.isoformat() if m.run_date else None,
    }


def _strategy_out(s: models.CompetitorStrategyResult) -> dict:
    return {
        "id": s.id,
        "competitor_name": s.competitor_name,
        "run_date": s.run_date.isoformat() if s.run_date else None,
        "strategy_type": s.strategy_type,
        "strategy_label_nl": s.strategy_label_nl,
        "confidence": s.confidence,
        "explanation_nl": s.explanation_nl,
        "recommended_action_nl": s.recommended_action_nl,
        "period_days": s.period_days,
        "data_points": s.data_points,
        "previous_strategy_type": s.previous_strategy_type,
        "strategy_changed": s.strategy_changed,
    }


def _gap_out(g: models.AssortmentGap) -> dict:
    return {
        "id": g.id,
        "category": g.category,
        "competitor_name": g.competitor_name,
        "gap_type": g.gap_type,
        "gap_value": g.gap_value,
        "opportunity_score": g.opportunity_score,
        "explanation_nl": g.explanation_nl,
        "competitor_has": g.competitor_has,
        "potential_revenue_eur": g.potential_revenue_eur,
        "run_date": g.run_date.isoformat() if g.run_date else None,
    }


def _discovery_out(i: models.CompetitorDiscoveryQueue) -> dict:
    return {
        "id": i.id,
        "domain": i.domain,
        "competitor_name": i.competitor_name,
        "discovery_reason": i.discovery_reason,
        "discovery_method": i.discovery_method,
        "categories": i.categories or [],
        "confidence": i.confidence,
        "status": i.status,
        "approved_by": i.approved_by,
        "approved_at": i.approved_at.isoformat() if i.approved_at else None,
        "run_id": i.run_id,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _run_out(r: models.CompetitorDiscoveryRun) -> dict:
    return {
        "id": r.id,
        "run_id": r.run_id,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "status": r.status,
        "categories_searched": r.categories_searched or [],
        "candidates_found": r.candidates_found,
        "candidates_new": r.candidates_new,
        "candidates_approved": r.candidates_approved,
        "candidates_rejected": r.candidates_rejected,
        "parameters": r.parameters or {},
        "error_message": r.error_message,
    }


# ── NIEUW: Rankings (§9 + §11) ───────────────────────────────────────────────

def _ranking_filter_context(db: Session, sid: int, names: list[str]) -> dict:
    """Profieldata per concurrent voor server-side rankingfilters."""
    from engine.competitor_scores import latest_scores_by_competitor
    scores = latest_scores_by_competitor(db, sid)
    business = {b.competitor_name: b for b in
                db.query(models.CompetitorBusinessProfile).filter(
                    models.CompetitorBusinessProfile.shop_id == sid,
                    models.CompetitorBusinessProfile.competitor_name.in_(names)).all()}
    fulfilment = {f.competitor_name: f for f in
                  db.query(models.CompetitorFulfilmentProfile).filter(
                      models.CompetitorFulfilmentProfile.shop_id == sid,
                      models.CompetitorFulfilmentProfile.competitor_name.in_(names)).all()}
    roles: dict = {}
    for r in db.query(models.CompetitorMarketRole).filter(
            models.CompetitorMarketRole.shop_id == sid,
            models.CompetitorMarketRole.competitor_name.in_(names),
            models.CompetitorMarketRole.valid_to.is_(None)).all():
        roles.setdefault(r.competitor_name, set()).add(r.role)
    countries: dict = {}
    for g in db.query(models.CompetitorGeographicPresence).filter(
            models.CompetitorGeographicPresence.shop_id == sid,
            models.CompetitorGeographicPresence.competitor_name.in_(names),
            models.CompetitorGeographicPresence.valid_to.is_(None)).all():
        if g.country_code:
            countries.setdefault(g.competitor_name, set()).add(g.country_code.upper())
    return {"scores": scores, "business": business, "fulfilment": fulfilment,
            "roles": roles, "countries": countries}


def _ranking_passes_filters(name: str, ctx: dict, *, company_size, geographic_scale,
                            country, customer_model, market_role, fulfilment_model,
                            financial_health, min_business_strength,
                            min_procurement_power, min_data_completeness) -> bool:
    s = ctx["scores"].get(name)
    b = ctx["business"].get(name)
    f = ctx["fulfilment"].get(name)
    if company_size and not (
            (s and s.company_size_class == company_size)
            or (b and b.size_class == company_size)):
        return False
    if geographic_scale and not (
            (s and s.geographic_scale_class == geographic_scale)
            or (b and b.geographic_scale == geographic_scale)):
        return False
    if country and country.upper() not in ctx["countries"].get(name, set()):
        return False
    if customer_model and not (b and b.customer_model == customer_model):
        return False
    if market_role and market_role not in ctx["roles"].get(name, set()):
        return False
    if fulfilment_model and not (
            (s and s.fulfilment_model_class == fulfilment_model)
            or (f and f.inventory_model == fulfilment_model)):
        return False
    if financial_health and not (s and s.financial_health_status == financial_health):
        return False
    if min_business_strength is not None and not (
            s and s.business_strength_score is not None
            and float(s.business_strength_score) >= min_business_strength):
        return False
    if min_procurement_power is not None and not (
            s and s.procurement_power_score is not None
            and float(s.procurement_power_score) >= min_procurement_power):
        return False
    if min_data_completeness is not None and not (
            s and s.data_completeness_pct is not None
            and float(s.data_completeness_pct) >= min_data_completeness):
        return False
    return True


@router.get("/rankings")
def get_competitor_rankings(
    scope: str = Query("overall"),
    shop_id: Optional[int] = Query(None),
    company_size: Optional[str] = Query(None),
    geographic_scale: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    customer_model: Optional[str] = Query(None, description="B2C / B2B / hybride"),
    market_role: Optional[str] = Query(None, description="Competition DNA-rol"),
    fulfilment_model: Optional[str] = Query(None, description="stockholding / dropship / hybrid / marketplace"),
    financial_health: Optional[str] = Query(None, description="gezond / aandacht / zwak / unknown"),
    min_business_strength: Optional[float] = Query(None, ge=0.0, le=100.0),
    min_procurement_power: Optional[float] = Query(None, ge=0.0, le=100.0),
    min_data_completeness: Optional[float] = Query(None, ge=0.0, le=100.0),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Concurrentrankings met de drie gestandaardiseerde scores (§9):
    Competition Relevance, Price Relevance en Influence — plus rank,
    vorige rank en trend (§11). Server-side filterbaar op profielkenmerken
    en scoreklassen (taak #248); totalen kloppen met de filters.
    """
    from sqlalchemy import func as _func
    sid = _scope(db, shop_id)
    latest = db.query(_func.max(models.CompetitorRanking.run_date)).filter(
        models.CompetitorRanking.scope == scope,
        models.CompetitorRanking.shop_id == sid,
    ).scalar()
    last_sync_at = _last_feed_sync_at(db)
    if not latest:
        return {"scope": scope, "run_date": None, "rankings": [], "total": 0,
                "computed_at": None,
                "last_feed_sync_at": last_sync_at.isoformat() if last_sync_at else None,
                "stale": last_sync_at is not None,
                "changed": False,
                "scopes": _ranking_scopes(db, sid)}

    rows_q = (
        db.query(models.CompetitorRanking)
        .filter(models.CompetitorRanking.scope == scope,
                models.CompetitorRanking.run_date == latest,
                models.CompetitorRanking.shop_id == sid)
    )
    # Globale filtercontext (taak #263): beperk tot concurrenten die zijn
    # waargenomen op de gefilterde SKU-set (hiërarchie-descendants + merken)
    # — toegepast in SQL vóór het laden van de rijen.
    _gf_sq = _filtered_competitor_names_sq(db, sid, hierarchy_node_ids, brands)
    if _gf_sq is not None:
        rows_q = rows_q.filter(
            models.CompetitorRanking.competitor_name.in_(_gf_sq))
    rows = rows_q.order_by(models.CompetitorRanking.rank).all()
    filters_active = any(v is not None for v in (
        company_size, geographic_scale, country, customer_model, market_role,
        fulfilment_model, financial_health, min_business_strength,
        min_procurement_power, min_data_completeness))
    if filters_active:
        ctx = _ranking_filter_context(db, sid, [r.competitor_name for r in rows])
        rows = [r for r in rows if _ranking_passes_filters(
            r.competitor_name, ctx,
            company_size=company_size, geographic_scale=geographic_scale,
            country=country, customer_model=customer_model,
            market_role=market_role, fulfilment_model=fulfilment_model,
            financial_health=financial_health,
            min_business_strength=min_business_strength,
            min_procurement_power=min_procurement_power,
            min_data_completeness=min_data_completeness)]
    # Versheid: wanneer zijn deze rankings berekend, en is er sindsdien een
    # nieuwe feed-sync geweest (dan zijn ze "verouderd")?
    computed_at = max((r.created_at for r in rows if r.created_at), default=None)
    stale = bool(last_sync_at and computed_at and computed_at < last_sync_at)
    # "Gewijzigd" = er is een vorige run om mee te vergelijken én er zijn
    # verschuivingen. Bij de allereerste run (alles "new", geen previous_rank)
    # is er niets gewijzigd — dan zou een banner misleidend zijn.
    had_previous = any(r.previous_rank is not None for r in rows)
    changed = had_previous and any(
        (r.rank_trend or "stable") not in ("stable",) for r in rows)
    return {
        "scope": scope,
        "run_date": str(latest),
        "computed_at": computed_at.isoformat() if computed_at else None,
        "last_feed_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "stale": stale,
        "changed": changed,
        "total": len(rows),
        "scopes": _ranking_scopes(db, sid),
        "rankings": [
            {
                "rank": r.rank,
                "previous_rank": r.previous_rank,
                "trend": r.rank_trend,
                "competitor_name": r.competitor_name,
                "competition_relevance_score": round(float(r.competition_relevance_score or 0), 4),
                "price_relevance_score": round(float(r.price_relevance_score or 0), 4),
                "influence_score": round(float(r.influence_score or 0), 4),
                "combined_score": round(float(r.combined_score or 0), 4),
                "confidence": round(float(r.confidence or 0), 2),
                "explanation": r.explanation,
                "evidence": r.evidence,
                "model_version": r.model_version,
            }
            for r in rows
        ],
    }


@router.get("/rankings/history")
def get_competitor_ranking_history(
    scope: str = Query("overall"),
    shop_id: Optional[int] = Query(None),
    competitor: Optional[str] = Query(None),
    limit_runs: int = Query(12, ge=1, le=60),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Rank-verloop per concurrent over eerdere runs (§11): per run_date de rank
    en combined score, zodat structurele stijgers/dalers zichtbaar zijn.
    Beperkt tot de laatste `limit_runs` runs binnen scope + shop.
    """
    sid = _scope(db, shop_id)
    run_dates = [
        r[0] for r in
        db.query(models.CompetitorRanking.run_date)
        .filter(models.CompetitorRanking.scope == scope,
                models.CompetitorRanking.shop_id == sid)
        .distinct()
        .order_by(models.CompetitorRanking.run_date.desc())
        .limit(limit_runs)
        .all()
    ]
    if not run_dates:
        return {"scope": scope, "run_dates": [], "history": {}}
    q = (
        db.query(models.CompetitorRanking)
        .filter(models.CompetitorRanking.scope == scope,
                models.CompetitorRanking.shop_id == sid,
                models.CompetitorRanking.run_date.in_(run_dates))
    )
    if competitor:
        q = q.filter(models.CompetitorRanking.competitor_name == _canon(competitor))
    _gf_sq = _filtered_competitor_names_sq(db, sid, hierarchy_node_ids, brands)
    if _gf_sq is not None:
        q = q.filter(models.CompetitorRanking.competitor_name.in_(_gf_sq))
    rows = q.order_by(models.CompetitorRanking.run_date.asc(),
                      models.CompetitorRanking.rank.asc()).all()
    history: dict = {}
    for r in rows:
        history.setdefault(r.competitor_name, []).append({
            "run_date": str(r.run_date),
            "rank": r.rank,
            "combined_score": round(float(r.combined_score or 0), 4),
        })
    return {
        "scope": scope,
        "run_dates": [str(d) for d in sorted(run_dates)],
        "history": history,
    }


def _filtered_competitor_names_sq(
    db: Session, sid: Optional[int],
    hierarchy_node_ids: Optional[str] = None,
    brands: Optional[str] = None,
):
    """Scalar-subquery met concurrentnamen die zijn waargenomen op de
    gefilterde SKU-set (globale filtercontext, taak #263).

    None = geen globale filter actief (alles tonen). Anders een subquery die
    rechtstreeks in `competitor_name.in_(...)`-predicaten past. Alles blijft
    SQL — geen gematerialiseerde SKU- of naamlijsten — zodat ook brede
    hiërarchie-/merkselecties met duizenden SKU's nooit tegen
    parameterlimieten aanlopen.
    """
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands)
    if sku_q is None:
        return None
    F = models.FactCompetitorPriceDaily
    q = db.query(F.competitor_name).filter(
        F.sku_id.in_(sku_q.scalar_subquery()))
    if sid is not None:
        q = q.filter(F.shop_id == sid)
    return q.distinct().scalar_subquery()


def _last_feed_sync_at(db: Session):
    """Tijdstip van de laatste geslaagde PriceShape-feed-sync (of None)."""
    cfg = (db.query(models.ConnectorConfig)
           .filter(models.ConnectorConfig.connector_name == "priceshape")
           .first())
    return cfg.last_synced_at if cfg else None


def _ranking_scopes(db: Session, shop_id: Optional[int] = None) -> list[str]:
    q = db.query(models.CompetitorRanking.scope).distinct()
    if shop_id is not None:
        q = q.filter(models.CompetitorRanking.shop_id == shop_id)
    scopes = [s[0] for s in q.all()]
    return sorted(scopes, key=lambda s: (s != "overall", s))


def _run_rankings_job(db: Session, shop_id: Optional[int] = None) -> dict:
    """
    Herbereken de competitor rankings (drie-scoremodel §9-§11).

    Stap 1: bereken CIS-scores per SKU/concurrent uit de prijshistorie en
            schrijf ze naar competitor_influence_scores.
    Stap 2: bereken rankings die de CIS-scores als Influence-component lezen.

    shop_id (optioneel): beperk de run tot één shop (sneller bij tests/gefocuste runs).
    """
    from engine.competitor_influence import run_cis_engine
    from engine.competition_rankings import run_competitor_rankings
    from services.refresh import _feed_sync_lock

    with _feed_sync_lock() as got:
        if not got:
            raise RuntimeError(
                "Er draait momenteel een feed-sync; probeer het zo dadelijk opnieuw."
            )
        return _do_rankings_run(db, shop_id, run_cis_engine, run_competitor_rankings)


def _do_rankings_run(db, shop_id, run_cis_engine, run_competitor_rankings) -> dict:
    if shop_id is not None:
        sku_ids = [p.sku_id for p in
                   db.query(models.DimProduct).filter(
                       models.DimProduct.shop_id == shop_id).all()]
        # Lege shop = no-op; voorkom dat een lege lijst als None behandeld wordt
        # waardoor de volledige CIS-engine zou draaien.
        if not sku_ids:
            cis_written = 0
        else:
            cis_written = run_cis_engine(db, sku_ids=sku_ids)
    else:
        cis_written = run_cis_engine(db)
    rankings_written = run_competitor_rankings(db, shop_id=shop_id)
    return {
        "status": "voltooid",
        "cis_scores_geschreven": cis_written,
        "rankings_geschreven": rankings_written,
    }


@router.post("/rankings/run")
def run_rankings(
    shop_id: Optional[int] = Query(None),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Start de rankings-herberekening op de achtergrond; retourneert een job-id.

    De CIS-engine kan bij grote catalogi ruim langer duren dan de request-
    timeout; daarom loopt de run als achtergrondjob (poll /api/engine-jobs/{id}).
    """
    from services.engine_jobs import start_engine_job
    return start_engine_job(
        "rankings", _run_rankings_job,
        shop_id=shop_id, username=current_user.username,
        audit_entity_id="rankings",
        audit_details=lambda r: (
            f"Rankings-run: {r.get('cis_scores_geschreven', 0)} CIS-scores, "
            f"{r.get('rankings_geschreven', 0)} ranking-rijen"
        ),
    )


# ── NIEUW: Competition Intelligence — trends, events, dekking, kwaliteit ──────

def _canon(name: str | None) -> str | None:
    """Canoniseer een concurrentnaam uit een REST-parameter: een variant-
    schrijfwijze ('WWW.X.nl') resolvet naar dezelfde concurrent ('x.nl')."""
    if not name:
        return name
    from services.domain_normalize import normalize_domain
    return normalize_domain(name) or name


def _scope(db: Session, shop_id: Optional[int]) -> int:
    """Effectieve shop-scope voor competition-endpoints (default shop als geen
    shop_id is meegegeven; 404 bij onbekende shop)."""
    from semantic_layer import _shop_scope
    return _shop_scope(db, shop_id)

def _shop_or_legacy(col, sid: int, db: Session):
    """Shop-filter voor tabellen met legacy-rijen: rijen met shop_id NULL
    stammen van vóór de shop-scoping en horen bij de default shop."""
    from services.competition_settings import default_shop_id
    if sid == default_shop_id(db):
        return or_(col == sid, col.is_(None))
    return col == sid
@router.get("/trends/price-index")
def get_price_index_trend(
    days: int = Query(30, ge=1, le=365),
    competitor: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Dagelijkse trend: gemiddelde prijsindex (eigen/concurrent), volatiliteit
    (variatiecoëfficiënt) en positie (aandeel SKU's waar wij goedkoper zijn).
    Gebruikt de historische eigen prijs per dag (fact_price_daily), zodat
    latere prijswijzigingen de historie niet herschrijven."""
    from statistics import mean, pstdev
    from engine.competition_intelligence import rejected_pairs

    sid = _scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    q = db.query(
        models.FactCompetitorPriceDaily.date,
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
    ).filter(models.FactCompetitorPriceDaily.date >= since,
             models.FactCompetitorPriceDaily.price.isnot(None),
             models.FactCompetitorPriceDaily.shop_id == sid)
    if competitor:
        q = q.filter(models.FactCompetitorPriceDaily.competitor_name == _canon(competitor))
    rows = q.all()

    prods = db.query(models.DimProduct.sku_id, models.DimProduct.current_price,
                     models.DimProduct.category).filter(
        models.DimProduct.shop_id == sid).all()
    current_own = {p.sku_id: float(p.current_price) for p in prods if p.current_price}
    cats = {p.sku_id: p.category for p in prods}
    rejected = rejected_pairs(db)

    # Historische eigen prijzen per (datum, sku)
    own_hist: dict[tuple, float] = {}
    for d, sku, price in db.query(
        models.FactPriceDaily.date, models.FactPriceDaily.sku_id,
        models.FactPriceDaily.price,
    ).filter(models.FactPriceDaily.date >= since,
             models.FactPriceDaily.price.isnot(None),
             models.FactPriceDaily.sku_id.in_(list(cats.keys()) or [""])).all():
        own_hist[(d, sku)] = float(price)

    per_day: dict = {}
    for d, sku, comp, price in rows:
        if (sku, comp) in rejected or float(price) <= 0:
            continue
        if category and cats.get(sku) != category:
            continue
        if sku not in cats:
            continue
        # Historische eigen prijs van die dag; alleen als fallback de huidige
        o = own_hist.get((d, sku)) or current_own.get(sku)
        if not o:
            continue
        per_day.setdefault(d, {"indices": [], "cheaper": 0, "total": 0})
        idx = o / float(price)
        per_day[d]["indices"].append(idx)
        per_day[d]["total"] += 1
        if idx < 1.0:
            per_day[d]["cheaper"] += 1

    series = []
    for d in sorted(per_day):
        v = per_day[d]
        idxs = v["indices"]
        series.append({
            "date": str(d),
            "avg_price_index": round(mean(idxs), 4),
            "volatility": round(pstdev(idxs) / mean(idxs), 4) if len(idxs) > 1 and mean(idxs) > 0 else 0.0,
            "pct_cheaper": round(v["cheaper"] / v["total"] * 100, 1) if v["total"] else None,
            "observations": v["total"],
        })
    return {"days": days, "competitor": competitor, "category": category, "series": series}


@router.get("/trends/coverage")
def get_coverage_trend(
    days: int = Query(90, ge=1, le=365),
    competitor: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Dekkinghistorie per concurrent (category=None → totaal assortiment)."""
    sid = _scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    q = db.query(models.CompetitorCoverageResult).filter(
        models.CompetitorCoverageResult.run_date >= since,
        models.CompetitorCoverageResult.shop_id == sid)
    if competitor:
        q = q.filter(models.CompetitorCoverageResult.competitor_name == _canon(competitor))
    if category:
        q = q.filter(models.CompetitorCoverageResult.category == category)
    else:
        q = q.filter(models.CompetitorCoverageResult.category.is_(None))
    rows = q.order_by(models.CompetitorCoverageResult.run_date).all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.competitor_name, []).append({
            "date": str(r.run_date),
            "own_products": r.own_products,
            "matched_products": r.matched_products,
            "coverage_pct": r.coverage_pct,
        })
    return {"days": days, "category": category, "competitors": out}


@router.get("/coverage")
def get_coverage_latest(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Laatste dekkingsstand per concurrent, totaal + per categorie."""
    sid = _scope(db, shop_id)
    last = db.query(models.CompetitorCoverageResult.run_date).filter(
        models.CompetitorCoverageResult.shop_id == sid).order_by(
        models.CompetitorCoverageResult.run_date.desc()).first()
    if not last:
        return {"run_date": None, "items": []}
    rows = db.query(models.CompetitorCoverageResult).filter(
        models.CompetitorCoverageResult.run_date == last[0],
        models.CompetitorCoverageResult.shop_id == sid).all()
    items = [{
        "competitor_name": r.competitor_name,
        "category": r.category,
        "own_products": r.own_products,
        "matched_products": r.matched_products,
        "coverage_pct": r.coverage_pct,
    } for r in rows]
    return {"run_date": str(last[0]), "items": items}


@router.get("/events")
def list_price_events(
    days: int = Query(30, ge=1, le=365),
    event_type: Optional[str] = Query(None),
    competitor: Optional[str] = Query(None),
    sku_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Gedetecteerde concurrent-events (prijswijzigingen en promo's)."""
    sid = _scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    q = db.query(models.CompetitorPriceEvent).filter(
        models.CompetitorPriceEvent.event_date >= since,
        models.CompetitorPriceEvent.shop_id == sid)
    if event_type:
        q = q.filter(models.CompetitorPriceEvent.event_type == event_type)
    if competitor:
        q = q.filter(models.CompetitorPriceEvent.competitor_name == _canon(competitor))
    if sku_id:
        q = q.filter(models.CompetitorPriceEvent.sku_id == sku_id)
    total = q.count()
    rows = (q.order_by(models.CompetitorPriceEvent.event_date.desc(),
                       models.CompetitorPriceEvent.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    sku_ids = [r.sku_id for r in rows]
    products = {p.sku_id: p.product_name for p in db.query(
        models.DimProduct.sku_id, models.DimProduct.product_name
    ).filter(models.DimProduct.sku_id.in_(sku_ids)).all()}
    return {
        "items": [{
            "id": r.id, "event_date": str(r.event_date), "sku_id": r.sku_id,
            "product_name": products.get(r.sku_id),
            "competitor_name": r.competitor_name, "event_type": r.event_type,
            "old_price": float(r.old_price) if r.old_price is not None else None,
            "new_price": float(r.new_price) if r.new_price is not None else None,
            "change_pct": r.change_pct, "direction": r.direction,
            "promo_depth_pct": r.promo_depth_pct,
            "promo_duration_days": r.promo_duration_days,
        } for r in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/availability")
def get_availability_trend(
    days: int = Query(30, ge=1, le=365),
    competitor: Optional[str] = Query(None),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Dagelijkse beschikbaarheid (voorraad %) en levertijd per concurrent."""
    sid = _scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    q = db.query(models.CompetitorAvailabilityDaily).filter(
        models.CompetitorAvailabilityDaily.date >= since,
        models.CompetitorAvailabilityDaily.shop_id == sid)
    if competitor:
        q = q.filter(models.CompetitorAvailabilityDaily.competitor_name == _canon(competitor))
    rows = q.order_by(models.CompetitorAvailabilityDaily.date).all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.competitor_name, []).append({
            "date": str(r.date), "offers_total": r.offers_total,
            "offers_in_stock": r.offers_in_stock,
            "in_stock_rate": r.in_stock_rate,
            "avg_delivery_days": r.avg_delivery_days,
        })
    return {"days": days, "competitors": out}


@router.get("/match-quality")
def get_match_quality(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """KPI's over de AI-matchkwaliteit + verdachte matches voor review."""
    from sqlalchemy import func as _f
    sid = _scope(db, shop_id)
    rows = db.query(
        models.AiMatchResult.match_type, models.AiMatchResult.status,
        _f.count(models.AiMatchResult.id), _f.avg(models.AiMatchResult.confidence),
    ).join(models.DimProduct,
           models.DimProduct.sku_id == models.AiMatchResult.own_sku_id
    ).filter(models.DimProduct.shop_id == sid
    ).group_by(models.AiMatchResult.match_type, models.AiMatchResult.status).all()

    by_type: dict[str, dict] = {}
    totals = {"total": 0, "approved": 0, "rejected": 0, "pending": 0}
    for mtype, status, cnt, avg_conf in rows:
        t = by_type.setdefault(mtype or "Onbekend", {
            "total": 0, "approved": 0, "rejected": 0, "pending": 0,
            "avg_confidence": None, "_conf_sum": 0.0})
        t["total"] += cnt
        t["_conf_sum"] += float(avg_conf or 0) * cnt
        key = (status or "PENDING").lower()
        if key in ("approved", "rejected", "pending"):
            t[key] += cnt
            totals[key] += cnt
        totals["total"] += cnt
    for t in by_type.values():
        t["avg_confidence"] = round(t.pop("_conf_sum") / t["total"], 3) if t["total"] else None

    reviewed = totals["approved"] + totals["rejected"]

    # Match-basis: EAN-geverifieerd vs feed-koppeling (itemGroupId).
    # PriceShape-exports op itemGroupId-basis hebben ean_match=False — dat is
    # verwacht gedrag, geen kwaliteitsprobleem.
    ean_matched = 0
    feed_linked = 0
    basis_rows = db.query(
        models.AiMatchResult.ean_match,
        _f.count(models.AiMatchResult.id),
    ).join(models.DimProduct,
           models.DimProduct.sku_id == models.AiMatchResult.own_sku_id
    ).filter(models.DimProduct.shop_id == sid,
             models.AiMatchResult.match_type == "Exact"
    ).group_by(models.AiMatchResult.ean_match).all()
    for is_ean, cnt in basis_rows:
        if is_ean:
            ean_matched += cnt
        else:
            feed_linked += cnt

    # Verdachte matches: hoge confidence maar extreem prijsverschil
    suspect_threshold = competition_intelligence.suspicious_match_threshold_pct(db)
    suspects = (
        db.query(models.AiMatchResult)
        .join(models.DimProduct,
              models.DimProduct.sku_id == models.AiMatchResult.own_sku_id)
        .filter(models.DimProduct.shop_id == sid,
                models.AiMatchResult.status == "PENDING",
                models.AiMatchResult.price_diff_pct.isnot(None))
        .filter((models.AiMatchResult.price_diff_pct > suspect_threshold)
                | (models.AiMatchResult.price_diff_pct < -suspect_threshold))
        .order_by(models.AiMatchResult.confidence.desc())
        .limit(25).all()
    )
    return {
        "totals": {
            **{k: v for k, v in totals.items()},
            "review_rate_pct": round(reviewed / totals["total"] * 100, 1) if totals["total"] else 0.0,
            "approval_rate_pct": round(totals["approved"] / reviewed * 100, 1) if reviewed else None,
        },
        "match_basis": {
            "ean_matched": ean_matched,
            "feed_linked": feed_linked,
            "note": ("Feed-koppeling via itemGroupId is de standaard voor "
                     "PriceShape-exports; 0 EAN-matches is dan verwacht en "
                     "geen kwaliteitsprobleem."),
        },
        "by_match_type": by_type,
        "suspect_matches": [{
            "id": m.id, "own_sku_id": m.own_sku_id,
            "competitor_name": m.competitor_name,
            "match_type": m.match_type, "confidence": m.confidence,
            "own_price": m.own_price, "competitor_price": m.competitor_price,
            "price_diff_pct": m.price_diff_pct,
            "explanation": m.explanation_nl,
        } for m in suspects],
        "suspect_threshold_pct": suspect_threshold,
        "note": (f"Verdachte matches: |prijsverschil| > {suspect_threshold:g}% "
                 "bij status PENDING — kandidaat voor review."),
    }


@router.post("/intelligence/run")
def run_competition_intelligence(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Draai alle competition-intelligence stappen (dekking, events, promo's,
    beschikbaarheid, elasticiteit, profielen).

    Optionele body-parameter:
    - shop_id (int): beperk de run tot één shop (handig voor tests en scheduled runs).
    """
    from engine.competition_intelligence import run_all
    shop_id = payload.get("shop_id") if payload else None
    return {"status": "voltooid", **run_all(db, shop_id=shop_id)}


@router.post("/simulate")
def simulate_scenario(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """Multi-concurrent scenario-simulatie (volg/niet-volg per concurrent)."""
    sku_id = payload.get("sku_id")
    change_pct = payload.get("change_pct")
    if not sku_id or change_pct is None:
        raise HTTPException(400, "sku_id en change_pct zijn verplicht")
    # Via de semantic layer zodat shop-scope + toegangscontrole gelden
    from semantic_layer import simulate_competitor_scenario
    return simulate_competitor_scenario(
        db, current_user, str(sku_id), float(change_pct),
        assume_follow=payload.get("assume_follow"),
        assume_no_follow=payload.get("assume_no_follow"),
        shop_id=payload.get("shop_id"),
    )

@router.put("/settings")
def update_competition_settings(
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Sla competition-instellingen op voor een shop (gevalideerd)."""
    from services import competition_settings as cs
    sid = _scope(db, shop_id)
    try:
        effective = cs.upsert_settings(db, sid, payload, current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"shop_id": sid, "settings": effective}


# ── NIEUW: Concurrentscores — kracht, inkoopmacht & Future Threat (taak #247) ─

_SCORE_RANK_DIMENSIONS = {
    "procurement_power": "procurement_power_score",
    "future_threat": "future_threat_score",
    "business_strength": "business_strength_score",
    "operational_strength": "operational_strength_score",
    "financial_health": "financial_health_score",
}


def _score_row_summary(r) -> dict:
    return {
        "competitor_name": r.competitor_name,
        "run_date": str(r.run_date),
        "company_size_class": r.company_size_class,
        "company_size_confidence": r.company_size_confidence,
        "geographic_scale_class": r.geographic_scale_class,
        "geographic_scale_confidence": r.geographic_scale_confidence,
        "fulfilment_model_class": r.fulfilment_model_class,
        "fulfilment_model_confidence": r.fulfilment_model_confidence,
        "operational_strength_score": r.operational_strength_score,
        "financial_health_score": r.financial_health_score,
        "financial_health_status": r.financial_health_status,
        "financial_data_confidence": r.financial_data_confidence,
        "business_strength_score": r.business_strength_score,
        "procurement_power_score": r.procurement_power_score,
        "future_threat_score": r.future_threat_score,
        "data_completeness_pct": r.data_completeness_pct,
        "model_version": r.model_version,
    }


@router.get("/competitor-scores")
def list_competitor_scores(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Meest recente concurrentscores per concurrent (shop-gescoped).
    Ontbrekende data is 'Unknown' (score null + data completeness), nooit 0."""
    from engine.competitor_scores import latest_scores_by_competitor
    sid = _scope(db, shop_id)
    rows = latest_scores_by_competitor(db, sid)
    return {
        "shop_id": sid,
        "count": len(rows),
        "scores": [_score_row_summary(r) for _, r in sorted(rows.items())],
    }


@router.get("/competitor-scores/rankings")
def get_competitor_score_rankings(
    dimension: str = Query("procurement_power"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Aparte rankings op score-dimensies (o.a. Procurement Power Ranking en
    Future Threat Ranking). Unknown-scores worden niet gerangschikt maar wel
    apart teruggegeven (nooit impliciet als 0 onderaan gezet)."""
    from engine.competitor_scores import latest_scores_by_competitor
    if dimension not in _SCORE_RANK_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Onbekende dimensie '{dimension}'. Kies uit: "
                   f"{', '.join(sorted(_SCORE_RANK_DIMENSIONS))}")
    sid = _scope(db, shop_id)
    attr = _SCORE_RANK_DIMENSIONS[dimension]
    rows = list(latest_scores_by_competitor(db, sid).values())
    known = [r for r in rows if getattr(r, attr) is not None]
    unknown = [r for r in rows if getattr(r, attr) is None]
    known.sort(key=lambda r: float(getattr(r, attr)), reverse=True)
    return {
        "shop_id": sid,
        "dimension": dimension,
        "rankings": [
            {
                "rank": idx,
                "competitor_name": r.competitor_name,
                "score": float(getattr(r, attr)),
                "run_date": str(r.run_date),
                "data_completeness_pct": r.data_completeness_pct,
                "details": (r.details or {}).get(dimension),
            }
            for idx, r in enumerate(known, start=1)
        ],
        "unknown": [
            {
                "competitor_name": r.competitor_name,
                "run_date": str(r.run_date),
                "data_completeness_pct": r.data_completeness_pct,
                "reason": ((r.details or {}).get(dimension) or {}).get("explanation"),
            }
            for r in sorted(unknown, key=lambda x: x.competitor_name)
        ],
    }


@router.post("/competitor-scores/run")
def run_competitor_scores_endpoint(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Herbereken de concurrentscores voor de shop (synchrone run)."""
    from engine.competitor_scores import run_competitor_scores
    sid = _scope(db, shop_id)
    result = run_competitor_scores(db, shop_id=sid)
    return {"shop_id": sid, **result}


@router.get("/competitor-scores/{competitor_name}")
def get_competitor_score_detail(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Volledige uitleg per concurrent: factoren, gewichten, bronnen,
    confidence per score + feature-dependency-gebruik. 404 buiten de shop."""
    sid = _scope(db, shop_id)
    competitor_name = _canon(competitor_name)
    row = (db.query(models.CompetitorScoreResult)
           .filter(models.CompetitorScoreResult.shop_id == sid,
                   models.CompetitorScoreResult.competitor_name == competitor_name)
           .order_by(models.CompetitorScoreResult.run_date.desc())
           .first())
    if row is None:
        raise HTTPException(status_code=404,
                            detail="Geen concurrentscores voor deze concurrent in deze shop")
    return {**_score_row_summary(row), "shop_id": sid, "details": row.details}


# ── NIEUW: Concurrent Landscape — managementmatrix (taak #248) ───────────────

@router.get("/landscape")
def get_competitor_landscape(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Management-bubblematrix: per concurrent Competition Relevance,
    Business Strength en Future Threat, plus company-scale (bubbelgrootte)
    en Competition DNA-rollen (kleur/type). Concurrenten zonder waarde op
    een as worden apart teruggegeven als 'unknown' — nooit als 0 geplot.
    """
    from engine.competitor_scores import latest_scores_by_competitor
    from sqlalchemy import func as _func
    sid = _scope(db, shop_id)

    latest = db.query(_func.max(models.CompetitorRanking.run_date)).filter(
        models.CompetitorRanking.scope == "overall",
        models.CompetitorRanking.shop_id == sid).scalar()
    rankings = {}
    if latest:
        rankings = {r.competitor_name: r for r in
                    db.query(models.CompetitorRanking).filter(
                        models.CompetitorRanking.scope == "overall",
                        models.CompetitorRanking.shop_id == sid,
                        models.CompetitorRanking.run_date == latest).all()}
    scores = latest_scores_by_competitor(db, sid)
    names = sorted(set(rankings) | set(scores))
    roles: dict = {}
    if names:
        for r in db.query(models.CompetitorMarketRole).filter(
                models.CompetitorMarketRole.shop_id == sid,
                models.CompetitorMarketRole.competitor_name.in_(names),
                models.CompetitorMarketRole.valid_to.is_(None)).all():
            roles.setdefault(r.competitor_name, []).append(r.role)

    items = []
    for n in names:
        rk = rankings.get(n)
        sc = scores.get(n)
        items.append({
            "competitor_name": n,
            "competition_relevance_score": (
                round(float(rk.competition_relevance_score), 4)
                if rk and rk.competition_relevance_score is not None else None),
            "business_strength_score": (
                float(sc.business_strength_score)
                if sc and sc.business_strength_score is not None else None),
            "future_threat_score": (
                float(sc.future_threat_score)
                if sc and sc.future_threat_score is not None else None),
            "company_size_class": sc.company_size_class if sc else None,
            "market_roles": sorted(roles.get(n, [])),
            "data_completeness_pct": sc.data_completeness_pct if sc else None,
            "rank": rk.rank if rk else None,
        })
    return {
        "shop_id": sid,
        "run_date": str(latest) if latest else None,
        "items": items,
        "total": len(items),
    }
