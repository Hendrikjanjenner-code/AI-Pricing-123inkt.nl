"""
Globale filtercontext (taak #216) — gedeelde query-parameters voor dashboards.

Endpoints die de Global Filter Bar ondersteunen accepteren:
  - hierarchy_node_ids : csv van producthiërarchie-node-ids. Een geselecteerde
    parent telt server-side automatisch alle descendants mee (prefix-LIKE op
    het gematerialiseerde pad).
  - brands             : csv van merknamen (DimProduct.brand).

`resolve_sku_filter` geeft None terug als er geen filter actief is, anders de
set sku_id's die aan alle actieve filters voldoet (lege set = niets matcht).
"""
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models


def parse_csv_ints(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def parse_csv(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def hierarchy_sku_ids(db: Session, node_ids: list[int]) -> set[str]:
    """Alle actieve SKU's onder de nodes, inclusief descendants (server-side)."""
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    nodes = db.query(N).filter(N.id.in_(node_ids)).all()
    conds = [N.path.like(n.path + "%") for n in nodes if n.path]
    if not conds:
        return set()
    all_node_ids = [r[0] for r in db.query(N.id).filter(or_(*conds)).all()]
    rows = (db.query(A.sku_id)
            .filter(A.node_id.in_(all_node_ids), A.status == "active")
            .distinct().all())
    return {r[0] for r in rows}


def resolve_sku_filter(
    db: Session,
    hierarchy_node_ids: Optional[str] = None,
    brands: Optional[str] = None,
) -> Optional[set[str]]:
    """None = geen filter actief; anders de gefilterde sku_id-set."""
    node_ids = parse_csv_ints(hierarchy_node_ids)
    brand_list = parse_csv(brands)
    if not node_ids and not brand_list:
        return None
    result: Optional[set[str]] = None
    if node_ids:
        result = hierarchy_sku_ids(db, node_ids)
    if brand_list:
        P = models.DimProduct
        brand_skus = {r[0] for r in
                      db.query(P.sku_id).filter(P.brand.in_(brand_list)).all()}
        result = brand_skus if result is None else (result & brand_skus)
    return result
