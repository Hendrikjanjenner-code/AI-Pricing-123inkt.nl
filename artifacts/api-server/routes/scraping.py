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
    DimCompetitor, CompetitorScrapeConfig, FactScrapeResult, ScrapeSchedule, User
)
from datetime import datetime

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


@router.get("/status")
def get_scraping_status(
    current_user: User = Depends(get_current_user),
):
    """Geef de status van de vereiste scraping-packages terug."""
    from services.scraping_engine import check_scraping_dependencies
    return check_scraping_dependencies()


@router.get("/configs")
def get_scraping_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Haal alle concurrent-configuraties op."""
    from services.scraping_engine import check_scraping_dependencies
    deps = check_scraping_dependencies()
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
                    "delivery_selector": cfg.delivery_selector,
                    "ean_selector": cfg.ean_selector,
                    "active": cfg.active,
                }
                for cfg in configs
            ],
        })
    return {"concurrenten": resultaat, "totaal": len(resultaat), "dependencies": deps}


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
    if any(payload.get(f) for f in ("price_selector", "title_selector", "url_pattern")):
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


@router.put("/configs/{competitor_id}")
def update_competitor_config(
    competitor_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pas een bestaande concurrent-configuratie aan (selectors, scraping_enabled, naam, url)."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    concurrent = db.query(DimCompetitor).filter(DimCompetitor.competitor_id == competitor_id).first()
    if not concurrent:
        raise HTTPException(status_code=404, detail="Concurrent niet gevonden")

    if "competitor_name" in payload and payload["competitor_name"].strip():
        concurrent.competitor_name = payload["competitor_name"].strip()
    if "base_url" in payload:
        concurrent.base_url = payload["base_url"]
    if "scraping_enabled" in payload:
        concurrent.scraping_enabled = bool(payload["scraping_enabled"])
    if "competitor_type" in payload:
        concurrent.competitor_type = payload["competitor_type"]

    # Update or create the selector config for this competitor
    has_selectors = any(
        k in payload for k in ("price_selector", "title_selector", "stock_selector", "delivery_selector", "ean_selector", "url_pattern")
    )
    if has_selectors:
        cfg = db.query(CompetitorScrapeConfig).filter(
            CompetitorScrapeConfig.competitor_id == competitor_id
        ).first()
        if not cfg:
            cfg = CompetitorScrapeConfig(competitor_id=competitor_id, page_type="product", scrape_method="requests", requests_per_minute=10, active=True)
            db.add(cfg)
        for field in ("price_selector", "title_selector", "stock_selector", "delivery_selector", "ean_selector", "url_pattern"):
            if field in payload:
                setattr(cfg, field, payload[field])

    db.commit()
    return {"status": "bijgewerkt", "competitor_id": competitor_id, "naam": concurrent.competitor_name}


@router.delete("/configs/{competitor_id}")
def delete_competitor_config(
    competitor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactiveer een concurrent (soft-delete)."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    concurrent = db.query(DimCompetitor).filter(DimCompetitor.competitor_id == competitor_id).first()
    if not concurrent:
        raise HTTPException(status_code=404, detail="Concurrent niet gevonden")
    concurrent.active = False
    concurrent.scraping_enabled = False
    db.commit()
    return {"status": "gedeactiveerd", "competitor_id": competitor_id}


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

    from services.scraping_engine import (
        scrape_competitor_product, SCRAPE_SKIPPED_ROBOTS, check_scraping_dependencies,
    )
    deps = check_scraping_dependencies()
    if not deps["ok"]:
        raise HTTPException(status_code=503, detail=deps["message"])
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

    from services.scraping_engine import check_scraping_dependencies
    deps = check_scraping_dependencies()
    if not deps["ok"]:
        raise HTTPException(status_code=503, detail=deps["message"])

    from services.scraping_engine import run_scrape_for_competitor
    samenvatting = run_scrape_for_competitor(db, concurrent, triggered_by="manual")
    if samenvatting["status"] == "geen_config":
        return {"status": "geen_config", "bericht": "Geen actieve selector-configs voor deze concurrent"}
    return samenvatting


DEFAULT_SCHEDULE = [
    {"time_slot": "08:00", "label": "Ochtendrun — voor werkdag"},
    {"time_slot": "13:00", "label": "Middagscan — midden op de dag"},
    {"time_slot": "18:00", "label": "Avondrun — na sluitingstijd"},
]


@router.get("/schedule")
def get_scrape_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Haal het dagelijkse scraperooster op.
    Standaard: 3× per dag op 08:00, 13:00 en 18:00.
    """
    tijdsloten = db.query(ScrapeSchedule).order_by(ScrapeSchedule.time_slot).all()
    if not tijdsloten:
        # Seed defaults if table is empty
        for s in DEFAULT_SCHEDULE:
            db.add(ScrapeSchedule(**s, active=True))
        db.commit()
        tijdsloten = db.query(ScrapeSchedule).order_by(ScrapeSchedule.time_slot).all()

    from services.scrape_scheduler import compute_next_run, get_last_automatic_run
    volgende_run = compute_next_run(db)
    laatste_automatische_run = get_last_automatic_run(db)

    return {
        "tijdsloten": [
            {
                "id": t.id,
                "time_slot": t.time_slot,
                "label": t.label,
                "active": t.active,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tijdsloten
        ],
        "frequentie_per_dag": sum(1 for t in tijdsloten if t.active),
        "volgende_run": volgende_run,
        "laatste_automatische_run": laatste_automatische_run,
        "omschrijving": "Configureerbare scrape-tijdsloten. Standaard 3× per dag.",
    }


@router.put("/schedule/{tijdslot_id}")
def update_scrape_schedule(
    tijdslot_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activeer/deactiveer een tijdslot of pas het tijdstip aan."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    tijdslot = db.query(ScrapeSchedule).filter(ScrapeSchedule.id == tijdslot_id).first()
    if not tijdslot:
        raise HTTPException(status_code=404, detail="Tijdslot niet gevonden")
    if "active" in payload:
        tijdslot.active = bool(payload["active"])
    if "time_slot" in payload:
        nieuw = payload["time_slot"].strip()
        if len(nieuw) == 5 and nieuw[2] == ":" and nieuw[:2].isdigit() and nieuw[3:].isdigit():
            tijdslot.time_slot = nieuw
        else:
            raise HTTPException(status_code=400, detail="Ongeldig tijdformaat — verwacht HH:MM")
    if "label" in payload:
        tijdslot.label = payload["label"]
    db.commit()
    return {"status": "bijgewerkt", "tijdslot": tijdslot.time_slot, "active": tijdslot.active}


@router.post("/schedule")
def add_scrape_schedule(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Voeg een nieuw tijdslot toe aan het scraperooster."""
    if current_user.role not in ("admin", "pricing_manager"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    time_slot = (payload.get("time_slot") or "").strip()
    if not (len(time_slot) == 5 and time_slot[2] == ":" and time_slot[:2].isdigit() and time_slot[3:].isdigit()):
        raise HTTPException(status_code=400, detail="Ongeldig tijdformaat — verwacht HH:MM")
    bestaand = db.query(ScrapeSchedule).filter(ScrapeSchedule.time_slot == time_slot).first()
    if bestaand:
        raise HTTPException(status_code=409, detail=f"Tijdslot {time_slot} bestaat al")
    nieuw = ScrapeSchedule(
        time_slot=time_slot,
        label=payload.get("label", ""),
        active=payload.get("active", True),
    )
    db.add(nieuw)
    db.commit()
    db.refresh(nieuw)
    return {"status": "aangemaakt", "id": nieuw.id, "time_slot": nieuw.time_slot}


@router.post("/analyze-html")
def analyze_html(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyseer een URL (of raw HTML voor Admin) en geef gerangschikte selector-suggesties terug.
    HTML wordt nooit in de database opgeslagen.
    """
    if current_user.role not in ("admin", "pricing_manager", "analyst"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")

    url = (payload.get("url") or "").strip()
    html_snippet = payload.get("html_snippet") if current_user.role == "admin" else None

    if not url and not html_snippet:
        raise HTTPException(status_code=400, detail="url of html_snippet is verplicht")

    from services.scraping_engine import (
        _check_robots_txt, _throttle, _get_domain, USER_AGENT,
        check_scraping_dependencies, SCRAPE_FAILED_BLOCKED,
    )

    deps = check_scraping_dependencies()
    if not deps["ok"]:
        raise HTTPException(status_code=503, detail=deps["message"])

    html = html_snippet or ""
    http_status = 200

    if url and not html_snippet:
        # Robots.txt
        if not _check_robots_txt(url):
            from services.html_analyser import analyse_html as _analyse
            result = _analyse(url, "", 403, is_admin=(current_user.role == "admin"))
            return _result_to_dict(result)

        try:
            import requests
        except ImportError:
            raise HTTPException(status_code=503, detail="requests-pakket niet geïnstalleerd")

        domain = _get_domain(url)
        _throttle(domain, max_per_minute=5)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "nl-NL,nl;q=0.9",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            http_status = resp.status_code
            html = resp.text
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Pagina ophalen mislukt: {exc}")

    from services.html_analyser import analyse_html as _analyse
    result = _analyse(url, html, http_status, is_admin=(current_user.role == "admin"))
    return _result_to_dict(result)


def _result_to_dict(result) -> dict:
    def cand_list(lst):
        return [{"selector": c.selector, "sample_text": c.sample_text, "score": c.score} for c in lst]

    out = {
        "prijs_kandidaten": cand_list(result.prijs_kandidaten),
        "titel_kandidaten": cand_list(result.titel_kandidaten),
        "voorraad_kandidaten": cand_list(result.voorraad_kandidaten),
        "js_rendering_waarschijnlijk": result.js_rendering_waarschijnlijk,
        "geblokkeerd": result.geblokkeerd,
        "blok_reden": result.blok_reden,
        "aanbevolen_actie": result.aanbevolen_actie,
    }
    if result.html_preview is not None:
        out["html_preview"] = result.html_preview
    return out


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
