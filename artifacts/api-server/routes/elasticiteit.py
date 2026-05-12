"""
Routes voor prijselasticiteit per SKU.
Pad: /api/elasticiteit/...
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from models import SkuElasticity, DimProduct, User

router = APIRouter(prefix="/api/elasticiteit", tags=["elasticiteit"])

VERTROUWENS_LABELS = {
    "hoog_betrouwbaar": "Hoog betrouwbaar",
    "bruikbaar": "Bruikbaar",
    "laag_betrouwbaar": "Laag betrouwbaar",
}


@router.get("/sku/{sku_id}")
def get_sku_elasticiteit(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elasticiteitsdata voor een specifieke SKU."""
    product = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not product:
        return {"error": "SKU niet gevonden"}

    elast = (
        db.query(SkuElasticity)
        .filter(SkuElasticity.sku_id == sku_id)
        .order_by(desc(SkuElasticity.run_date))
        .first()
    )

    if not elast:
        return {
            "sku_id": sku_id,
            "product_naam": product.product_name,
            "data_beschikbaar": False,
        }

    return {
        "sku_id": sku_id,
        "product_naam": product.product_name,
        "merk": product.brand,
        "categorie": product.category,
        "data_beschikbaar": True,
        "run_datum": str(elast.run_date),
        # Elasticiteitswaarden
        "eigen_prijselasticiteit": elast.own_price_elasticity,
        "kruiselasticiteit": elast.cross_elasticity,
        "competitieve_elasticiteit": elast.competitive_elasticity,
        "interne_substitutie_elasticiteit": elast.internal_substitution_elasticity,
        # Betrouwbaarheid
        "betrouwbaarheidsscore": elast.elasticity_confidence_score,
        "betrouwbaarheidsklasse": elast.confidence_class,
        "betrouwbaarheidslabel": VERTROUWENS_LABELS.get(elast.confidence_class or "", elast.confidence_class or ""),
        # Context
        "pcis_score_gebruikt": elast.pcis_score_used,
        "csrs_score_gebruikt": elast.csrs_score_used,
        "verkoopvolume_30d": elast.sales_volume_30d,
        "prijsvariatie_30d": elast.price_variation_30d,
        # Interpretatie
        "interpretatie": _interpreteer_elasticiteit(
            elast.own_price_elasticity,
            elast.competitive_elasticity,
            elast.internal_substitution_elasticity,
        ),
    }


@router.get("/overzicht")
def get_elasticiteit_overzicht(
    categorie: str = Query(None),
    vertrouwen: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overzichtstabel met elasticiteitsscores voor alle SKU's."""
    q = db.query(SkuElasticity, DimProduct).join(
        DimProduct, DimProduct.sku_id == SkuElasticity.sku_id
    )
    if categorie:
        q = q.filter(DimProduct.category == categorie)
    if vertrouwen:
        q = q.filter(SkuElasticity.confidence_class == vertrouwen)

    # Meest recente run per SKU
    laatste = q.order_by(desc(SkuElasticity.run_date)).all()
    sku_laatste: dict = {}
    for elast, prod in laatste:
        if elast.sku_id not in sku_laatste:
            sku_laatste[elast.sku_id] = (elast, prod)

    items = []
    for sku_id, (elast, prod) in sku_laatste.items():
        items.append({
            "sku_id": sku_id,
            "product_naam": prod.product_name,
            "categorie": prod.category,
            "eigen_prijselasticiteit": elast.own_price_elasticity,
            "competitieve_elasticiteit": elast.competitive_elasticity,
            "interne_substitutie_elasticiteit": elast.internal_substitution_elasticity,
            "betrouwbaarheidsscore": elast.elasticity_confidence_score,
            "betrouwbaarheidsklasse": elast.confidence_class,
            "betrouwbaarheidslabel": VERTROUWENS_LABELS.get(elast.confidence_class or "", ""),
        })

    # Sorteer op eigen prijselasticiteit (meest negatief = meest gevoelig)
    items.sort(key=lambda x: x["eigen_prijselasticiteit"] or 0)

    total = len(items)
    offset = (page - 1) * page_size
    return {
        "items": items[offset: offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _interpreteer_elasticiteit(eigen: float, competitief: float, intern: float) -> dict:
    """Geeft Nederlandse interpretaties voor de UI."""
    resultaat = {}

    if eigen and eigen < -2.0:
        resultaat["eigen"] = "Zeer prijsgevoelig — kleine prijsstijging = groot volumeverlies"
    elif eigen and eigen < -1.0:
        resultaat["eigen"] = "Prijsgevoelig — prijsstijging verlaagt vraag meer dan evenredig"
    elif eigen and eigen < -0.5:
        resultaat["eigen"] = "Matig prijsgevoelig — vraag reageert gematigd op prijswijziging"
    else:
        resultaat["eigen"] = "Weinig prijsgevoelig — vraag stabiel ondanks prijswijziging"

    if competitief and competitief > 1.5:
        resultaat["competitief"] = "Hoge gevoeligheid voor concurrentenprijzen — nauw volgen"
    elif competitief and competitief > 0.8:
        resultaat["competitief"] = "Gemiddelde gevoeligheid voor concurrentenprijzen"
    else:
        resultaat["competitief"] = "Lage gevoeligheid voor concurrentenprijzen"

    if intern and abs(intern) > 1.5:
        resultaat["intern"] = "Hoge substitutiegevoeligheid — overstapmogelijkheid naar huismerk groot"
    elif intern and abs(intern) > 0.5:
        resultaat["intern"] = "Matige substitutiegevoeligheid"
    else:
        resultaat["intern"] = "Lage substitutiegevoeligheid — klant blijft bij A-merk"

    return resultaat
