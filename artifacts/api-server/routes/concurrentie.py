"""
Routes voor CIS/CSRS/CSS concurrentie-intelligentie per SKU.
Pad: /api/concurrentie/...
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from routes.global_filters import resolve_sku_filter
from models import CompetitorInfluenceScore, DimProduct, FactCompetitorPriceDaily, User
from datetime import date

router = APIRouter(prefix="/api/concurrentie", tags=["concurrentie"])


@router.get("/sku/{sku_id}")
def get_sku_concurrentie(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CIS/CSRS/CSS scores voor alle concurrenten van een SKU."""
    product = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not product:
        return {"error": "SKU niet gevonden"}

    scores = (
        db.query(CompetitorInfluenceScore)
        .filter(CompetitorInfluenceScore.sku_id == sku_id)
        .order_by(desc(CompetitorInfluenceScore.run_date), desc(CompetitorInfluenceScore.cis_score))
        .all()
    )

    # Meest recente run_date
    laatste_datum = scores[0].run_date if scores else None
    if laatste_datum:
        scores = [s for s in scores if s.run_date == laatste_datum]

    # Recentste voorraad/levertijd per concurrent uit de dagelijkse feed-facts
    fact_rows = (
        db.query(FactCompetitorPriceDaily)
        .filter(FactCompetitorPriceDaily.sku_id == sku_id)
        .order_by(
            desc(FactCompetitorPriceDaily.date),
            desc(FactCompetitorPriceDaily.observed_at).nulls_last(),
            desc(FactCompetitorPriceDaily.id),
        )
        .all()
    )
    beschikbaarheid: dict = {}
    for f in fact_rows:
        if f.competitor_name and f.competitor_name not in beschikbaarheid:
            beschikbaarheid[f.competitor_name] = {
                "op_voorraad": f.in_stock,  # True/False/None (None = onbekend)
                "levertijd_dagen": f.delivery_days,
                "waargenomen_op": f.observed_at.isoformat() if f.observed_at else None,
            }

    # Gewogen mediaanreferentieprijs op basis van CIS-gewogen concurrenten.
    # Niet-leverbare concurrenten (op_voorraad=False) tellen niet mee;
    # onbekende voorraad (None) telt wél mee (§task-116).
    # Concurrenten met onwerkbaar lange levertijd (> drempel) tellen evenmin
    # mee; onbekende levertijd (None) telt wél mee (§task-174).
    from services import import_settings as imps
    imp_settings = imps.get_settings(db)

    def _uitsluitingsreden(naam: str):
        besch = beschikbaarheid.get(naam, {})
        if besch.get("op_voorraad") is False:
            return "COMPETITOR_IGNORED_OUT_OF_STOCK"
        if imps.delivery_excluded(imp_settings, besch.get("levertijd_dagen")):
            return "COMPETITOR_IGNORED_BAD_DELIVERY"
        return None

    actieve = [
        s for s in scores
        if s.status == "Actief" and s.competitor_price is not None
        and _uitsluitingsreden(s.competitor_name) is None
    ]
    gewogen_ref = None
    if actieve:
        totaal_gewicht = sum(float(s.competitor_weight or s.cis_score or 0) for s in actieve)
        if totaal_gewicht > 0:
            gewogen_ref = round(
                sum(float(s.competitor_price) * float(s.competitor_weight or s.cis_score or 0) for s in actieve)
                / totaal_gewicht,
                4
            )

    concurrenten = []
    for s in scores:
        besch = beschikbaarheid.get(s.competitor_name, {})
        reden = _uitsluitingsreden(s.competitor_name)
        uitgesloten = reden is not None
        concurrenten.append({
            "id": s.id,
            "concurrent": s.competitor_name,
            "concurrentielaag": s.competition_layer,
            "cis_score": round(float(s.cis_score or 0), 3),
            "csrs_score": round(float(s.csrs_score or 0), 3),
            "css_score": round(float(s.css_score or 0), 3),
            "cis_klasse": s.cis_class,
            "status": s.status,
            "reden_code": s.reason_code,
            "prijsactie": s.pricing_action,
            "concurrent_prijs": float(s.competitor_price) if s.competitor_price else None,
            "prijs_vs_eigen_pct": s.price_vs_own_pct,
            "concurrent_gewicht": round(float(s.competitor_weight or 0), 3),
            # Voorraad & levertijd uit de meest recente feed-waarneming
            "op_voorraad": besch.get("op_voorraad"),
            # Uitsluiting van de gewogen referentieprijs
            "uitgesloten_van_referentie": uitgesloten,
            "uitsluitingsreden": reden,
            "levertijd_dagen": besch.get("levertijd_dagen"),
            "waargenomen_op": besch.get("waargenomen_op"),
            # CSRS sub-scores
            "beschikbaarheidsscore": s.availability_rate,
            "levertijdscore": s.delivery_speed_score,
            "voorraadstabiliteit": s.stock_stability_score,
            "lijstconsistentie": s.listing_consistency_score,
            # CSS sub-scores
            "prijsafwijkingsscore": s.price_deviation_score,
            "prijsvolatiliteit": s.price_volatility_score,
            "concurrent_type_score": s.competitor_type_score,
            "leverbetrouwbaarheid": s.delivery_reliability_score,
        })

    return {
        "sku_id": sku_id,
        "product_naam": product.product_name,
        "merk": product.brand,
        "categorie": product.category,
        "eigen_prijs": float(product.current_price) if product.current_price else None,
        "gewogen_referentieprijs": gewogen_ref,
        "run_datum": str(laatste_datum) if laatste_datum else None,
        "concurrenten": concurrenten,
        "samenvatting": {
            "totaal": len(scores),
            "actief": len([s for s in scores if s.status == "Actief"]),
            "monitoren": len([s for s in scores if s.status == "Monitoren"]),
            "negeren": len([s for s in scores if s.status == "Negeren"]),
            "primaire": len([s for s in scores if s.cis_class == "Primaire concurrent"]),
            "sterke": len([s for s in scores if s.cis_class == "Sterke concurrent"]),
        }
    }


@router.get("/overzicht")
def get_concurrentie_overzicht(
    categorie: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overzicht van SKU's met CIS-scores — tabel voor de concurrentie-analyse pagina."""
    # Haal meest recente datum op
    laatste = db.query(CompetitorInfluenceScore.run_date).order_by(desc(CompetitorInfluenceScore.run_date)).first()
    if not laatste:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    q = (
        db.query(CompetitorInfluenceScore)
        .filter(CompetitorInfluenceScore.run_date == laatste[0])
    )
    if categorie:
        q = q.join(DimProduct, DimProduct.sku_id == CompetitorInfluenceScore.sku_id)
        q = q.filter(DimProduct.category == categorie)
    if status:
        q = q.filter(CompetitorInfluenceScore.status == status)
    # Globale filtercontext: doorsnede met categorie-filter. Lege set = niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands)
    if _gf is not None:
        q = q.filter(CompetitorInfluenceScore.sku_id.in_(_gf))

    scores = q.order_by(desc(CompetitorInfluenceScore.cis_score)).all()

    # Groepeer per SKU — neem de hoogste CIS per SKU
    sku_map: dict = {}
    for s in scores:
        if s.sku_id not in sku_map or float(s.cis_score or 0) > float(sku_map[s.sku_id].cis_score or 0):
            sku_map[s.sku_id] = s

    sku_ids = list(sku_map.keys())
    producten = {p.sku_id: p for p in db.query(DimProduct).filter(DimProduct.sku_id.in_(sku_ids)).all()}

    items = []
    for sku_id, s in sku_map.items():
        prod = producten.get(sku_id)
        items.append({
            "sku_id": sku_id,
            "product_naam": prod.product_name if prod else sku_id,
            "categorie": prod.category if prod else "",
            "eigen_prijs": float(prod.current_price) if prod and prod.current_price else None,
            "max_cis": round(float(s.cis_score or 0), 3),
            "cis_klasse": s.cis_class,
            "status": s.status,
            "primaire_concurrent": s.competitor_name if s.cis_class == "Primaire concurrent" else None,
        })

    total = len(items)
    offset = (page - 1) * page_size
    return {
        "items": items[offset: offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
