"""
Routes voor interne concurrentie (huismerk vs A-merk) en ISV.
Pad: /api/huismerk-impact/...
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from routes.global_filters import resolve_sku_filter
from models import InternalCompetitionScore, DimProduct, User

router = APIRouter(prefix="/api/huismerk-impact", tags=["huismerk"])

ACTIE_LABELS = {
    "PRIVATE_LABEL_PUSH": "Huismerk actief promoten",
    "PORTFOLIO_MARGIN_OPTIMIZATION": "Portfolio-margeoptimalisatie",
    "TRAFFIC_TO_MARGIN_SWITCH": "Traffic naar hogere marge sturen",
    "PRICE_A_BRAND_COMPETITIVELY": "A-merkprijs competitief aanpassen",
    "HOLD_PRICE_MONITOR": "Prijs handhaven, monitoren",
}


@router.get("/sku/{sku_id}")
def get_sku_huismerk_impact(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ISV en interne concurrentiedata voor een specifieke SKU."""
    product = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not product:
        return {"error": "SKU niet gevonden"}

    scores = (
        db.query(InternalCompetitionScore)
        .filter(
            (InternalCompetitionScore.sku_id == sku_id) |
            (InternalCompetitionScore.paired_sku_id == sku_id)
        )
        .order_by(desc(InternalCompetitionScore.run_date))
        .all()
    )

    if not scores:
        return {
            "sku_id": sku_id,
            "product_naam": product.product_name,
            "data_beschikbaar": False,
        }

    # Meest recente datum
    laatste_datum = scores[0].run_date
    scores = [s for s in scores if s.run_date == laatste_datum]

    paren = []
    for s in scores:
        # Haal partnernaam op
        partner_id = s.paired_sku_id if s.sku_id == sku_id else s.sku_id
        partner = db.query(DimProduct).filter(DimProduct.sku_id == partner_id).first()

        paren.append({
            "a_merk_sku": s.sku_id,
            "huismerk_sku": s.paired_sku_id,
            "partner_naam": partner.product_name if partner else partner_id,
            "is_a_merk": s.sku_id == sku_id,
            "schakelkans": round(float(s.internal_switch_probability or 0), 3),
            "marge_kloof": round(float(s.internal_margin_gap or 0), 4),
            "isv": round(float(s.isv or 0), 4),
            "aanbevolen_actie": s.recommended_internal_action,
            "actie_label": ACTIE_LABELS.get(s.recommended_internal_action or "", s.recommended_internal_action or ""),
            "actie_reden": s.action_reason,
            "a_merk_prijs": float(s.a_brand_price) if s.a_brand_price else None,
            "huismerk_prijs": float(s.private_label_price) if s.private_label_price else None,
            "a_merk_marge_pct": s.a_brand_margin_pct,
            "huismerk_marge_pct": s.private_label_margin_pct,
        })

    hoogste_isv = max((p["isv"] for p in paren), default=0)

    return {
        "sku_id": sku_id,
        "product_naam": product.product_name,
        "merk": product.brand,
        "categorie": product.category,
        "ean": product.ean,
        "oem_code": product.oem_code,
        "is_a_merk": product.is_a_brand,
        "is_huismerk": product.is_private_label,
        "data_beschikbaar": True,
        "run_datum": str(laatste_datum),
        "paren": paren,
        "hoogste_isv": round(hoogste_isv, 4),
        "primaire_aanbeveling": paren[0]["aanbevolen_actie"] if paren else None,
    }


@router.get("/overzicht")
def get_huismerk_overzicht(
    min_isv: float = Query(0.0),
    actie: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overzichtstabel van A-merk/huismerk-paren gesorteerd op ISV."""
    q = (
        db.query(InternalCompetitionScore)
        .order_by(desc(InternalCompetitionScore.run_date), desc(InternalCompetitionScore.isv))
    )
    if actie:
        q = q.filter(InternalCompetitionScore.recommended_internal_action == actie)
    if min_isv > 0:
        q = q.filter(InternalCompetitionScore.isv >= min_isv)
    # Globale filtercontext: neem een paar mee als het A-merk (sku_id) in de set
    # zit — het A-merk is het ankerproduct. None = geen filter; lege set = niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands, statuses, sku_query)
    if _gf is not None:
        q = q.filter(InternalCompetitionScore.sku_id.in_(_gf))

    alle = q.all()

    # Meest recente datum
    if not alle:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    laatste_datum = alle[0].run_date
    alle = [s for s in alle if s.run_date == laatste_datum]

    sku_ids = list({s.sku_id for s in alle} | {s.paired_sku_id for s in alle})
    producten = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.sku_id.in_(sku_ids)).all()}

    items = []
    for s in alle:
        a_prod = producten.get(s.sku_id)
        hl_prod = producten.get(s.paired_sku_id)
        items.append({
            "a_merk_sku": s.sku_id,
            "a_merk_naam": a_prod.product_name if a_prod else s.sku_id,
            "a_merk_ean": a_prod.ean if a_prod else None,
            "a_merk_oem": a_prod.oem_code if a_prod else None,
            "huismerk_sku": s.paired_sku_id,
            "huismerk_naam": hl_prod.product_name if hl_prod else s.paired_sku_id,
            "huismerk_ean": hl_prod.ean if hl_prod else None,
            "huismerk_oem": hl_prod.oem_code if hl_prod else None,
            "categorie": a_prod.category if a_prod else "",
            "schakelkans": round(float(s.internal_switch_probability or 0), 3),
            "marge_kloof": round(float(s.internal_margin_gap or 0), 4),
            "isv": round(float(s.isv or 0), 4),
            "aanbevolen_actie": s.recommended_internal_action,
            "actie_label": ACTIE_LABELS.get(s.recommended_internal_action or "", s.recommended_internal_action or ""),
            "a_merk_prijs": float(s.a_brand_price) if s.a_brand_price else None,
            "huismerk_prijs": float(s.private_label_price) if s.private_label_price else None,
        })

    total = len(items)
    offset = (page - 1) * page_size
    return {
        "items": items[offset: offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
