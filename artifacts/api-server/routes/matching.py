"""
Product Matching routes — /api/matching/...
Koppelt concurrent-producten aan eigen SKU's.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from models import ProductMatch, DimCompetitor, DimProduct, FactScrapeResult, User
from datetime import datetime

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.get("/suggestions")
def get_match_suggestions(
    status: str = Query(None),  # pending / goedgekeurd / afgewezen
    min_confidence: float = Query(0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal match-voorstellen op, gesorteerd op confidence."""
    q = db.query(ProductMatch)
    if status == "pending":
        q = q.filter(ProductMatch.approved_by.is_(None), ProductMatch.active == True)
    elif status == "goedgekeurd":
        q = q.filter(ProductMatch.approved_by.isnot(None), ProductMatch.active == True)
    elif status == "afgewezen":
        q = q.filter(ProductMatch.active == False)
    if min_confidence:
        q = q.filter(ProductMatch.match_confidence >= min_confidence)

    q = q.order_by(desc(ProductMatch.match_confidence))
    totaal = q.count()
    matches = q.offset((page - 1) * page_size).limit(page_size).all()

    concurrenten = {c.competitor_id: c.competitor_name for c in db.query(DimCompetitor).all()}
    producten_obj = {p.sku_id: p for p in db.query(DimProduct).all()}
    producten = {sku: p.product_name for sku, p in producten_obj.items()}

    return {
        "items": [
            {
                "match_id": m.match_id,
                "own_sku_id": m.own_sku_id,
                "product_naam": producten.get(m.own_sku_id, m.own_sku_id),
                "ean": producten_obj.get(m.own_sku_id).ean if producten_obj.get(m.own_sku_id) else None,
                "oem_code": producten_obj.get(m.own_sku_id).oem_code if producten_obj.get(m.own_sku_id) else None,
                "concurrent": concurrenten.get(m.competitor_id, str(m.competitor_id)),
                "competitor_sku": m.competitor_sku,
                "competitor_url": m.competitor_url,
                "match_type": m.match_type,
                "match_confidence": m.match_confidence,
                "match_reason": m.match_reason,
                "pack_size_warning": m.pack_size_warning,
                "manual_override": m.manual_override,
                "approved_by": m.approved_by,
                "approved_at": str(m.approved_at) if m.approved_at else None,
                "active": m.active,
            }
            for m in matches
        ],
        "totaal": totaal,
        "page": page,
        "page_size": page_size,
    }


@router.post("/run")
def run_matching(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Voer automatische matching uit tussen scrape-resultaten en eigen SKU's.
    Genereert match-voorstellen in product_match.
    """
    if current_user.role not in ("admin", "pricing_manager", "analyst"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.matching_engine import match_competitor_offer_to_sku

    # Haal onverwerkte scrape-resultaten op
    verwerkt = {m.competitor_sku for m in db.query(ProductMatch).filter(ProductMatch.active == True).all()}
    scrapes = (
        db.query(FactScrapeResult)
        .filter(FactScrapeResult.scrape_status == "SCRAPE_SUCCESS")
        .limit(200)
        .all()
    )
    producten = db.query(DimProduct).all()

    nieuw = 0
    for scrape in scrapes:
        if scrape.ean and scrape.ean in verwerkt:
            continue
        comp_offer = {
            "scrape_id": scrape.scrape_id,
            "competitor_sku": scrape.ean or str(scrape.scrape_id),
            "product_title": scrape.product_title,
            "brand": scrape.brand,
            "ean": scrape.ean,
            "mpn": scrape.mpn,
            "pack_size": scrape.pack_size,
        }
        for product in producten:
            own = {
                "sku_id": product.sku_id,
                "product_name": product.product_name,
                "brand": product.brand,
                "category": product.category,
            }
            resultaat = match_competitor_offer_to_sku(own, comp_offer)
            if resultaat["match_confidence"] > 0.35:
                bestaand = db.query(ProductMatch).filter(
                    ProductMatch.own_sku_id == product.sku_id,
                    ProductMatch.competitor_sku == comp_offer["competitor_sku"],
                ).first()
                if not bestaand:
                    match = ProductMatch(
                        own_sku_id=product.sku_id,
                        competitor_id=scrape.competitor_id,
                        competitor_sku=comp_offer["competitor_sku"],
                        competitor_url=scrape.product_url,
                        match_type=resultaat["match_type"],
                        match_confidence=resultaat["match_confidence"],
                        match_reason=resultaat["match_reason"],
                        pack_size_warning=resultaat["pack_size_warning"],
                        active=True,
                    )
                    db.add(match)
                    nieuw += 1
    db.commit()
    return {"status": "uitgevoerd", "nieuwe_voorstellen": nieuw}


@router.post("/approve")
def approve_match(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Keur een match-voorstel goed."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    match_id = payload.get("match_id")
    match = db.query(ProductMatch).filter(ProductMatch.match_id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match niet gevonden")

    match.approved_by = current_user.username
    match.approved_at = datetime.utcnow()
    match.active = True
    db.commit()
    return {"status": "goedgekeurd", "match_id": match_id}


@router.post("/reject")
def reject_match(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wijs een match-voorstel af."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    match_id = payload.get("match_id")
    match = db.query(ProductMatch).filter(ProductMatch.match_id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match niet gevonden")

    match.active = False
    match.match_reason = (match.match_reason or "") + " | AFGEWEZEN"
    db.commit()
    return {"status": "afgewezen", "match_id": match_id}


@router.post("/manual")
def create_manual_match(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Maak een handmatige koppeling aan tussen eigen SKU en concurrent."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    from services.matching_engine import create_manual_match_override
    resultaat = create_manual_match_override(
        db=db,
        own_sku_id=payload.get("own_sku_id", ""),
        competitor_id=payload.get("competitor_id", 0),
        competitor_sku=payload.get("competitor_sku", ""),
        competitor_url=payload.get("competitor_url", ""),
        approved_by=current_user.username,
    )
    return resultaat
