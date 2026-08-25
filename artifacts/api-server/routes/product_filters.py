"""
Cascaderende productfilters (taak #301) — /api/product-filters/*.

Vijf afhankelijke gebruikersvelden: Hoofdcategorie → Subcategorie →
Sub-Subcategorie → Sub-Sub-Subcategorie → Product. Elk niveau levert
uitsluitend children van het gekozen bovenliggende niveau; ongeldige
combinaties worden met 422 geweigerd (nooit gemengde data).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth as auth_utils
import authz
import models
from database import get_db
from services import product_scope

router = APIRouter(prefix="/api/product-filters", tags=["product-filters"])


@router.get("/main-categories")
def get_main_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return {"items": product_scope.main_categories(db)}


def _children_endpoint(db: Session, parent_id: int, expected_level: int) -> dict:
    veld = product_scope.LEVEL_LABELS[expected_level - 1]
    parent = product_scope.get_active_node(db, parent_id, veld)
    if parent.level != expected_level:
        raise HTTPException(
            status_code=422,
            detail=f"{veld}: categorie '{parent.name}' hoort niet op dit niveau.")
    return {"items": product_scope.children_of(db, parent)}


@router.get("/subcategories")
def get_subcategories(
    main_category_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return _children_endpoint(db, main_category_id, 1)


@router.get("/sub-subcategories")
def get_sub_subcategories(
    subcategory_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return _children_endpoint(db, subcategory_id, 2)


@router.get("/sub-sub-subcategories")
def get_sub_sub_subcategories(
    sub_subcategory_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return _children_endpoint(db, sub_subcategory_id, 3)


@router.get("/products")
def get_products(
    main_category_id: Optional[int] = Query(None),
    subcategory_id: Optional[int] = Query(None),
    sub_subcategory_id: Optional[int] = Query(None),
    sub_sub_subcategory_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Doorzoekbare productlijst binnen de gekozen (gevalideerde) categorie-
    keten. Altijd server-side gefilterd en gelimiteerd."""
    nodes = product_scope.validate_chain(
        db, [main_category_id, subcategory_id,
             sub_subcategory_id, sub_sub_subcategory_id])
    node = product_scope.deepest_node(nodes)
    allowed = authz.user_allowed_shop_ids(db, current_user)
    return {"items": product_scope.search_products(
        db, node, search, allowed_shop_ids=allowed)}


class ResolveScopeRequest(BaseModel):
    main_category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    sub_subcategory_id: Optional[int] = None
    sub_sub_subcategory_id: Optional[int] = None
    sku_id: Optional[str] = None


@router.post("/resolve-scope")
def post_resolve_scope(
    body: ResolveScopeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Valideer de volledige filtercombinatie; geeft de effectieve scope
    (niveaus, product, diepste node, breadcrumb) terug of een 422 met een
    duidelijke Nederlandse foutmelding."""
    return product_scope.resolve_scope(
        db,
        [body.main_category_id, body.subcategory_id,
         body.sub_subcategory_id, body.sub_sub_subcategory_id],
        body.sku_id,
        allowed_shop_ids=authz.user_allowed_shop_ids(db, current_user),
    )
