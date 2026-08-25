"""
ProductScopeService (taak #301) — cascaderende productfilters.

Vertaalt de vijf gebruikersvelden (Hoofdcategorie → Subcategorie →
Sub-Subcategorie → Sub-Sub-Subcategorie → Product) naar gevalideerde
hiërarchie-scopes op basis van de canonieke producthiërarchie
(ProductHierarchyNode / ProductHierarchyAssignment).

Regels:
- Geen filter = geen scope (None): alle data.
- Elk gekozen niveau moet een direct kind zijn van het niveau erboven;
  ongeldige combinaties (bv. subcategorie onder een andere hoofdcategorie)
  worden geweigerd met een duidelijke Nederlandse foutmelding.
- Het diepst gekozen niveau bepaalt de scope: descendants tellen server-side
  mee via het gematerialiseerde pad (prefix-LIKE, geïndexeerd).
- Ondiepe paden: een tak die eindigt op bv. Sub-Subcategorie heeft gewoon
  geen kinderen op het volgende niveau; het product blijft selecteerbaar
  binnen het bestaande pad (geen fictief niveau nodig).
- Diepere paden (level > 4): niet als apart gebruikersveld getoond; de
  scope van het diepste gebruikersniveau omvat ze via descendants.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models

#: Nederlandse labels per gebruikersniveau (1-based index = hiërarchie-level).
LEVEL_LABELS = ["Hoofdcategorie", "Subcategorie",
                "Sub-Subcategorie", "Sub-Sub-Subcategorie"]
MAX_USER_LEVELS = len(LEVEL_LABELS)
PRODUCT_SEARCH_LIMIT = 50


def _node_dict(n: models.ProductHierarchyNode) -> dict:
    return {"id": n.id, "name": n.name, "level": n.level,
            "path": n.path, "path_names": n.path_names}


def get_active_node(db: Session, node_id: int,
                    veld: str) -> models.ProductHierarchyNode:
    n = db.get(models.ProductHierarchyNode, node_id)
    if n is None or not n.is_active:
        raise HTTPException(status_code=422,
                            detail=f"{veld}: categorie {node_id} bestaat niet (meer).")
    return n


def validate_chain(db: Session, level_ids: list[Optional[int]]
                   ) -> list[models.ProductHierarchyNode]:
    """Valideer de keten Hoofdcategorie→…→Sub-Sub-Subcategorie.

    `level_ids` is een lijst van max 4 optionele node-ids (positie 0 =
    Hoofdcategorie). Retourneert de gevalideerde nodes (ondiepste eerst).
    Regels: geen gaten in de keten; elk niveau is een direct kind van het
    vorige; het level van de node komt overeen met de positie.
    """
    nodes: list[models.ProductHierarchyNode] = []
    seen_gap = False
    for idx, node_id in enumerate(level_ids[:MAX_USER_LEVELS]):
        label = LEVEL_LABELS[idx]
        if node_id is None:
            seen_gap = True
            continue
        if seen_gap:
            raise HTTPException(
                status_code=422,
                detail=f"{label} is gekozen zonder bovenliggend niveau; "
                       "kies eerst de niveaus daarboven.")
        n = get_active_node(db, node_id, label)
        if n.level != idx + 1:
            raise HTTPException(
                status_code=422,
                detail=f"{label}: categorie '{n.name}' hoort niet op dit niveau.")
        if idx == 0:
            if n.parent_id is not None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Hoofdcategorie: '{n.name}' is geen hoofdcategorie.")
        else:
            parent = nodes[-1]
            if n.parent_id != parent.id:
                raise HTTPException(
                    status_code=422,
                    detail=f"{label} '{n.name}' hoort niet bij "
                           f"{LEVEL_LABELS[idx - 1].lower()} '{parent.name}'.")
        nodes.append(n)
    return nodes


def deepest_node(nodes: list[models.ProductHierarchyNode]
                 ) -> Optional[models.ProductHierarchyNode]:
    return nodes[-1] if nodes else None


def children_of(db: Session, parent: models.ProductHierarchyNode) -> list[dict]:
    N = models.ProductHierarchyNode
    rows = (db.query(N)
            .filter(N.parent_id == parent.id, N.is_active.is_(True))
            .order_by(N.name).all())
    return [_node_dict(r) for r in rows]


def main_categories(db: Session) -> list[dict]:
    N = models.ProductHierarchyNode
    rows = (db.query(N)
            .filter(N.level == 1, N.parent_id.is_(None), N.is_active.is_(True))
            .order_by(N.name).all())
    return [_node_dict(r) for r in rows]


def _scope_sku_subquery(db: Session, node: models.ProductHierarchyNode):
    """Subquery met sku_id's onder `node` (inclusief descendants)."""
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    node_sq = (db.query(N.id)
               .filter(N.path.like((node.path or f"/{node.id}/") + "%"))
               .scalar_subquery())
    return (db.query(A.sku_id)
            .filter(A.node_id.in_(node_sq), A.status == "active")
            .scalar_subquery())


def product_label(p: models.DimProduct) -> str:
    return f"SKU {p.sku_id} – {p.product_name}"


def get_scoped_product(db: Session, sku_id: str,
                       allowed_shop_ids: Optional[set[int]]
                       ) -> Optional[models.DimProduct]:
    """Product-lookup binnen de shop-autorisatie van de gebruiker.

    `allowed_shop_ids` volgt de semantiek van authz.user_allowed_shop_ids:
    None = onbeperkt; anders mag alleen een product van een toegestane shop
    worden teruggegeven (nooit productdata van andere winkels lekken).
    """
    p = db.get(models.DimProduct, sku_id)
    if p is None:
        return None
    if allowed_shop_ids is not None and p.shop_id not in allowed_shop_ids:
        return None
    return p


def search_products(db: Session, node: Optional[models.ProductHierarchyNode],
                    search: Optional[str],
                    allowed_shop_ids: Optional[set[int]] = None,
                    limit: int = PRODUCT_SEARCH_LIMIT) -> list[dict]:
    """Doorzoekbare productlijst binnen de (optionele) categoriescope.

    Zoekt op naam, SKU, EAN en OEM-code; altijd server-side gelimiteerd
    zodat er nooit tienduizenden rijen naar de browser gaan. Met een
    shop-beperkte gebruiker (allowed_shop_ids ≠ None) blijven producten
    van andere winkels onzichtbaar.
    """
    P = models.DimProduct
    q = db.query(P)
    if allowed_shop_ids is not None:
        q = q.filter(P.shop_id.in_(allowed_shop_ids))
    if node is not None:
        q = q.filter(P.sku_id.in_(_scope_sku_subquery(db, node)))
    term = (search or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(or_(P.sku_id.ilike(like), P.ean.ilike(like),
                         P.oem_code.ilike(like), P.product_name.ilike(like)))
    rows = q.order_by(P.product_name, P.sku_id).limit(limit).all()
    return [{"sku_id": p.sku_id, "name": p.product_name,
             "label": product_label(p)} for p in rows]


def derive_levels_for_sku(db: Session, sku_id: str) -> list[dict]:
    """Leid de categorieniveaus (max 4) af uit de actieve toewijzing van een
    product; gebruikt voor het automatisch invullen van de dropdowns na een
    directe productkeuze."""
    A = models.ProductHierarchyAssignment
    N = models.ProductHierarchyNode
    assign = (db.query(A)
              .filter(A.sku_id == sku_id, A.status == "active")
              .order_by(A.id.desc()).first())
    if assign is None:
        return []
    node = db.get(N, assign.node_id)
    if node is None or not node.path:
        return []
    ids = [int(part) for part in node.path.strip("/").split("/") if part]
    ids = ids[:MAX_USER_LEVELS]
    rows = db.query(N).filter(N.id.in_(ids)).all()
    by_id = {r.id: r for r in rows}
    return [_node_dict(by_id[i]) for i in ids if i in by_id]


def resolve_scope(db: Session, level_ids: list[Optional[int]],
                  sku_id: Optional[str],
                  allowed_shop_ids: Optional[set[int]] = None) -> dict:
    """Valideer de volledige filtercombinatie en geef de effectieve scope
    terug (voor frontend-sync én Copilot).

    - Bij een gekozen product worden de categorieniveaus afgeleid uit de
      toewijzing; conflicterende opgegeven niveaus worden geweigerd.
    - Zonder product geldt de gevalideerde keten; het diepste niveau bepaalt
      de scope.
    """
    product = None
    derived: list[dict] = []
    if sku_id:
        # Shop-autorisatie: een SKU buiten de toegestane winkels gedraagt
        # zich als onbestaand (geen productnaam/label van andermans shop).
        p = get_scoped_product(db, sku_id, allowed_shop_ids)
        if p is None:
            raise HTTPException(status_code=422,
                                detail=f"Product: SKU {sku_id} bestaat niet.")
        product = {"sku_id": p.sku_id, "name": p.product_name,
                   "label": product_label(p)}
        derived = derive_levels_for_sku(db, sku_id)

    nodes = validate_chain(db, level_ids)

    if product is not None and nodes:
        # Opgegeven keten moet consistent zijn met het gekozen product.
        derived_ids = {d["id"] for d in derived}
        for idx, n in enumerate(nodes):
            if n.id not in derived_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"{LEVEL_LABELS[idx]} '{n.name}' hoort niet bij "
                           f"het gekozen product.")

    levels = derived if product is not None else [_node_dict(n) for n in nodes]
    deepest = levels[-1] if levels else None
    breadcrumb = " > ".join(l["name"] for l in levels)
    if product is not None:
        breadcrumb = f"{breadcrumb} > {product['label']}" if breadcrumb else product["label"]
    return {
        "valid": True,
        "levels": levels,
        "product": product,
        "deepest_node_id": deepest["id"] if deepest else None,
        "breadcrumb": breadcrumb or None,
    }
