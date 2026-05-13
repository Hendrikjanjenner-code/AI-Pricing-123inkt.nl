"""
Dynamische hiërarchische categoriestructuur.
Endpoints voor cascaderende filters: categorie → subcategorie → sub-subcategorie.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/category-hierarchy", tags=["category-hierarchy"])


# ── Hulpfuncties ────────────────────────────────────────────────────────────

def _node(c: models.DimCategoryHierarchy) -> dict:
    return {
        "category_id": c.category_id,
        "category_name": c.category_name,
        "parent_category_id": c.parent_category_id,
        "category_level": c.category_level,
        "active": c.active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/categories")
def get_categories(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """Alle level-1 categorieën (actief)."""
    rows = (
        db.query(models.DimCategoryHierarchy)
        .filter(
            models.DimCategoryHierarchy.category_level == 1,
            models.DimCategoryHierarchy.active == True,
        )
        .order_by(models.DimCategoryHierarchy.category_name)
        .all()
    )
    return [_node(r) for r in rows]


@router.get("/subcategories")
def get_subcategories(
    parent_id: Optional[int] = Query(None, description="ID van de parent-categorie (level 1)"),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """
    Level-2 subcategorieën.
    Wanneer parent_id opgegeven → alleen subcategorieën van die categorie.
    Wanneer geen parent_id → alle subcategorieën.
    """
    q = db.query(models.DimCategoryHierarchy).filter(
        models.DimCategoryHierarchy.category_level == 2,
        models.DimCategoryHierarchy.active == True,
    )
    if parent_id is not None:
        q = q.filter(models.DimCategoryHierarchy.parent_category_id == parent_id)
    rows = q.order_by(models.DimCategoryHierarchy.category_name).all()
    return [_node(r) for r in rows]


@router.get("/sub-subcategories")
def get_sub_subcategories(
    parent_id: Optional[int] = Query(None, description="ID van de parent-subcategorie (level 2)"),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """
    Level-3 sub-subcategorieën.
    Wanneer parent_id opgegeven → alleen sub-subcategorieën van die subcategorie.
    """
    q = db.query(models.DimCategoryHierarchy).filter(
        models.DimCategoryHierarchy.category_level == 3,
        models.DimCategoryHierarchy.active == True,
    )
    if parent_id is not None:
        q = q.filter(models.DimCategoryHierarchy.parent_category_id == parent_id)
    rows = q.order_by(models.DimCategoryHierarchy.category_name).all()
    return [_node(r) for r in rows]


@router.get("/tree")
def get_tree(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """Volledige hiërarchieboom als geneste structuur."""
    all_nodes = (
        db.query(models.DimCategoryHierarchy)
        .filter(models.DimCategoryHierarchy.active == True)
        .order_by(models.DimCategoryHierarchy.category_level, models.DimCategoryHierarchy.category_name)
        .all()
    )

    cats   = {n.category_id: {**_node(n), "children": []} for n in all_nodes if n.category_level == 1}
    subs   = {n.category_id: {**_node(n), "children": []} for n in all_nodes if n.category_level == 2}
    subsubs = [_node(n) for n in all_nodes if n.category_level == 3]

    for ss in subsubs:
        if ss["parent_category_id"] in subs:
            subs[ss["parent_category_id"]]["children"].append(ss)

    for sub in subs.values():
        if sub["parent_category_id"] in cats:
            cats[sub["parent_category_id"]]["children"].append(sub)

    return list(cats.values())


@router.get("/search")
def search_categories(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """Zoek door alle niveaus op naam."""
    results = (
        db.query(models.DimCategoryHierarchy)
        .filter(
            models.DimCategoryHierarchy.active == True,
            models.DimCategoryHierarchy.category_name.ilike(f"%{q}%"),
        )
        .order_by(models.DimCategoryHierarchy.category_level, models.DimCategoryHierarchy.category_name)
        .limit(50)
        .all()
    )
    return [_node(r) for r in results]


@router.get("/filter-options")
def get_filter_options(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """
    Gecombineerde filteropties voor alle 8 filterdimensies:
    categorie, subcategorie, sub-subcategorie, merk,
    huismerk/a-merk types, BCG intern, BCG extern.
    """
    # Merken uit dim_product
    brands = (
        db.query(distinct(models.DimProduct.brand))
        .filter(models.DimProduct.brand != None, models.DimProduct.lifecycle_status == "active")
        .order_by(models.DimProduct.brand)
        .all()
    )

    # BCG klassen
    bcg_intern = []
    bcg_extern = []
    try:
        bcg_intern = (
            db.query(distinct(models.SkuCompetitionScore.internal_bcg_class))
            .filter(models.SkuCompetitionScore.internal_bcg_class != None)
            .order_by(models.SkuCompetitionScore.internal_bcg_class)
            .all()
        )
        bcg_extern = (
            db.query(distinct(models.SkuCompetitionScore.external_bcg_class))
            .filter(models.SkuCompetitionScore.external_bcg_class != None)
            .order_by(models.SkuCompetitionScore.external_bcg_class)
            .all()
        )
    except Exception:
        pass

    return {
        "merken": [b[0] for b in brands if b[0]],
        "bcg_intern": [b[0] for b in bcg_intern if b[0]],
        "bcg_extern": [b[0] for b in bcg_extern if b[0]],
        "merktype_opties": [
            {"value": "huismerk", "label": "Huismerk"},
            {"value": "a_merk", "label": "A-merk"},
            {"value": "overig", "label": "Overig"},
        ],
        "actie_nodig_opties": [
            {"value": "ja", "label": "Actie nodig"},
            {"value": "nee", "label": "Geen actie"},
        ],
    }


# ── CRUD ─────────────────────────────────────────────────────────────────────

class CreateCategoryRequest(BaseModel):
    category_name: str
    parent_category_id: Optional[int] = None
    category_level: int


class UpdateCategoryRequest(BaseModel):
    category_name: Optional[str] = None
    parent_category_id: Optional[int] = None
    active: Optional[bool] = None


@router.post("", status_code=201)
def create_category(
    req: CreateCategoryRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Maak een nieuwe categorie/subcategorie/sub-subcategorie aan."""
    if req.category_level not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="category_level moet 1, 2 of 3 zijn")
    if req.category_level > 1 and req.parent_category_id is None:
        raise HTTPException(status_code=400, detail="parent_category_id is verplicht voor niveau 2 en 3")

    if req.parent_category_id:
        parent = db.query(models.DimCategoryHierarchy).filter(
            models.DimCategoryHierarchy.category_id == req.parent_category_id,
            models.DimCategoryHierarchy.active == True,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent categorie niet gevonden")
        if parent.category_level != req.category_level - 1:
            raise HTTPException(
                status_code=400,
                detail=f"Parent moet niveau {req.category_level - 1} zijn, is {parent.category_level}"
            )

    node = models.DimCategoryHierarchy(
        category_name=req.category_name.strip(),
        parent_category_id=req.parent_category_id,
        category_level=req.category_level,
        active=True,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _node(node)


@router.put("/{category_id}")
def update_category(
    category_id: int,
    req: UpdateCategoryRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Wijzig naam, parent of actief-status van een categorieknoop."""
    node = db.query(models.DimCategoryHierarchy).filter(
        models.DimCategoryHierarchy.category_id == category_id
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Categorie niet gevonden")

    if req.category_name is not None:
        node.category_name = req.category_name.strip()
    if req.parent_category_id is not None:
        node.parent_category_id = req.parent_category_id
    if req.active is not None:
        node.active = req.active

    db.commit()
    db.refresh(node)
    return _node(node)
