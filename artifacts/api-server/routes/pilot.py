"""
Pilot Test Dashboard — Paper_Copy categorie.

GET /api/pilot/paper-copy/summary
Berekent KPI's uit geïmporteerde data voor de Paper_Copy pilotcategorie.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import date, timedelta
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/pilot", tags=["pilot"])

PAPER_CATEGORIES = ["Paper", "Paper_Copy", "Copy Paper", "Papier"]


def _is_paper_sku(product: models.DimProduct) -> bool:
    if not product:
        return False
    cat = (product.category or "").lower()
    subcat = (product.subcategory or "").lower()
    return any(
        p in cat or p in subcat
        for p in ["paper", "papier", "copy", "kopie"]
    )


@router.get("/paper-copy/summary")
def get_pilot_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Pilot KPI's voor de Paper_Copy categorie.

    Retourneert:
    - geimporteerde_skus:        Aantal Paper-SKU's in de database
    - concurrentieprijzen:       Totaal concurrentieprijzen voor Paper-SKU's
    - scrapes_vandaag:           Scrape-resultaten van vandaag
    - laatste_scrape_status:     Status laatste scrape
    - gem_prijsindex:            Gemiddelde eigen prijs / gemiddelde concurrentprijs
    - gem_marge_pct:             Gemiddeld margepercentage (eigen prijzen)
    - huismerk_aandeel_pct:      Percentage private-label SKU's
    - oem_vs_huismerk_prijsgap:  Gemiddeld prijsverschil OEM – huismerk
    - sku_met_prijsrisico:        SKU's waar eigen prijs > alle concurrenten
    - sku_met_huismerkkans:       SKU's waar concurrentprijs A-merk > eigen huismerk
    - top5_concurrenten:         Meeste prijswijzigingen afgelopen 7 dagen
    - categorie_advies:          Tekst op basis van gemiddelde prijsindex
    """
    today = date.today()
    week_ago = today - timedelta(days=7)

    # Alle paper-producten
    alle_producten = db.query(models.DimProduct).all()
    paper_producten = [p for p in alle_producten if _is_paper_sku(p)]
    paper_sku_ids = [p.sku_id for p in paper_producten]

    geimporteerde_skus = len(paper_sku_ids)

    # Concurrentieprijzen voor Paper-SKU's
    concurrentieprijzen = 0
    if paper_sku_ids:
        concurrentieprijzen = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(models.FactCompetitorPriceDaily.sku_id.in_(paper_sku_ids))
            .count()
        )

    # Scrapes vandaag
    scrapes_vandaag = (
        db.query(models.FactScrapeResult)
        .filter(func.date(models.FactScrapeResult.scraped_at) == today)
        .count()
    )
    laatste_scrape = (
        db.query(models.FactScrapeResult)
        .order_by(desc(models.FactScrapeResult.scraped_at))
        .first()
    )

    # Gemiddelde prijsindex
    gem_prijsindex = None
    if paper_sku_ids:
        scores = (
            db.query(models.SkuCompetitionScore)
            .filter(
                models.SkuCompetitionScore.sku_id.in_(paper_sku_ids),
                models.SkuCompetitionScore.price_index.isnot(None),
            )
            .all()
        )
        if scores:
            gem_prijsindex = round(
                sum(s.price_index for s in scores) / len(scores), 4
            )

    # Gemiddelde marge %
    gem_marge_pct = None
    if paper_sku_ids:
        marge_rijen = (
            db.query(models.FactSalesDaily)
            .filter(
                models.FactSalesDaily.sku_id.in_(paper_sku_ids),
                models.FactSalesDaily.date >= week_ago,
                models.FactSalesDaily.margin_pct.isnot(None),
            )
            .all()
        )
        if marge_rijen:
            gem_marge_pct = round(
                sum(r.margin_pct for r in marge_rijen) / len(marge_rijen) * 100, 2
            )

    # Huismerk-aandeel
    huismerken = [p for p in paper_producten if p.is_private_label]
    huismerk_aandeel_pct = (
        round(len(huismerken) / geimporteerde_skus * 100, 1)
        if geimporteerde_skus > 0 else 0.0
    )

    # OEM vs huismerk prijsgap
    oem_vs_huismerk_gap = None
    oem_prijzen = [float(p.current_price) for p in paper_producten
                   if not p.is_private_label and p.current_price]
    hl_prijzen = [float(p.current_price) for p in huismerken if p.current_price]
    if oem_prijzen and hl_prijzen:
        oem_vs_huismerk_gap = round(
            sum(oem_prijzen) / len(oem_prijzen) - sum(hl_prijzen) / len(hl_prijzen), 2
        )

    # SKU's met prijsrisico: eigen prijs > alle concurrenten
    sku_met_prijsrisico: list[dict] = []
    for p in paper_producten:
        if not p.current_price:
            continue
        comp_prijzen = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(
                models.FactCompetitorPriceDaily.sku_id == p.sku_id,
                models.FactCompetitorPriceDaily.date >= week_ago,
            )
            .all()
        )
        if not comp_prijzen:
            continue
        hoogste_comp = max(float(r.price) for r in comp_prijzen if r.price)
        if float(p.current_price) > hoogste_comp:
            sku_met_prijsrisico.append({
                "sku_id": p.sku_id,
                "product_name": p.product_name,
                "eigen_prijs": float(p.current_price),
                "hoogste_concurrent": round(hoogste_comp, 4),
                "verschil_pct": round((float(p.current_price) / hoogste_comp - 1) * 100, 2),
            })

    # SKU's met huismerkkans: concurrentprijs A-merk > eigen huismerk
    sku_met_huismerkkans: list[dict] = []
    for hl in huismerken:
        if not hl.current_price:
            continue
        sub = db.query(models.MapSubstitution).filter(
            models.MapSubstitution.private_label_sku == hl.sku_id
        ).first()
        if not sub:
            continue
        a_merk = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sub.a_brand_sku
        ).first()
        if not a_merk or not a_merk.current_price:
            continue
        comp_a_merk = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(
                models.FactCompetitorPriceDaily.sku_id == a_merk.sku_id,
                models.FactCompetitorPriceDaily.date >= week_ago,
            )
            .all()
        )
        if not comp_a_merk:
            continue
        gem_comp = sum(float(r.price) for r in comp_a_merk if r.price) / len(comp_a_merk)
        if gem_comp > float(hl.current_price):
            sku_met_huismerkkans.append({
                "huismerk_sku": hl.sku_id,
                "huismerk_naam": hl.product_name,
                "huismerk_prijs": float(hl.current_price),
                "a_merk_concurrent_gem": round(gem_comp, 4),
                "gap_pct": round((gem_comp / float(hl.current_price) - 1) * 100, 2),
            })

    # Top 5 concurrenten met meeste prijswijzigingen afgelopen 7 dagen
    top5: list[dict] = []
    if paper_sku_ids:
        rijen_7d = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(
                models.FactCompetitorPriceDaily.sku_id.in_(paper_sku_ids),
                models.FactCompetitorPriceDaily.date >= week_ago,
            )
            .order_by(models.FactCompetitorPriceDaily.competitor_name,
                       models.FactCompetitorPriceDaily.sku_id,
                       models.FactCompetitorPriceDaily.date)
            .all()
        )
        wijzigingen_per_concurrent: dict[str, int] = {}
        vorige: dict[str, float] = {}
        for r in rijen_7d:
            sleutel = f"{r.competitor_name}|{r.sku_id}"
            huidig = float(r.price) if r.price else None
            if huidig and sleutel in vorige and abs(huidig - vorige[sleutel]) / (vorige[sleutel] + 1e-9) > 0.005:
                wijzigingen_per_concurrent[r.competitor_name] = (
                    wijzigingen_per_concurrent.get(r.competitor_name, 0) + 1
                )
            if huidig:
                vorige[sleutel] = huidig

        gesorteerd = sorted(wijzigingen_per_concurrent.items(), key=lambda x: x[1], reverse=True)
        top5 = [{"concurrent": k, "wijzigingen": v} for k, v in gesorteerd[:5]]

    # Categorieadvies
    # price_index = eigen_prijs / marktprijs (competitor avg)
    # <1.0 = eigen prijs LAGER dan markt (wij zijn goedkoper)
    # >1.0 = eigen prijs HOGER dan markt (wij zijn duurder)
    if gem_prijsindex is None:
        advies = "Onvoldoende data — importeer eerst concurrentieprijzen."
    elif gem_prijsindex < 0.97:
        advies = "💡 Prijzen liggen onder markt — kans om marge te verbeteren zonder volume te verliezen."
    elif gem_prijsindex <= 1.01:
        advies = "✓ Prijzen zijn goed gepositioneerd ten opzichte van de markt."
    elif gem_prijsindex <= 1.05:
        advies = "⚠️ Prijzen liggen licht boven markt — monitor wekelijks en overweeg aanpassingen voor prijsgevoelige SKU's."
    else:
        advies = "⚠️ Eigen prijzen liggen significant boven markt. Overweeg prijsverlagingen voor prijsgevoelige SKU's."

    return {
        "geimporteerde_skus": geimporteerde_skus,
        "concurrentieprijzen": concurrentieprijzen,
        "scrapes_vandaag": scrapes_vandaag,
        "laatste_scrape_status": laatste_scrape.scrape_status if laatste_scrape else None,
        "laatste_scrape_tijd": (
            laatste_scrape.scraped_at.isoformat() if laatste_scrape else None
        ),
        "gem_prijsindex": gem_prijsindex,
        "gem_marge_pct": gem_marge_pct,
        "huismerk_aandeel_pct": huismerk_aandeel_pct,
        "oem_vs_huismerk_prijsgap": oem_vs_huismerk_gap,
        "sku_met_prijsrisico": sku_met_prijsrisico,
        "sku_met_huismerkkans": sku_met_huismerkkans,
        "top5_concurrenten": top5,
        "categorie_advies": advies,
        "data_status": {
            "heeft_producten": geimporteerde_skus > 0,
            "heeft_concurrentieprijzen": concurrentieprijzen > 0,
            "heeft_scrapes": scrapes_vandaag > 0,
        },
    }
