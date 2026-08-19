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


def descendant_node_ids(db: Session, node_ids: list[int]) -> set[int]:
    """Alle node-ids onder de selectie (inclusief de nodes zelf), via
    prefix-LIKE op het gematerialiseerde pad."""
    if not node_ids:
        return set()
    N = models.ProductHierarchyNode
    nodes = db.query(N).filter(N.id.in_(node_ids)).all()
    conds = [N.path.like(n.path + "%") for n in nodes if n.path]
    if not conds:
        return set()
    return {r[0] for r in db.query(N.id).filter(or_(*conds)).all()}


def signal_filter_conditions(
    db: Session,
    sku_filter: Optional[set[str]],
    hierarchy_node_ids: Optional[str] = None,
    brands: Optional[str] = None,
):
    """
    SQLAlchemy-condities om IntelligenceSignal-rijen op de globale
    filtercontext te beperken. Regels:
    - SKU-signalen: entity_id moet in de gefilterde SKU-set zitten.
    - Niet-SKU-signalen (categorie/subcategorie): alleen matchen op
      hierarchy_node_id binnen de geselecteerde (sub)boom — en alléén als er
      geen merk-filter actief is, want een merk-selectie is op categorie-
      niveau niet evalueerbaar ("niet geëvalueerd" ≠ "binnen selectie").
    Geeft None terug als er geen filter actief is.
    """
    if sku_filter is None:
        return None
    S = models.IntelligenceSignal
    conds = [(S.entity_type == "sku") & (S.entity_id.in_(list(sku_filter)))]
    if not parse_csv(brands):
        node_set = descendant_node_ids(db, parse_csv_ints(hierarchy_node_ids))
        if node_set:
            conds.append((S.entity_type != "sku") & (S.hierarchy_node_id.in_(list(node_set))))
    return or_(*conds)


def filter_metadata(
    db: Session,
    hierarchy_node_ids: Optional[str] = None,
    brands: Optional[str] = None,
) -> dict:
    """Leesbare metadata over de actieve filtercontext (voor exports)."""
    node_ids = parse_csv_ints(hierarchy_node_ids)
    names: list[str] = []
    if node_ids:
        N = models.ProductHierarchyNode
        rows = db.query(N.id, N.path_names, N.name).filter(N.id.in_(node_ids)).all()
        names = [(r[1] or r[2]) for r in rows]
    brand_list = parse_csv(brands)
    return {
        "filters_actief": bool(node_ids or brand_list),
        "hierarchie_selectie": names,
        "merken": brand_list,
    }


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
