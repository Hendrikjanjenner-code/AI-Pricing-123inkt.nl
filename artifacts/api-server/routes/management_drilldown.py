"""
Management-drilldown (taak #221): KPI's aggregeerbaar per hiërarchieniveau.

GET /api/management/drilldown           — KPI's per child-node van een node
                                          (of de topniveaus zonder node_id),
                                          met doordrillen via node_id.
GET /api/management/drilldown/shops     — cross-shop vergelijking voor een
                                          node, beperkt tot shops waartoe de
                                          gebruiker geautoriseerd is.

KPI's per node: omzet (YTD), marge (YTD), marge%, #SKU's, open kansen
(pending prijsadviezen) en risico's (actieve high/critical signalen).
Vereist management.view; shop-scoping respecteert UserScope.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import authz
from database import get_db

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/management/drilldown", tags=["management"])

RISK_SEVERITIES = ("high", "critical")


def _descendant_node_ids(db: Session, node: models.ProductHierarchyNode) -> list[int]:
    N = models.ProductHierarchyNode
    if not node.path:
        return [node.id]
    return [r[0] for r in db.query(N.id).filter(N.path.like(node.path + "%")).all()]


def _sku_ids_for_nodes(db: Session, node_ids: list[int]) -> set[str]:
    A = models.ProductHierarchyAssignment
    rows = (db.query(A.sku_id)
            .filter(A.node_id.in_(node_ids), A.status == "active")
            .distinct().all())
    return {r[0] for r in rows}


def _kpis(db: Session, sku_ids: set[str], node_ids: list[int],
          shop_ids: Optional[set[int]]) -> dict:
    """KPI-aggregatie. `shop_ids` is de effectieve shop-scope: None =
    onbeperkt (admin/ongescopede gebruiker), anders alleen deze shops —
    ook zonder expliciete shopkeuze mag een gescopede gebruiker nooit
    cijfers van andermans shops zien."""
    P = models.DimProduct
    R = models.FactPricingRecommendationDaily
    S = models.IntelligenceSignal

    if not sku_ids:
        return {"sku_count": 0, "revenue_ytd": 0.0, "margin_ytd": 0.0,
                "margin_pct": None, "opportunities": 0, "risks": 0}

    pq = db.query(
        func.count(P.sku_id),
        func.coalesce(func.sum(P.omzet_ytd), 0),
        func.coalesce(func.sum(P.marge_ytd), 0),
    ).filter(P.sku_id.in_(sku_ids))
    if shop_ids is not None:
        pq = pq.filter(P.shop_id.in_(shop_ids))
    sku_count, omzet, marge = pq.one()

    oq = db.query(func.count(R.id)).filter(
        R.sku_id.in_(sku_ids), R.approval_status == "pending")
    if shop_ids is not None:
        oq = oq.filter(R.shop_id.in_(shop_ids))
    opportunities = oq.scalar() or 0

    rq = db.query(func.count(S.id)).filter(
        S.status == "active",
        S.severity.in_(RISK_SEVERITIES),
        S.hierarchy_node_id.in_(node_ids))
    if shop_ids is not None:
        rq = rq.filter(S.shop_id.in_(shop_ids))
    risks = rq.scalar() or 0

    omzet = float(omzet or 0)
    marge = float(marge or 0)
    return {
        "sku_count": int(sku_count or 0),
        "revenue_ytd": round(omzet, 2),
        "margin_ytd": round(marge, 2),
        "margin_pct": round(marge / omzet * 100, 1) if omzet else None,
        "opportunities": int(opportunities),
        "risks": int(risks),
    }


def _effective_shop_scope(db: Session, user: models.User,
                          shop_id: Optional[int]) -> Optional[set[int]]:
    """Vertaal (gebruiker, gevraagde shop) naar de effectieve shop-scope.

    - Expliciete shop: 403 buiten de toegestane set, anders {shop_id}.
    - Geen shop gekozen: de toegestane set van de gebruiker (None =
      onbeperkt), zodat gescopede gebruikers nooit cross-shop totalen zien.
    """
    allowed = authz.user_allowed_shop_ids(db, user)
    if shop_id is not None:
        if allowed is not None and shop_id not in allowed:
            raise HTTPException(status_code=403, detail="Geen toegang tot deze shop")
        return {shop_id}
    return set(allowed) if allowed is not None else None


def _node_payload(n: models.ProductHierarchyNode) -> dict:
    return {"id": n.id, "name": n.name, "level": n.level,
            "path": n.path, "path_names": n.path_names}


@router.get("")
def drilldown(
    node_id: Optional[int] = Query(None),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(authz.require_permission("management.view")),
):
    shop_scope = _effective_shop_scope(db, current_user, shop_id)
    N = models.ProductHierarchyNode

    node = None
    breadcrumb: list[dict] = []
    if node_id is not None:
        node = db.query(N).filter(N.id == node_id, N.is_active.is_(True)).first()
        if not node:
            raise HTTPException(status_code=404, detail="Hiërarchie-node niet gevonden")
        # Breadcrumb via het gematerialiseerde pad ("/3/17/244/").
        if node.path:
            ancestor_ids = [int(p) for p in node.path.strip("/").split("/") if p.isdigit()]
            rows = db.query(N).filter(N.id.in_(ancestor_ids)).all()
            by_id = {r.id: r for r in rows}
            breadcrumb = [_node_payload(by_id[i]) for i in ancestor_ids if i in by_id]

    children_q = db.query(N).filter(N.is_active.is_(True))
    if node is not None:
        children_q = children_q.filter(N.parent_id == node.id)
    else:
        children_q = children_q.filter(N.parent_id.is_(None))
    children = children_q.order_by(N.name).all()

    rows = []
    for child in children:
        node_ids = _descendant_node_ids(db, child)
        sku_ids = _sku_ids_for_nodes(db, node_ids)
        rows.append({
            **_node_payload(child),
            "has_children": db.query(N.id).filter(
                N.parent_id == child.id, N.is_active.is_(True)).first() is not None,
            **_kpis(db, sku_ids, node_ids, shop_scope),
        })

    totals = None
    if node is not None:
        node_ids = _descendant_node_ids(db, node)
        totals = _kpis(db, _sku_ids_for_nodes(db, node_ids), node_ids, shop_scope)

    return {
        "node": _node_payload(node) if node else None,
        "breadcrumb": breadcrumb,
        "totals": totals,
        "children": rows,
    }


@router.get("/shops")
def drilldown_shops(
    node_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(authz.require_permission("management.view")),
):
    """Cross-shop vergelijking van dezelfde KPI's, alleen geautoriseerde shops."""
    N = models.ProductHierarchyNode
    node = None
    if node_id is not None:
        node = db.query(N).filter(N.id == node_id, N.is_active.is_(True)).first()
        if not node:
            raise HTTPException(status_code=404, detail="Hiërarchie-node niet gevonden")

    if node is not None:
        node_ids = _descendant_node_ids(db, node)
        sku_ids = _sku_ids_for_nodes(db, node_ids)
    else:
        node_ids = [r[0] for r in db.query(N.id).all()]
        sku_ids = None  # geen hiërarchiefilter: alle producten per shop

    allowed = authz.user_allowed_shop_ids(db, current_user)
    shops_q = db.query(models.DimShop).filter(models.DimShop.active.is_(True))
    if allowed is not None:
        shops_q = shops_q.filter(models.DimShop.id.in_(allowed))
    shops = shops_q.order_by(models.DimShop.name).all()

    P = models.DimProduct
    rows = []
    for shop in shops:
        if sku_ids is None:
            shop_skus = {r[0] for r in db.query(P.sku_id).filter(P.shop_id == shop.id).all()}
        else:
            shop_skus = sku_ids
        rows.append({
            "shop_id": shop.id,
            "shop_code": shop.shop_code,
            "shop_name": shop.name,
            "country": shop.country,
            **_kpis(db, shop_skus, node_ids or [0], {shop.id}),
        })

    return {"node": _node_payload(node) if node else None, "shops": rows}
