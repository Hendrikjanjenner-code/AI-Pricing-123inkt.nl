"""
Scraping routes — /api/scraping/...
Beheer van concurrent-configuraties en scrape-resultaten.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import get_current_user
from models import (
    DimCompetitor, CompetitorScrapeConfig, FactScrapeResult, User
)
from datetime import datetime

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


@router.get("/configs")
def get_scraping_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal alle concurrent-configuraties op."""
    concurrenten = db.query(DimCompetitor).filter(DimCompetitor.active == True).all()
    resultaat = []
    for c in concurrenten:
        configs = (
            db.query(CompetitorScrapeConfig)
            .filter(CompetitorScrapeConfig.competitor_id == c.competitor_id)
            .all()
        )
        # Laatste scrape
        laatste = (
            db.query(FactScrapeResult)
            .filter(FactScrapeResult.competitor_id == c.competitor_id)
            .order_by(desc(FactScrapeResult.scraped_at))
            .first()
        )
        resultaat.append({
            "competitor_id": c.competitor_id,
            "competitor_name": c.competitor_name,
            "base_url": c.base_url,
            "competitor_type": c.competitor_type,
            "default_relevance_score": c.default_relevance_score,
            "scraping_enabled": c.scraping_enabled,
            "active": c.active,
            "configs_count": len(configs),
            "laatste_scrape": str(laatste.scraped_at) if laatste else None,
            "laatste_status": laatste.scrape_status if laatste else None,
            "configs": [
                {
                    "config_id": cfg.config_id,
                    "page_type": cfg.page_type,
                    "url_pattern": cfg.url_pattern,
                    "scrape_method": cfg.scrape_method,
                    "requests_per_minute": cfg.requests_per_minute,
                    "title_selector": cfg.title_selector,
                    "price_selector": cfg.price_selector,
                    "stock_selector": cfg.stock_selector,
                    "active": cfg.active,
                }
                for cfg in configs
            ],
        })
    return {"concurrenten": resultaat, "totaal": len(resultaat)}


@router.post("/configs")
def create_competitor_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Voeg een nieuwe concurrent of scrape-config toe."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    # Maak concurrent aan als nog niet aanwezig
    naam = payload.get("competitor_name", "").strip()
    if not naam:
        raise HTTPException(status_code=400, detail="competitor_name is verplicht")

    bestaand = db.query(DimCompetitor).filter(DimCompetitor.competitor_name == naam).first()
    if bestaand:
        concurrent = bestaand
    else:
        concurrent = DimCompetitor(
            competitor_name=naam,
            base_url=payload.get("base_url"),
            competitor_type=payload.get("competitor_type", "online"),
            default_relevance_score=payload.get("default_relevance_score", 0.5),
            scraping_enabled=payload.get("scraping_enabled", True),
            active=True,
        )
        db.add(concurrent)
        db.commit()
        db.refresh(concurrent)

    # Voeg eventueel selector-config toe
    if payload.get("price_selector") or payload.get("title_selector"):
        cfg = CompetitorScrapeConfig(
            competitor_id=concurrent.competitor_id,
            page_type=payload.get("page_type", "product"),
            url_pattern=payload.get("url_pattern"),
            title_selector=payload.get("title_selector"),
            price_selector=payload.get("price_selector"),
            stock_selector=payload.get("stock_selector"),
            delivery_selector=payload.get("delivery_selector"),
            ean_selector=payload.get("ean_selector"),
            mpn_selector=payload.get("mpn_selector"),
            pack_size_selector=payload.get("pack_size_selector"),
            scrape_method=payload.get("scrape_method", "requests"),
            requests_per_minute=payload.get("requests_per_minute", 10),
            active=True,
        )
        db.add(cfg)
        db.commit()

    return {"status": "aangemaakt", "competitor_id": concurrent.competitor_id, "naam": naam}


@router.post("/test")
def test_scrape(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Voer een testscrape uit op één URL met opgegeven selectors.
    Slaat robots.txt / rate-limit regels in acht.
    """
    if current_user.role not in ("admin", "pricing_manager", "analyst"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is verplicht")

    from services.scraping_engine import scrape_competitor_product, SCRAPE_SKIPPED_ROBOTS
    config = {
        "title_selector": payload.get("title_selector"),
        "price_selector": payload.get("price_selector"),
        "stock_selector": payload.get("stock_selector"),
        "delivery_selector": payload.get("delivery_selector"),
        "ean_selector": payload.get("ean_selector"),
        "mpn_selector": payload.get("mpn_selector"),
    }
    resultaat = scrape_competitor_product(url, config, max_per_minute=5, max_retries=2)
    resultaat["getest_op"] = str(datetime.utcnow())
    resultaat["url"] = url
    return resultaat


@router.post("/run")
def run_scrape(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start een scrape-run voor een specifieke concurrent.
    Slaat resultaten op in fact_scrape_result.
    """
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    competitor_id = payload.get("competitor_id")
    if not competitor_id:
        raise HTTPException(status_code=400, detail="competitor_id is verplicht")

    concurrent = db.query(DimCompetitor).filter(
        DimCompetitor.competitor_id == competitor_id
    ).first()
    if not concurrent:
        raise HTTPException(status_code=404, detail="Concurrent niet gevonden")
    if not concurrent.scraping_enabled:
        raise HTTPException(status_code=400, detail="Scraping uitgeschakeld voor deze concurrent")

    configs = db.query(CompetitorScrapeConfig).filter(
        CompetitorScrapeConfig.competitor_id == competitor_id,
        CompetitorScrapeConfig.active == True,
    ).all()

    if not configs:
        return {"status": "geen_config", "bericht": "Geen actieve selector-configs voor deze concurrent"}

    from services.scraping_engine import scrape_competitor_product, save_scrape_result
    resultaten = []
    for cfg in configs[:3]:  # Demo: max 3 configs per run
        if cfg.url_pattern:
            config_dict = {
                "title_selector": cfg.title_selector,
                "price_selector": cfg.price_selector,
                "stock_selector": cfg.stock_selector,
                "delivery_selector": cfg.delivery_selector,
                "ean_selector": cfg.ean_selector,
                "mpn_selector": cfg.mpn_selector,
            }
            resultaat = scrape_competitor_product(cfg.url_pattern, config_dict, cfg.requests_per_minute)
            save_scrape_result(db, competitor_id, cfg.url_pattern, resultaat)
            resultaten.append(resultaat["scrape_status"])

    return {
        "status": "uitgevoerd",
        "concurrent": concurrent.competitor_name,
        "configs_verwerkt": len(resultaten),
        "statussen": resultaten,
    }


@router.get("/results")
def get_scrape_results(
    competitor_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal recente scrape-resultaten op."""
    q = db.query(FactScrapeResult)
    if competitor_id:
        q = q.filter(FactScrapeResult.competitor_id == competitor_id)
    resultaten = q.order_by(desc(FactScrapeResult.scraped_at)).limit(limit).all()

    concurrenten_map = {
        c.competitor_id: c.competitor_name
        for c in db.query(DimCompetitor).all()
    }

    return {
        "resultaten": [
            {
                "scrape_id": r.scrape_id,
                "competitor_name": concurrenten_map.get(r.competitor_id, str(r.competitor_id)),
                "product_url": r.product_url,
                "scraped_at": str(r.scraped_at),
                "scrape_status": r.scrape_status,
                "product_title": r.product_title,
                "price_inc_vat": float(r.price_inc_vat) if r.price_inc_vat else None,
                "stock_status": r.stock_status,
                "delivery_days": r.delivery_days,
                "ean": r.ean,
                "error_message": r.error_message,
            }
            for r in resultaten
        ],
        "totaal": len(resultaten),
    }
