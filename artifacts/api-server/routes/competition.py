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
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/competition", tags=["competition"])


# ── Bestaande: Summary ────────────────────────────────────────────────────────

@router.get("/summary")
def get_competition_summary(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    scores = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id.in_(shop_sku_ids)
    ).all()
    if not scores:
        return {
            "total_skus_scored": 0, "avg_pcis": 0,
            "critical_count": 0, "strong_count": 0,
            "influence_count": 0, "monitor_count": 0, "ignore_count": 0,
            "avg_price_index": 1.0, "total_competitors_excluded": 0,
            "downward_pressure_count": 0, "upward_opportunity_count": 0,
        }

    avg_pcis = sum(s.pcis_score or 0 for s in scores) / len(scores)
    class_counts: dict = {}
    for s in scores:
        c = s.competition_class or "Ignore"
        class_counts[c] = class_counts.get(c, 0) + 1

    price_indexed = [s for s in scores if s.price_index is not None]
    avg_pi = sum(s.price_index for s in price_indexed) / len(price_indexed) if price_indexed else 1.0
    total_excluded = sum(s.competitors_excluded or 0 for s in scores)
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Begrens tot SKU's van deze shop
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    q = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id.in_(shop_sku_ids)
    )
    if competition_class:
        q = q.filter(models.SkuCompetitionScore.competition_class == competition_class)
    if category:
        sku_ids = [
            p.sku_id
            for p in db.query(models.DimProduct).filter(
                models.DimProduct.category == category,
                models.DimProduct.shop_id == sid,
            ).all()
        ]
        q = q.filter(models.SkuCompetitionScore.sku_id.in_(sku_ids))

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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    score = (
        db.query(models.SkuCompetitionScore)
        .filter(models.SkuCompetitionScore.sku_id == sku_id)
        .order_by(models.SkuCompetitionScore.run_date.desc())
        .first()
    )
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()

    recent_date = date.today() - timedelta(days=14)
    comp_prices = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(
            models.FactCompetitorPriceDaily.sku_id == sku_id,
            models.FactCompetitorPriceDaily.date >= recent_date,
        )
        .order_by(models.FactCompetitorPriceDaily.date.desc())
        .all()
    )

    seen: set = set()
    competitor_detail = []
    ref_price = float(score.reference_price) if score and score.reference_price else None
    for c in comp_prices:
        if c.competitor_name not in seen:
            seen.add(c.competitor_name)
            price = float(c.price) if c.price else None
            is_excluded = False
            exclusion_reason = None
            if ref_price and price:
                deviation = abs(price - ref_price) / (ref_price + 0.001)
                if deviation > 0.30:
                    is_excluded = True
                    exclusion_reason = "COMPETITOR_IGNORED_OUTLIER"
            competitor_detail.append({
                "competitor_name": c.competitor_name,
                "price": price,
                "date": c.date.isoformat() if c.date else None,
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    return [
        {
            "class": cls,
            "count": db.query(models.SkuCompetitionScore).filter(
                models.SkuCompetitionScore.competition_class == cls,
                models.SkuCompetitionScore.sku_id.in_(shop_sku_ids),
            ).count(),
        }
        for cls in classes
    ]


@router.get("/charts/price-index-by-category")
def get_price_index_by_category(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_sku_ids = {r.sku_id for r in
                   db.query(models.DimProduct.sku_id)
                   .filter(models.DimProduct.shop_id == sid).all()}
    scores = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.price_index.isnot(None),
        models.SkuCompetitionScore.sku_id.in_(shop_sku_ids),
    ).all()
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    result = []
    for cls in classes:
        rows = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.competition_class == cls,
            models.SkuCompetitionScore.sku_id.in_(shop_sku_ids),
        ).all()
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Top-10 concurrenten per categorie met alle 7 scores, verkeerslicht,
    strategie-label en laatste prijswijziging — shop-gefilterd.
    """
    sid = _scope(db, shop_id)
    q = db.query(models.CategoryCompetitorRelevance).filter(
        models.CategoryCompetitorRelevance.shop_id == sid
    )
    if category:
        q = q.filter(models.CategoryCompetitorRelevance.category == category)
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.CompetitorDiscoveryQueue)
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
    min_confidence: float = Query(0.60, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Start een nieuwe discovery-run (synchronous voor de pilot)."""
    from engine.competitor_discovery import run_discovery
    result = run_discovery(db, categories=categories, min_confidence=min_confidence)
    return {"status": "completed", **result}


@router.post("/discovery/{item_id}/approve")
def approve_discovery_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    item = db.query(models.CompetitorDiscoveryQueue).filter(
        models.CompetitorDiscoveryQueue.id == item_id
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    item = db.query(models.CompetitorDiscoveryQueue).filter(
        models.CompetitorDiscoveryQueue.id == item_id
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    q = db.query(models.CompetitorProfile).filter(
        models.CompetitorProfile.shop_id == sid
    )
    if relevance_label:
        q = q.filter(models.CompetitorProfile.relevance_label == relevance_label)
    total = q.count()
    items = (
        q.order_by(models.CompetitorProfile.functional_overlap_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_profile_out(p) for p in items],
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
        "profile": _profile_out(profile),
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    # Begrens tot SKU's van deze shop via DimProduct (AiMatchResult heeft geen shop_id)
    shop_sku_ids = [r.sku_id for r in
                    db.query(models.DimProduct.sku_id)
                    .filter(models.DimProduct.shop_id == sid).all()]
    q = db.query(models.AiMatchResult).filter(
        models.AiMatchResult.own_sku_id.in_(shop_sku_ids)
    )
    if match_type:
        q = q.filter(models.AiMatchResult.match_type == match_type)
    if min_confidence > 0:
        q = q.filter(models.AiMatchResult.confidence >= min_confidence)
    if status:
        q = q.filter(models.AiMatchResult.status == status)
    if sku_id:
        q = q.filter(models.AiMatchResult.own_sku_id == sku_id)

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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    total = db.query(models.CompetitorDiscoveryRun).count()
    items = (
        db.query(models.CompetitorDiscoveryRun)
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

@router.get("/rankings")
def get_competitor_rankings(
    scope: str = Query("overall"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Concurrentrankings met de drie gestandaardiseerde scores (§9):
    Competition Relevance, Price Relevance en Influence — plus rank,
    vorige rank en trend (§11).
    """
    from sqlalchemy import func as _func
    sid = _scope(db, shop_id)
    latest = db.query(_func.max(models.CompetitorRanking.run_date)).filter(
        models.CompetitorRanking.scope == scope,
        models.CompetitorRanking.shop_id == sid,
    ).scalar()
    if not latest:
        return {"scope": scope, "run_date": None, "rankings": [],
                "scopes": _ranking_scopes(db, sid)}

    rows = (
        db.query(models.CompetitorRanking)
        .filter(models.CompetitorRanking.scope == scope,
                models.CompetitorRanking.run_date == latest,
                models.CompetitorRanking.shop_id == sid)
        .order_by(models.CompetitorRanking.rank)
        .all()
    )
    return {
        "scope": scope,
        "run_date": str(latest),
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


def _ranking_scopes(db: Session, shop_id: Optional[int] = None) -> list[str]:
    q = db.query(models.CompetitorRanking.scope).distinct()
    if shop_id is not None:
        q = q.filter(models.CompetitorRanking.shop_id == shop_id)
    scopes = [s[0] for s in q.all()]
    return sorted(scopes, key=lambda s: (s != "overall", s))


@router.post("/rankings/run")
def run_rankings(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    Herbereken de competitor rankings (drie-scoremodel §9-§11).

    Stap 1: bereken CIS-scores per SKU/concurrent uit de prijshistorie en
            schrijf ze naar competitor_influence_scores.
    Stap 2: bereken rankings die de CIS-scores als Influence-component lezen.

    shop_id (optioneel in body): beperk de run tot één shop (sneller bij tests/gefocuste runs).
    """
    from engine.competitor_influence import run_cis_engine
    from engine.competition_rankings import run_competitor_rankings
    shop_id: Optional[int] = payload.get("shop_id")
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


# ── NIEUW: Competition Intelligence — trends, events, dekking, kwaliteit ──────

def _scope(db: Session, shop_id: Optional[int]) -> int:
    """Effectieve shop-scope voor competition-endpoints (default shop als geen
    shop_id is meegegeven; 404 bij onbekende shop)."""
    from semantic_layer import _shop_scope
    return _shop_scope(db, shop_id)


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
        q = q.filter(models.FactCompetitorPriceDaily.competitor_name == competitor)
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
        q = q.filter(models.CompetitorCoverageResult.competitor_name == competitor)
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
        q = q.filter(models.CompetitorPriceEvent.competitor_name == competitor)
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
        q = q.filter(models.CompetitorAvailabilityDaily.competitor_name == competitor)
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
    # Verdachte matches: hoge confidence maar extreem prijsverschil
    suspects = (
        db.query(models.AiMatchResult)
        .join(models.DimProduct,
              models.DimProduct.sku_id == models.AiMatchResult.own_sku_id)
        .filter(models.DimProduct.shop_id == sid,
                models.AiMatchResult.status == "PENDING",
                models.AiMatchResult.price_diff_pct.isnot(None))
        .filter((models.AiMatchResult.price_diff_pct > 40)
                | (models.AiMatchResult.price_diff_pct < -40))
        .order_by(models.AiMatchResult.confidence.desc())
        .limit(25).all()
    )
    return {
        "totals": {
            **{k: v for k, v in totals.items()},
            "review_rate_pct": round(reviewed / totals["total"] * 100, 1) if totals["total"] else 0.0,
            "approval_rate_pct": round(totals["approved"] / reviewed * 100, 1) if reviewed else None,
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
        "note": "Verdachte matches: |prijsverschil| > 40% bij status PENDING — kandidaat voor review.",
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
