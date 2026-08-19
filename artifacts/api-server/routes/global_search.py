"""
Platformbrede zoekfunctie (taak #221).

GET /api/search?q=... zoekt over SKU's, productcodes (OEM), EAN's,
productnamen, hiërarchie-nodes, categorieën, merken, leveranciers en
concurrenten. Resultaten worden gefilterd op de effectieve permissies
van de gebruiker:
  - producten / hiërarchie / categorieën / merken : data.view, catman.view
    of pricing.view (één van deze volstaat);
  - leveranciers  : supplier.view;
  - concurrenten  : competition.view.
Admins zien alles. De frontend bepaalt de navigatie per resultaattype.
"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import auth as auth_utils
import authz
from database import get_db

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/search", tags=["search"])

PRODUCT_PERMS = {"data.view", "catman.view", "pricing.view"}


def _hit(type_: str, id_, label: str, sublabel: str | None = None, extra: dict | None = None):
    d = {"type": type_, "id": id_, "label": label, "sublabel": sublabel}
    if extra:
        d.update(extra)
    return d


@router.get("")
def global_search(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(8, ge=1, le=25),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Gegroepeerde zoekresultaten, permission-gefilterd."""
    term = q.strip()
    like = f"%{term}%"
    perms = authz.effective_permissions(db, current_user)
    is_admin = current_user.role == "admin"
    # Shop-scope: None = onbeperkt; anders alleen data van deze shops.
    allowed_shops = authz.user_allowed_shop_ids(db, current_user)

    def shop_scoped(query, shop_col):
        if allowed_shops is not None:
            return query.filter(shop_col.in_(allowed_shops))
        return query

    def allowed(*codes: str) -> bool:
        return is_admin or any(c in perms for c in codes)

    groups: dict[str, list[dict]] = {}

    if allowed(*PRODUCT_PERMS):
        P = models.DimProduct
        prods = (shop_scoped(db.query(P), P.shop_id)
                 .filter(or_(P.sku_id.ilike(like),
                             P.product_name.ilike(like),
                             P.oem_code.ilike(like),
                             P.ean.ilike(like)))
                 .order_by(P.product_name)
                 .limit(limit).all())
        groups["products"] = [
            _hit("product", p.sku_id, p.product_name or p.sku_id,
                 " · ".join(x for x in [p.sku_id, p.brand, p.ean] if x))
            for p in prods
        ]

        N = models.ProductHierarchyNode
        nodes = (db.query(N)
                 .filter(N.is_active.is_(True), N.name.ilike(like))
                 .order_by(N.level, N.name)
                 .limit(limit).all())
        groups["hierarchy_nodes"] = [
            _hit("hierarchy_node", n.id, n.name, n.path_names,
                 {"path": n.path, "level": n.level})
            for n in nodes
        ]

        cats = (shop_scoped(db.query(P.category), P.shop_id)
                .filter(P.category.isnot(None), P.category.ilike(like))
                .distinct().order_by(P.category).limit(limit).all())
        groups["categories"] = [_hit("category", c[0], c[0]) for c in cats]

        brands = (shop_scoped(db.query(P.brand), P.shop_id)
                  .filter(P.brand.isnot(None), P.brand.ilike(like))
                  .distinct().order_by(P.brand).limit(limit).all())
        groups["brands"] = [_hit("brand", b[0], b[0]) for b in brands]

    if allowed("supplier.view"):
        S = models.FactSupplierData
        P = models.DimProduct
        sq = (db.query(S.supplier_id, S.supplier_name)
              .filter(S.supplier_name.ilike(like)))
        if allowed_shops is not None:
            # Leveranciersdata heeft geen eigen shop-kolom; scope via de
            # gekoppelde producten van de toegestane shops.
            sq = (sq.join(P, P.sku_id == S.sku_id)
                  .filter(P.shop_id.in_(allowed_shops)))
        sups = sq.distinct().order_by(S.supplier_name).limit(limit).all()
        groups["suppliers"] = [
            _hit("supplier", s.supplier_id, s.supplier_name) for s in sups
        ]

    if allowed("competition.view"):
        C = models.DimCompetitor
        comps = (db.query(C)
                 .filter(C.active.is_(True), C.competitor_name.ilike(like))
                 .order_by(C.competitor_name).limit(limit).all())
        groups["competitors"] = [
            _hit("competitor", c.competitor_id, c.competitor_name, c.base_url)
            for c in comps
        ]

    total = sum(len(v) for v in groups.values())
    return {"query": term, "total": total, "groups": groups}
