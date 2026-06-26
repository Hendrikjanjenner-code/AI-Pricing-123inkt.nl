"""
Scraping Engine — Module 1
Haalt publieke productdata op van geconfigureerde concurrenten.
Respecteert robots.txt, rate limits en alle wettelijke beperkingen.
Geen omzeiling van anti-bot systemen.
"""
import hashlib
import re
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

# ── Reason codes ────────────────────────────────────────────────────────────
SCRAPE_SUCCESS = "SCRAPE_SUCCESS"
SCRAPE_FAILED_TIMEOUT = "SCRAPE_FAILED_TIMEOUT"
SCRAPE_FAILED_SELECTOR_MISSING = "SCRAPE_FAILED_SELECTOR_MISSING"
SCRAPE_FAILED_BLOCKED = "SCRAPE_FAILED_BLOCKED"
SCRAPE_SKIPPED_ROBOTS = "SCRAPE_SKIPPED_ROBOTS"
SCRAPE_FAILED_INVALID_PRICE = "SCRAPE_FAILED_INVALID_PRICE"
SCRAPE_FAILED_DEPENDENCY = "SCRAPE_FAILED_DEPENDENCY"

# ── Vereiste Python-packages voor scraping ──────────────────────────────────
REQUIRED_PACKAGES = ("requests", "bs4")
DEPENDENCY_HELP = (
    "De Python-packages 'requests' en 'beautifulsoup4' zijn vereist voor scraping. "
    "Installeer ze en herstart de server."
)


def check_scraping_dependencies() -> dict:
    """
    Controleer of de scraping-packages geladen kunnen worden.
    Geeft een dict terug met: ok (bool), missing (list[str]), message (str).
    """
    missing: list[str] = []
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")
    try:
        import bs4  # noqa: F401
    except ImportError:
        missing.append("beautifulsoup4")

    if missing:
        return {
            "ok": False,
            "missing": missing,
            "message": (
                f"Ontbrekende package(s): {', '.join(missing)}. {DEPENDENCY_HELP}"
            ),
        }
    return {"ok": True, "missing": [], "message": "Alle scraping-packages zijn geïnstalleerd."}

# ── Per-domein throttle state (in-memory voor demo) ────────────────────────
_last_request_times: dict[str, list[datetime]] = {}
_robots_cache: dict[str, RobotFileParser] = {}

USER_AGENT = "PricingEngineBot/1.0 (respectful-pricing-research; +https://example.com/bot)"


def _get_domain(url: str) -> str:
    return urlparse(url).netloc


def _check_robots_txt(url: str) -> bool:
    """
    Controleer of scrapen van deze URL is toegestaan volgens robots.txt.
    Geeft True terug als toegestaan, False als verboden.
    """
    domain = _get_domain(url)
    if domain not in _robots_cache:
        rp = RobotFileParser()
        robots_url = f"https://{domain}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            _robots_cache[domain] = rp
        except Exception:
            # Bij onbereikbare robots.txt: conservatief — toestaan (robots.txt niet aanwezig)
            _robots_cache[domain] = None
    rp = _robots_cache.get(domain)
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url)


def _throttle(domain: str, max_per_minute: int = 10):
    """Zorg dat we niet meer dan max_per_minute verzoeken per domein doen."""
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=1)
    times = _last_request_times.get(domain, [])
    times = [t for t in times if t > window_start]
    if len(times) >= max_per_minute:
        sleep_secs = (times[0] - window_start).total_seconds() + random.uniform(1, 3)
        logger.info(f"Throttle {domain}: wachten {sleep_secs:.1f}s")
        time.sleep(sleep_secs)
        times = [t for t in times if t > datetime.utcnow() - timedelta(minutes=1)]
    times.append(now)
    _last_request_times[domain] = times


def parse_price(raw: str) -> Optional[float]:
    """Parseer prijsstring naar float. Ondersteunt €, komma-decimaal en punt-decimaal."""
    if not raw:
        return None
    cleaned = re.sub(r"[€$£\s]", "", raw).strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        val = float(cleaned)
        if val <= 0 or val > 100_000:
            return None
        return round(val, 4)
    except ValueError:
        return None


def parse_stock_status(raw: str) -> str:
    """Normaliseer voorraadtekst naar op_voorraad / niet_op_voorraad / onbekend."""
    if not raw:
        return "onbekend"
    lower = raw.lower()
    if any(w in lower for w in ["op voorraad", "in stock", "leverbaar", "beschikbaar", "op=op"]):
        return "op_voorraad"
    if any(w in lower for w in ["uitverkocht", "niet op voorraad", "out of stock", "niet leverbaar"]):
        return "niet_op_voorraad"
    return "onbekend"


def parse_delivery_days(raw: str) -> Optional[int]:
    """Extraheer verwacht aantal leveringsdagen uit tekst."""
    if not raw:
        return None
    match = re.search(r"(\d+)\s*(?:werkdag|dag|day|business day)", raw.lower())
    if match:
        return int(match.group(1))
    if "morgen" in raw.lower() or "vandaag" in raw.lower():
        return 1
    if "overmorgen" in raw.lower():
        return 2
    return None


def normalize_pack_size(raw: str) -> Optional[str]:
    """Normaliseer verpakkingsgrootte (bv. '10 stuks' → '10x')."""
    if not raw:
        return None
    raw = raw.strip()
    match = re.search(r"(\d+)\s*(st|stuks|pcs|pieces|pak|pack|rol|rollen|liter|ml|kg|g)", raw.lower())
    if match:
        qty = match.group(1)
        unit = match.group(2)[:2]
        return f"{qty}{unit}"
    return raw


def detect_scrape_changes(old_hash: Optional[str], new_content: str) -> bool:
    """Detecteer of de paginacontent is gewijzigd t.o.v. vorige scrape."""
    new_hash = hashlib.sha256(new_content.encode()).hexdigest()
    return old_hash != new_hash


def save_scrape_result(db, competitor_id: int, product_url: str, result: dict, triggered_by: str = "manual"):
    """Sla scrape-resultaat op in de database."""
    from models import FactScrapeResult
    record = FactScrapeResult(
        competitor_id=competitor_id,
        product_url=product_url,
        scraped_at=datetime.utcnow(),
        triggered_by=triggered_by,
        scrape_status=result.get("scrape_status", SCRAPE_FAILED_SELECTOR_MISSING),
        product_title=result.get("product_title"),
        brand=result.get("brand"),
        ean=result.get("ean"),
        mpn=result.get("mpn"),
        price_inc_vat=result.get("price_inc_vat"),
        shipping_cost=result.get("shipping_cost"),
        total_price_inc_vat=result.get("total_price_inc_vat"),
        stock_status=result.get("stock_status"),
        delivery_text=result.get("delivery_text"),
        delivery_days=result.get("delivery_days"),
        pack_size=result.get("pack_size"),
        unit_quantity=result.get("unit_quantity"),
        seller_name=result.get("seller_name"),
        raw_html_hash=result.get("raw_html_hash"),
        error_message=result.get("error_message"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def run_scrape_for_competitor(db, competitor, triggered_by: str = "manual") -> dict:
    """
    Voer een volledige scrape-run uit voor één concurrent op basis van zijn
    actieve selector-configs en sla alle resultaten op.

    Gedeeld door de handmatige /run route en de achtergrond-scheduler, zodat
    beide exact hetzelfde persisteren. Geeft een samenvatting terug met
    statussen; gooit geen excepties (de scheduler mag nooit crashen).
    """
    from models import CompetitorScrapeConfig

    configs = (
        db.query(CompetitorScrapeConfig)
        .filter(
            CompetitorScrapeConfig.competitor_id == competitor.competitor_id,
            CompetitorScrapeConfig.active == True,
        )
        .all()
    )

    if not configs:
        return {
            "status": "geen_config",
            "concurrent": competitor.competitor_name,
            "configs_verwerkt": 0,
            "statussen": [],
        }

    resultaten: list[str] = []
    for cfg in configs[:3]:  # Demo: max 3 configs per run
        if not cfg.url_pattern:
            continue
        config_dict = {
            "title_selector": cfg.title_selector,
            "price_selector": cfg.price_selector,
            "stock_selector": cfg.stock_selector,
            "delivery_selector": cfg.delivery_selector,
            "ean_selector": cfg.ean_selector,
            "mpn_selector": cfg.mpn_selector,
        }
        try:
            resultaat = scrape_competitor_product(
                cfg.url_pattern, config_dict, cfg.requests_per_minute
            )
        except Exception as exc:  # noqa: BLE001 — nooit de scheduler laten crashen
            logger.warning(
                "Scrape voor '%s' (%s) gooide een fout: %s",
                competitor.competitor_name, cfg.url_pattern, exc,
            )
            resultaat = {
                "scrape_status": SCRAPE_FAILED_TIMEOUT,
                "error_message": str(exc),
            }
        try:
            save_scrape_result(
                db, competitor.competitor_id, cfg.url_pattern, resultaat,
                triggered_by=triggered_by,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning(
                "Opslaan scrape-resultaat voor '%s' mislukt: %s",
                competitor.competitor_name, exc,
            )
        resultaten.append(resultaat["scrape_status"])

    return {
        "status": "uitgevoerd",
        "concurrent": competitor.competitor_name,
        "configs_verwerkt": len(resultaten),
        "statussen": resultaten,
    }


def scrape_competitor_product(
    url: str,
    config: dict,
    max_per_minute: int = 10,
    max_retries: int = 3,
) -> dict:
    """
    Haal productdata op van één product-URL.
    Respecteert robots.txt en rate limits.
    Geeft altijd een dict terug met scrape_status.
    """
    # Robots.txt controle
    if not _check_robots_txt(url):
        logger.warning(f"robots.txt blokkeert {url}")
        return {"scrape_status": SCRAPE_SKIPPED_ROBOTS, "error_message": "Geblokkeerd door robots.txt"}

    domain = _get_domain(url)

    for poging in range(max_retries):
        try:
            _throttle(domain, max_per_minute)
            delay = random.uniform(0.5, 2.0)
            time.sleep(delay)

            try:
                import requests
                from bs4 import BeautifulSoup
            except ImportError:
                return {
                    "scrape_status": SCRAPE_FAILED_DEPENDENCY,
                    "error_message": DEPENDENCY_HELP,
                }

            headers = {
                "User-Agent": USER_AGENT,
                "Accept-Language": "nl-NL,nl;q=0.9",
            }
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code == 403 or resp.status_code == 429:
                return {"scrape_status": SCRAPE_FAILED_BLOCKED, "error_message": f"HTTP {resp.status_code}"}
            if resp.status_code != 200:
                if poging < max_retries - 1:
                    time.sleep(2 ** poging)
                    continue
                return {"scrape_status": SCRAPE_FAILED_TIMEOUT, "error_message": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")
            content_hash = hashlib.sha256(resp.text.encode()).hexdigest()

            def extract(selector: Optional[str]) -> Optional[str]:
                if not selector:
                    return None
                el = soup.select_one(selector)
                return el.get_text(strip=True) if el else None

            raw_price = extract(config.get("price_selector"))
            prijs = parse_price(raw_price or "")
            if raw_price and prijs is None:
                return {"scrape_status": SCRAPE_FAILED_INVALID_PRICE, "error_message": f"Ongeldige prijs: {raw_price}"}

            raw_title = extract(config.get("title_selector"))
            if not raw_title:
                return {"scrape_status": SCRAPE_FAILED_SELECTOR_MISSING, "error_message": "title_selector leeg"}

            raw_stock = extract(config.get("stock_selector"))
            raw_delivery = extract(config.get("delivery_selector"))
            raw_pack_size = extract(config.get("pack_size_selector"))

            shipping = 0.0
            total = prijs
            if prijs:
                total = round(prijs + (shipping or 0.0), 4)

            return {
                "scrape_status": SCRAPE_SUCCESS,
                "product_title": raw_title,
                "brand": None,
                "ean": extract(config.get("ean_selector")),
                "mpn": extract(config.get("mpn_selector")),
                "price_inc_vat": prijs,
                "shipping_cost": shipping,
                "total_price_inc_vat": total,
                "stock_status": parse_stock_status(raw_stock or ""),
                "delivery_text": raw_delivery,
                "delivery_days": parse_delivery_days(raw_delivery or ""),
                "pack_size": normalize_pack_size(raw_pack_size or ""),
                "unit_quantity": None,
                "seller_name": None,
                "raw_html_hash": content_hash,
                "error_message": None,
            }

        except Exception as exc:
            backoff = 2 ** poging + random.uniform(0, 1)
            logger.warning(f"Scrape poging {poging + 1} mislukt: {exc}. Wachten {backoff:.1f}s")
            if poging < max_retries - 1:
                time.sleep(backoff)

    return {"scrape_status": SCRAPE_FAILED_TIMEOUT, "error_message": "Max pogingen bereikt"}


def scrape_competitor_category(
    category_url: str,
    config: dict,
    max_products: int = 50,
) -> list[dict]:
    """
    Doorzoek een categorie-pagina en haal product-URLs op.
    Geeft lijst van scrape-resultaten terug.
    """
    if not _check_robots_txt(category_url):
        return [{"scrape_status": SCRAPE_SKIPPED_ROBOTS, "product_url": category_url}]

    results = []
    try:
        import requests
        from bs4 import BeautifulSoup
        domain = _get_domain(category_url)
        _throttle(domain, config.get("requests_per_minute", 10))
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(category_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return [{"scrape_status": SCRAPE_FAILED_TIMEOUT, "product_url": category_url}]
        soup = BeautifulSoup(resp.text, "html.parser")
        product_links = [
            a["href"] for a in soup.find_all("a", href=True)
            if "/product/" in a["href"] or "/p/" in a["href"]
        ][:max_products]
        for link in product_links:
            if not link.startswith("http"):
                link = f"https://{domain}{link}"
            result = scrape_competitor_product(link, config)
            result["product_url"] = link
            results.append(result)
    except ImportError:
        results = [{"scrape_status": SCRAPE_FAILED_DEPENDENCY, "error_message": DEPENDENCY_HELP}]
    except Exception as exc:
        results = [{"scrape_status": SCRAPE_FAILED_TIMEOUT, "error_message": str(exc)}]
    return results
