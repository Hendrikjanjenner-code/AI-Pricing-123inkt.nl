"""
PriceShape feed → volledige catalogus-ingestie.

De PriceShape output-feed is de bron van waarheid voor:
- de productcatalogus (dim_product)      — 1 record per product (gtin)
- de eigen dagprijs (fact_price_daily)   — priceInclVat + costPriceExclVat
- concurrentprijzen (fact_competitor_price_daily) — geneste vendors[] per product

Deze module leest de feed één keer in en persisteert bovenstaande in bulk,
zodat de rest van de app (dashboard, aanbevelingen, concurrentie-intelligentie)
op echte feed-data draait. Er wordt GEEN verkoop-/voorraadhistorie verzonnen;
alleen wat de feed daadwerkelijk levert wordt opgeslagen.

Na de ingestie berekent `score_competition` de PCIS-scores per SKU uit de echte
concurrentprijzen, zodat de /competition-pagina's gevuld zijn.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from statistics import mean, pstdev

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from connectors import priceshape_connector as pc
from engine import competition_engine as ce

logger = logging.getLogger("uvicorn.error")

SOURCE_NAME = "priceshape"
_CHUNK = 5_000

# Strategie die zonder verkoop-/voorraadhistorie werkt: puur op concurrentprijzen.
_DEFAULT_STRATEGY = "COMPETITOR_INDEX"


# ── helpers ─────────────────────────────────────────────────────────────────
def _f(value) -> float | None:
    """Tolerante float-parse (accepteert '35,5' en '35.5')."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _split_category(ppc: str) -> tuple[str | None, str | None]:
    """'printer supplies > inkjet > cartridges' → ('Printer Supplies', 'Cartridges')."""
    if not ppc:
        return None, None
    parts = [p.strip() for p in str(ppc).replace("/", ">").split(">") if p.strip()]
    if not parts:
        return None, None
    top = parts[0].title()
    leaf = parts[-1].title() if len(parts) > 1 else None
    return top, leaf


def _brand_from_title(title: str) -> str | None:
    title = _s(title)
    if not title:
        return None
    first = title.split()[0]
    return first if first[:1].isalpha() else None


def _chunks(seq: list, size: int = _CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# Veldnamen die al naar echte kolommen worden gemapt — alles daarbuiten gaat
# verliesvrij mee in raw_attributes (per product / per vendor).
_PRODUCT_MAPPED_KEYS = {
    "gtin", "producttitle", "ppc_producttype", "itemgroupid",
    "priceinclvat", "costpriceexclvat",
}
_VENDOR_MAPPED_KEYS = {
    "domain", "name", "price", "producturl",
    "instock", "in_stock", "stock", "availability", "available",
    "deliverydays", "delivery_days", "deliverytime", "delivery_time", "leverdagen",
    "currency", "valuta", "scrapedat", "scraped_at", "timestamp", "lastseen", "last_seen",
}
_TRUE_WORDS = {"true", "1", "yes", "ja", "in stock", "instock", "in_stock", "op voorraad", "available", "y"}
_FALSE_WORDS = {"false", "0", "no", "nee", "out of stock", "outofstock", "out_of_stock",
                "niet op voorraad", "unavailable", "n"}


def _parse_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    s = _s(value).lower()
    if not s:
        return None
    if s in _TRUE_WORDS:
        return True
    if s in _FALSE_WORDS:
        return False
    return None


def _parse_dt(value):
    """Tolerante timestamp-parse (ISO-achtig); None bij onparseerbaar."""
    s = _s(value)
    if not s:
        return None
    from datetime import datetime as _dt
    for cleaned in (s.replace("Z", "+00:00"), s):
        try:
            return _dt.fromisoformat(cleaned)
        except ValueError:
            continue
    return None


def _first(rec: dict, *keys):
    """Case-insensitieve lookup van de eerste aanwezige sleutel."""
    lower = {str(k).strip().lower(): v for k, v in rec.items()}
    for key in keys:
        if key in lower and lower[key] not in (None, ""):
            return lower[key]
    return None


def _json_safe(v):
    """Maak een waarde JSON-serialiseerbaar zonder structuur of inhoud te verliezen."""
    from decimal import Decimal
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, Decimal):
        return float(v)
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return pc._stringify(v)


def _with_overflow(raw: dict | None, overflow: dict[str, tuple[str, int]]) -> dict | None:
    """
    Bewaar de ORIGINELE waarde van gemapte velden die door een kolomlimiet
    afgekapt worden, zodat het verliesvrij-contract ook voor gemapte velden
    geldt. `overflow` = {rawkey: (originele_waarde, kolomlimiet)}.
    """
    extra = {key: val for key, (val, limit) in overflow.items()
             if val and len(val) > limit}
    if not extra:
        return raw
    return {**(raw or {}), **extra}


def _raw_leftovers(rec: dict, mapped: set[str], exclude_values: tuple = ()) -> dict | None:
    """
    Alle niet-gemapte velden verliesvrij als JSON — inclusief geneste structuren,
    zonder truncatie. Alleen expliciet uitgesloten waarden (zoals de apart
    verwerkte vendor-lijst) worden overgeslagen.
    """
    out: dict = {}
    for k, v in rec.items():
        lk = str(k).strip().lower()
        if lk in mapped or v is None or v == "":
            continue
        if any(v is ex for ex in exclude_values):
            continue  # bijv. de geneste vendor-lijst — apart verwerkt in eigen rijen
        out[str(k)] = _json_safe(v)
    return out or None


# ── feed → genormaliseerde catalogus + concurrentrijen ──────────────────────
def _normalize(records) -> tuple[list[dict], list[dict]]:
    """Zet ruwe JSON-productrecords (lijst of iterator) om naar (catalogus, concurrentrijen)."""
    catalog: dict[str, dict] = {}
    comp_rows: list[dict] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue
        gtin = _s(rec.get("gtin"))
        if not gtin:
            continue

        if gtin not in catalog:
            title = _s(rec.get("productTitle")) or gtin
            top, leaf = _split_category(rec.get("PPC_ProductType"))
            catalog[gtin] = {
                "sku_id": gtin,
                "ean": gtin,
                "product_name": title[:500],
                "brand": _brand_from_title(title)[:255],
                "category": top,
                "subcategory": leaf,
                "product_group": _s(rec.get("itemGroupId")) or None,
                "current_price": _f(rec.get("priceInclVat")),
                "price_incl_vat": _f(rec.get("priceInclVat")),
                "cost_price": _f(rec.get("costPriceExclVat")),
                "strategy_type": _DEFAULT_STRATEGY,
                "lifecycle_status": "active",
                "is_active": True,
                "import_source": SOURCE_NAME,
                "data_quality_score": 1.0,
                # Vendor-lijst wordt apart tot eigen rijen genormaliseerd —
                # alle overige velden (ook genest) gaan verliesvrij mee, en
                # afgekapte gemapte velden behouden hun originele waarde.
                "raw_attributes": _with_overflow(
                    _raw_leftovers(
                        rec, _PRODUCT_MAPPED_KEYS,
                        exclude_values=(pc._find_vendor_list(rec),),
                    ),
                    {"_productTitle_full": (title, 500)},
                ),
            }

        vendors = pc._find_vendor_list(rec) or []
        seen_domains: set[str] = set()
        for v in vendors:
            if not isinstance(v, dict):
                continue
            domain = _s(v.get("domain") or v.get("name"))
            price = _f(v.get("price"))
            if not domain or price is None or domain in seen_domains:
                continue
            seen_domains.add(domain)
            comp_rows.append({
                "sku_id": gtin,
                "competitor_name": domain[:255],
                "price": price,
                "url": _s(v.get("productUrl")) or None,
                "in_stock": _parse_bool(_first(v, "instock", "in_stock", "stock",
                                                "availability", "available")),
                "delivery_days": _f(_first(v, "deliverydays", "delivery_days",
                                           "deliverytime", "delivery_time", "leverdagen")),
                "currency": (_s(_first(v, "currency", "valuta"))[:3] or None),
                "vendor_name": (_s(v.get("name"))[:255] or None),
                "observed_at": _parse_dt(_first(v, "scrapedat", "scraped_at",
                                                "timestamp", "lastseen", "last_seen")),
                "raw_attributes": _with_overflow(
                    _raw_leftovers(v, _VENDOR_MAPPED_KEYS),
                    {
                        "_domain_full": (domain, 255),
                        "_name_full": (_s(v.get("name")), 255),
                        "_currency_full": (_s(_first(v, "currency", "valuta")), 3),
                    },
                ),
            })

    return list(catalog.values()), comp_rows


def _parse_content(content: bytes, content_type: str, fmt: str) -> tuple[list[dict], list[dict]]:
    if fmt == "json":
        data = json.loads(content.decode("utf-8", "ignore"))
        records = pc._json_extract_rows(data)
        return _normalize(records)
    # CSV/XML: val terug op de platte expand-parser en normaliseer via aliassen.
    rows = pc._parse_feed_rows(content, content_type, fmt)
    return _normalize_flat(rows)


def _read_feed(db: Session, content: bytes | None = None,
               content_type: str = "") -> tuple[list[dict], list[dict]]:
    cfg = pc._get_feed_config(db=db)

    # Diagnostiek: begin elke leescyclus met schone responsmetadata zodat een
    # "0 producten"-melding nooit de metadata van een eerdere run toont.
    pc.reset_last_feed_response()

    # Vooraf opgehaalde body (bijv. bulk-load van schijf): parse gebufferd.
    if content is not None:
        pc._record_feed_response(None, content_type, len(content), content[:2048])
        fmt = pc._detect_feed_format(content, content_type, cfg["feed_format"])
        return _parse_content(content, content_type, fmt)

    # Geen body meegegeven: probeer STREAMING JSON-parsing (ijson) om het
    # piekgeheugen laag te houden — de PriceShape-feed is ~200 MB en zou als
    # één json.loads-structuur enkele GB's kosten en de VM OOM-killen.
    #
    # BELANGRIJK: val ALLEEN terug op gebufferd lezen bij `NotStreamable` (een
    # niet-array-formaat zoals CSV/XML/object-wrapper). Andere fouten — netwerk,
    # kapotte JSON, MemoryError — worden bewust NIET opgevangen: gebufferd
    # opnieuw proberen zou de 206 MB alsnog in het geheugen trekken en de
    # OOM-bescherming ondermijnen. Laat die fouten doorlopen; de scheduler
    # probeert de cyclus later opnieuw (retry/backoff) en de bestaande data
    # blijft intact (empty-feed-guard in ingest_feed).
    if (cfg.get("feed_format") or "auto") in ("auto", "json"):
        try:
            logger.info("Feed-parse: streaming JSON (ijson).")
            return _normalize(pc.stream_json_records(cfg["feed_url"]))
        except pc.NotStreamable:
            logger.info(
                "Feed is geen top-level JSON-array — val terug op gebufferd lezen."
            )

    # Fallback: volledige download + gebufferde parse (CSV/XML of object-wrapper).
    logger.info("Feed-parse: gebufferd lezen (niet-streambaar formaat).")
    content, content_type = pc._fetch_feed(cfg["feed_url"])
    fmt = pc._detect_feed_format(content, content_type, cfg["feed_format"])
    return _parse_content(content, content_type, fmt)


import re as _re

_WIDE_VENDOR_RE = _re.compile(r"^vendor_(\d+)\s+(.+)$")

# Basisproductvelden die expliciet gemapt worden in het brede CSV-formaat;
# alle overige niet-lege basiskolommen gaan verliesvrij mee in raw_attributes.
_WIDE_PRODUCT_MAPPED = {"gtin", "ean", "barcode", "itemgroupid", "name",
                        "producttitle", "priceinclvat", "costpriceexclvat",
                        "ppc_producttype", "category"}
# Vendorsubvelden die expliciet gemapt worden; de rest (priceWithShipping,
# previousPrice, shippingCost, source, pricePosition, …) blijft in raw.
_WIDE_VENDOR_MAPPED = {"domain", "price", "producturl", "stockstatus"}


def _normalize_wide_csv(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Normaliseer het BREDE PriceShape CSV-exportformaat: één product per rij,
    concurrenten in kolomgroepen `vendor_N <veld>` (domain, price, stockStatus,
    productUrl, priceWithShipping, …). Dit is het formaat dat de standaard
    export-feed (public.app.priceshape.io …/export/…) daadwerkelijk levert:
    geen gtin-kolom — `itemGroupId` is de productsleutel.
    """
    catalog: dict[str, dict] = {}
    comp_rows: list[dict] = []
    # Dedupliceer offers over de HELE feed op (sku, domein): dubbele
    # productrijen of herhaalde vendor-kolommen mogen geen dubbele
    # dagobservaties opleveren (eerste voorkomen wint — zelfde semantiek als
    # `seen_domains` in de JSON-normalisatie).
    seen_offers: set[tuple[str, str]] = set()
    for r in rows:
        gtin = _s(r.get("gtin") or r.get("ean") or r.get("barcode"))
        sku = gtin or _s(r.get("itemgroupid"))
        if not sku:
            continue

        base: dict = {}
        vendors: dict[int, dict] = {}
        for k, v in r.items():
            m = _WIDE_VENDOR_RE.match(k)
            if m:
                vendors.setdefault(int(m.group(1)), {})[m.group(2).strip()] = v
            else:
                base[k] = v

        if sku not in catalog:
            title = _s(base.get("name") or base.get("producttitle")) or sku
            top, leaf = _split_category(base.get("ppc_producttype") or base.get("category"))
            raw = {k: v for k, v in base.items()
                   if _s(v) and k not in _WIDE_PRODUCT_MAPPED}
            catalog[sku] = {
                "sku_id": sku, "ean": gtin or None, "product_name": title[:500],
                "brand": _brand_from_title(title)[:255] if _brand_from_title(title) else None,
                "category": top, "subcategory": leaf,
                "product_group": _s(base.get("itemgroupid")) or None,
                "current_price": _f(base.get("priceinclvat")),
                "price_incl_vat": _f(base.get("priceinclvat")),
                "cost_price": _f(base.get("costpriceexclvat")),
                "strategy_type": _DEFAULT_STRATEGY, "lifecycle_status": "active",
                "is_active": True, "import_source": SOURCE_NAME, "data_quality_score": 1.0,
                "raw_attributes": _with_overflow(
                    raw or None, {"_productTitle_full": (title, 500)}),
            }

        for idx in sorted(vendors):
            v = vendors[idx]
            domain_raw = _s(v.get("domain"))
            domain = domain_raw.lower()
            price = _f(v.get("price"))
            if not domain or price is None:
                continue
            if (sku, domain) in seen_offers:
                continue
            seen_offers.add((sku, domain))
            vraw = {k: val for k, val in v.items()
                    if _s(val) and k not in _WIDE_VENDOR_MAPPED}
            comp_rows.append({
                "sku_id": sku, "competitor_name": domain[:255], "price": price,
                "url": _s(v.get("producturl")) or None,
                "in_stock": _parse_bool(v.get("stockstatus")),
                "delivery_days": None,
                "currency": None,
                "vendor_name": None,
                "observed_at": None,
                # Bewaar het ORIGINELE (niet-kleingeschreven) domein bij overflow.
                "raw_attributes": _with_overflow(
                    vraw or None, {"_domain_full": (domain_raw, 255)}),
            })
    return list(catalog.values()), comp_rows


def _normalize_flat(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fallback voor niet-JSON feeds: platte, ge-unneste rijen (alias-gebaseerd)."""
    # Breed exportformaat (vendor_N-kolommen)? Dan de speciale wide-normalisatie.
    if rows and any(_WIDE_VENDOR_RE.match(k) for k in rows[0].keys()):
        return _normalize_wide_csv(rows)
    catalog: dict[str, dict] = {}
    comp_rows: list[dict] = []
    for r in rows:
        gtin = _s(r.get("gtin") or r.get("ean") or r.get("barcode"))
        if not gtin:
            continue
        if gtin not in catalog:
            title = _s(r.get("producttitle") or r.get("product_name") or r.get("title")) or gtin
            top, leaf = _split_category(r.get("ppc_producttype") or r.get("category"))
            catalog[gtin] = {
                "sku_id": gtin, "ean": gtin, "product_name": title[:500],
                "brand": _brand_from_title(title)[:255], "category": top, "subcategory": leaf,
                "product_group": _s(r.get("itemgroupid")) or None,
                "current_price": _f(r.get("priceinclvat")),
                "price_incl_vat": _f(r.get("priceinclvat")),
                "cost_price": _f(r.get("costpriceexclvat")),
                "strategy_type": _DEFAULT_STRATEGY, "lifecycle_status": "active",
                "is_active": True, "import_source": SOURCE_NAME, "data_quality_score": 1.0,
                "raw_attributes": _with_overflow(
                    _raw_leftovers(r, _PRODUCT_MAPPED_KEYS | _VENDOR_MAPPED_KEYS | {
                        "ean", "barcode", "product_name", "title", "category",
                        "competitor", "retailer", "competitor_price", "url",
                    }),
                    {"_productTitle_full": (title, 500)},
                ),
            }
        domain = _s(r.get("domain") or r.get("competitor") or r.get("retailer"))
        price = _f(r.get("price") or r.get("competitor_price"))
        if domain and price is not None:
            comp_rows.append({
                "sku_id": gtin, "competitor_name": domain[:255], "price": price,
                "url": _s(r.get("producturl") or r.get("url")) or None,
                "in_stock": _parse_bool(_first(r, "instock", "in_stock", "stock",
                                               "availability", "available")),
                "delivery_days": _f(_first(r, "deliverydays", "delivery_days",
                                           "deliverytime", "delivery_time", "leverdagen")),
                "currency": (_s(_first(r, "currency", "valuta"))[:3] or None),
                "vendor_name": None,
                "observed_at": _parse_dt(_first(r, "scrapedat", "scraped_at",
                                                "timestamp", "lastseen", "last_seen")),
                "raw_attributes": _with_overflow(
                    _raw_leftovers(r, _PRODUCT_MAPPED_KEYS | _VENDOR_MAPPED_KEYS | {
                        "ean", "barcode", "product_name", "title", "category",
                        "competitor", "retailer", "competitor_price", "url",
                    }),
                    {
                        "_domain_full": (domain, 255),
                        "_currency_full": (_s(_first(r, "currency", "valuta")), 3),
                    },
                ),
            })
    return list(catalog.values()), comp_rows


# ── persisteren ─────────────────────────────────────────────────────────────
def ingest_feed(db: Session, source: str = SOURCE_NAME,
                content: bytes | None = None, content_type: str = "") -> dict:
    """Lees de feed volledig in en persisteer catalogus + prijzen + concurrenten.

    `content` kan een reeds opgehaalde feed-body zijn (bijv. van schijf), zodat
    een eenmalige bulk-load de trage download kan overslaan.
    """
    today = date.today()
    from services import import_settings as imps
    settings = imps.get_settings(db, "priceshape")
    try:
        catalog, comp_rows = _read_feed(db, content=content, content_type=content_type)
    except Exception as _feed_exc:
        from connectors.priceshape_connector import ConnectorError as _ConnectorError
        if isinstance(_feed_exc, _ConnectorError):
            logger.error(
                "PriceShape feed niet bereikbaar of onleesbaar — sync afgebroken, "
                "bestaande catalogus en concurrentprijzen blijven intact "
                "(last-known-good). Fout: %s", _feed_exc
            )
        raise

    # Importselectie (aan/uitvinken): uitgevinkte concurrenten overslaan.
    # Bestaande data wordt hierdoor NIET gewist (zie last-known-good hieronder):
    # de delete is beperkt tot rijen die vervangen worden.
    skipped_competitor_rows = 0
    if settings["disabled_competitors"]:
        kept = [r for r in comp_rows
                if not imps.competitor_disabled(settings, r["competitor_name"])]
        skipped_competitor_rows = len(comp_rows) - len(kept)
        comp_rows = kept
    if not imps.component_enabled(settings, "competitor_prices"):
        skipped_competitor_rows += len(comp_rows)
        comp_rows = []
    # Uitgevinkte onderdelen zijn een echte no-op: de betreffende kolommen
    # worden niet geschreven, zodat bestaande waarden behouden blijven.
    own_on = imps.component_enabled(settings, "own_prices")
    cost_on = imps.component_enabled(settings, "cost_prices")
    attrs_on = imps.component_enabled(settings, "extra_attributes")
    avail_on = imps.component_enabled(settings, "availability")
    if not own_on:
        for p in catalog:
            p["current_price"] = None  # alleen gebruikt bij NIEUWE producten (insert)
            p["price_incl_vat"] = None
    if not cost_on:
        for p in catalog:
            p["cost_price"] = None  # idem: alleen inserts; updates laten de kolom ongemoeid
    if not attrs_on:
        for p in catalog:
            p["raw_attributes"] = None

    # Veiligheidsklep: een lege feed (netwerkhik, verlopen token, kapotte export)
    # mag NOOIT de bestaande dagdata wissen. Zonder producten én zonder
    # concurrentprijzen breken we af vóór welke delete dan ook, zodat de app
    # blijft draaien op de laatst-goede data ("never break").
    if not catalog and not comp_rows:
        # Neem de responsmetadata (HTTP-status, content-type, bytes, eerste
        # ~200 tekens) op in log én fout, zodat de echte oorzaak (lege export,
        # HTML-foutpagina met HTTP 200, rate limiting) vaststelbaar is.
        response_info = pc.describe_last_feed_response()
        logger.error(
            "PriceShape feed leverde 0 producten en 0 concurrentprijzen op — "
            "sync afgebroken om bestaande catalogus en concurrentprijzen te beschermen "
            "(last-known-good: bestaande data blijft ongewijzigd staan). "
            "Ontvangen respons: %s", response_info,
        )
        raise ValueError(
            "PriceShape feed leverde 0 producten en 0 concurrentprijzen op — "
            "sync afgebroken om bestaande data te beschermen (laatst-goede data "
            f"blijft staan). Ontvangen respons: {response_info}"
        )

    # 1. Producten: splits in nieuw vs bestaand.
    existing_ids = {row[0] for row in db.query(models.DimProduct.sku_id).all()}
    to_insert = [p for p in catalog if p["sku_id"] not in existing_ids]
    to_update = [p for p in catalog if p["sku_id"] in existing_ids]

    for chunk in _chunks(to_insert):
        db.bulk_insert_mappings(models.DimProduct, chunk)
    if to_update:
        def _upd_map(p: dict) -> dict:
            m = {
                "sku_id": p["sku_id"], "product_name": p["product_name"], "brand": p["brand"],
                "category": p["category"], "subcategory": p["subcategory"],
                "product_group": p["product_group"],
                "lifecycle_status": "active", "is_active": True, "import_source": source,
            }
            # Uitgevinkte onderdelen: kolom niet meesturen → bestaande waarde blijft.
            if own_on:
                m["current_price"] = p["current_price"]
                m["price_incl_vat"] = p["price_incl_vat"]
            if cost_on:
                m["cost_price"] = p["cost_price"]
            if attrs_on:
                m["raw_attributes"] = p.get("raw_attributes")
            return m
        upd = [_upd_map(p) for p in to_update]
        for chunk in _chunks(upd):
            db.bulk_update_mappings(models.DimProduct, chunk)
    db.commit()

    # 2. Categorieën + strategie-mapping (idempotent).
    cats = {(p["category"], p["subcategory"]) for p in catalog if p["category"]}
    existing_cat = {c[0] for c in db.query(models.DimCategory.name).all()}
    existing_map = {c[0] for c in db.query(models.CategoryStrategyMapping.category).all()}
    for top in {c[0] for c in cats}:
        if top not in existing_cat:
            db.add(models.DimCategory(name=top, default_strategy=_DEFAULT_STRATEGY))
        if top not in existing_map:
            db.add(models.CategoryStrategyMapping(category=top, strategy_type=_DEFAULT_STRATEGY,
                                                  updated_by=source))
    db.commit()

    # 3. Eigen dagprijs (fact_price_daily) — vervang die van vandaag.
    # Alleen wissen als er vervangende prijzen zijn: een lege set mag de
    # bestaande dagprijzen niet weggooien (laatst-goede data blijft staan).
    price_maps = [{
        "date": today, "sku_id": p["sku_id"], "price": p["current_price"],
        "cost_price": p["cost_price"],
    } for p in catalog if p["current_price"] is not None]
    if not imps.component_enabled(settings, "own_prices"):
        logger.info("Feed-sync: eigen prijzen uitgevinkt in importinstellingen — overgeslagen.")
        price_maps = []
    elif not cost_on and price_maps:
        # Kostprijzen uitgevinkt: bestaande kostprijs van vandaag behouden in
        # de vervangende dagprijsrijen (replace mag niets wissen).
        existing_costs = dict(db.query(
            models.FactPriceDaily.sku_id, models.FactPriceDaily.cost_price,
        ).filter(models.FactPriceDaily.date == today).all())
        for m in price_maps:
            m["cost_price"] = existing_costs.get(m["sku_id"])
    if price_maps:
        db.query(models.FactPriceDaily).filter(models.FactPriceDaily.date == today).delete(
            synchronize_session=False)
        for chunk in _chunks(price_maps):
            db.bulk_insert_mappings(models.FactPriceDaily, chunk)
        db.commit()
    else:
        logger.warning(
            "Feed-sync: 0 eigen dagprijzen ontvangen — bestaande dagprijzen "
            "van vandaag blijven behouden (niet gewist)."
        )

    # 4. Concurrentprijzen — vervang die van deze bron voor vandaag.
    # Zelfde bescherming: zonder vervangende concurrentprijzen NIET wissen, zodat
    # een gedeeltelijke feed-uitval (wel producten, geen concurrenten) de
    # bestaande concurrent-snapshot van vandaag niet vernietigt.
    known = {p["sku_id"] for p in catalog} | existing_ids
    comp_maps = [{
        "date": today, "sku_id": r["sku_id"], "competitor_name": r["competitor_name"],
        "price": r["price"], "url": r["url"], "source": source,
        "in_stock": r.get("in_stock"), "delivery_days": r.get("delivery_days"),
        "currency": r.get("currency"), "vendor_name": r.get("vendor_name"),
        "observed_at": r.get("observed_at"), "raw_attributes": r.get("raw_attributes"),
    } for r in comp_rows if r["sku_id"] in known]

    if comp_maps and (not avail_on or not attrs_on):
        # Uitgevinkt onderdeel = no-op: neem de bestaande waarden van vandaag
        # over in de vervangende rijen, zodat de replace niets wist.
        existing_today = {
            (rec.sku_id, rec.competitor_name): rec
            for rec in db.query(models.FactCompetitorPriceDaily).filter(
                models.FactCompetitorPriceDaily.date == today,
                models.FactCompetitorPriceDaily.source == source,
            ).all()
        }
        for m in comp_maps:
            prev = existing_today.get((m["sku_id"], m["competitor_name"]))
            if not avail_on:
                m["in_stock"] = prev.in_stock if prev else None
                m["delivery_days"] = prev.delivery_days if prev else None
            if not attrs_on:
                m["raw_attributes"] = prev.raw_attributes if prev else None
    if comp_maps:
        # Volledige vervanging van de snapshot van vandaag (normale pad), maar
        # uitgevinkte concurrenten behouden hun bestaande data (worden nooit
        # gewist door een sync waarin ze niet meegenomen worden).
        delete_q = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.date == today,
            models.FactCompetitorPriceDaily.source == source,
        )
        disabled = settings["disabled_competitors"]
        if disabled:
            delete_q = delete_q.filter(
                ~func.lower(models.FactCompetitorPriceDaily.competitor_name).in_(disabled)
            )
        delete_q.delete(synchronize_session=False)
        for chunk in _chunks(comp_maps):
            db.bulk_insert_mappings(models.FactCompetitorPriceDaily, chunk)
        db.commit()
    else:
        logger.warning(
            "Feed-sync: 0 concurrentprijzen ontvangen — bestaande concurrent-"
            "snapshot van vandaag blijft behouden (niet gewist)."
        )

    # 5. Beschikbaarheid van concurrenten (fact_competitor_offer_daily) — alleen
    # wanneer het onderdeel aan staat én de feed daadwerkelijk voorraaddata levert.
    offers_written = 0
    if imps.component_enabled(settings, "availability"):
        offers_written = _persist_offers(db, today, comp_maps)

    return {
        "products_new": len(to_insert),
        "products_updated": len(to_update),
        "products_total": len(catalog),
        "own_prices": len(price_maps),
        "competitor_rows": len(comp_maps),
        "offer_rows": offers_written,
        "skipped_by_settings": skipped_competitor_rows,
    }


def _persist_offers(db: Session, today: date, comp_maps: list[dict]) -> int:
    """
    Schrijf vendor-voorraaddata door naar fact_competitor_offer_daily, zodat het
    bestaande beschikbaarheidsmodel (update_availability) er direct mee kan werken.
    Alleen rijen met een echte voorraad-/levertijdwaarneming worden geschreven;
    zonder zulke data wordt er niets gewist (last-known-good).
    """
    with_stock = [m for m in comp_maps
                  if m.get("in_stock") is not None or m.get("delivery_days") is not None]
    if not with_stock:
        return 0

    # Concurrentregister bijwerken: domein → competitor_id (idempotent).
    names = {m["competitor_name"] for m in with_stock}
    existing = {c.competitor_name: c.competitor_id
                for c in db.query(models.DimCompetitor).filter(
                    models.DimCompetitor.competitor_name.in_(names)).all()}
    for name in sorted(names - set(existing)):
        db.add(models.DimCompetitor(competitor_name=name))
    db.flush()
    ids = {c.competitor_name: c.competitor_id
           for c in db.query(models.DimCompetitor).filter(
               models.DimCompetitor.competitor_name.in_(names)).all()}

    offer_maps = [{
        "date": today,
        "own_sku_id": m["sku_id"],
        "competitor_id": ids[m["competitor_name"]],
        "product_url": m.get("url"),
        "competitor_price_inc_vat": m.get("price"),
        "in_stock": m.get("in_stock"),
        "delivery_days": int(m["delivery_days"]) if m.get("delivery_days") is not None else None,
        "match_type": "Exact",
        "source": "priceshape",
    } for m in with_stock]

    # Alleen de eigen (priceshape) rijen van vandaag vervangen voor precies de
    # (SKU, concurrent)-combinaties die opnieuw aangeleverd worden — offers van
    # scrapers, andere shops én uitgevinkte/afwezige concurrenten blijven staan.
    db.query(models.FactCompetitorOfferDaily).filter(
        models.FactCompetitorOfferDaily.date == today,
        models.FactCompetitorOfferDaily.source == "priceshape",
        models.FactCompetitorOfferDaily.own_sku_id.in_({m["sku_id"] for m in with_stock}),
        models.FactCompetitorOfferDaily.competitor_id.in_(
            {m["competitor_id"] for m in offer_maps}),
    ).delete(synchronize_session=False)
    for chunk in _chunks(offer_maps):
        db.bulk_insert_mappings(models.FactCompetitorOfferDaily, chunk)
    db.commit()
    return len(offer_maps)


# ── PCIS-scoring uit echte concurrentprijzen ────────────────────────────────
def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_competition(db: Session) -> int:
    """Bereken SkuCompetitionScore per SKU uit de concurrentprijzen van vandaag."""
    today = date.today()

    products = {
        p.sku_id: p for p in db.query(
            models.DimProduct.sku_id, models.DimProduct.current_price, models.DimProduct.category
        ).all()
    }

    # Concurrentprijzen van vandaag groeperen per SKU.
    # Door analisten afgekeurde matches (REJECTED) tellen niet mee (§match-review).
    from engine.competition_intelligence import rejected_pairs
    rejected = rejected_pairs(db)
    by_sku: dict[str, list[float]] = {}
    rows = db.query(
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
    ).filter(models.FactCompetitorPriceDaily.date == today).all()
    for sku_id, competitor_name, price in rows:
        if price is None or (sku_id, competitor_name) in rejected:
            continue
        by_sku.setdefault(sku_id, []).append(float(price))

    db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.run_date == today
    ).delete(synchronize_session=False)

    score_maps: list[dict] = []
    for sku_id, prices in by_sku.items():
        prod = products.get(sku_id)
        if prod is None or not prices:
            continue
        ref_price, used, excluded, reasons = ce.calculate_reference_price(prices)
        if ref_price is None or used == 0:
            continue

        own = float(prod.current_price) if prod.current_price else None
        price_index = round(own / ref_price, 4) if own and ref_price else None

        avg = mean(prices)
        cv = (pstdev(prices) / avg) if avg > 0 and len(prices) > 1 else 0.0

        sub = {
            "product_comparability": 0.9,  # feed-koppeling (GTIN of itemGroupId) → hoge vergelijkbaarheid
            "price_sensitivity": _clamp(cv * 2.0),
            "substitution": 0.0,
            "competitor_relevance": _clamp(used / 8.0),
            "competitor_price_reliability": _clamp(used / (used + excluded)) if (used + excluded) else 0.0,
            "basket_dependency": 0.0,
            "strategic_importance": _clamp((price_index - 0.9) * 2.0) if price_index else 0.0,
        }
        weights = ce.CATEGORY_WEIGHTS.get(prod.category or "", ce.CATEGORY_WEIGHTS["default"])
        pcis = round(sum(sub[k] * weights.get(k, 0.0) for k in sub), 4)

        score_maps.append({
            "sku_id": sku_id, "run_date": today,
            "product_comparability_score": sub["product_comparability"],
            "price_sensitivity_score": sub["price_sensitivity"],
            "substitution_score": sub["substitution"],
            "competitor_relevance_score": sub["competitor_relevance"],
            "competitor_price_reliability_score": sub["competitor_price_reliability"],
            "basket_dependency_score": sub["basket_dependency"],
            "strategic_importance_score": sub["strategic_importance"],
            "pcis_score": pcis,
            "competition_class": ce.get_competition_class(pcis),
            "reference_price": round(ref_price, 4),
            "price_index": price_index,
            "competitors_used": used,
            "competitors_excluded": excluded,
            "excluded_reasons": reasons or None,
        })

    for chunk in _chunks(score_maps):
        db.bulk_insert_mappings(models.SkuCompetitionScore, chunk)
    db.commit()
    return len(score_maps)


def build_ai_matches(db: Session) -> int:
    """
    Bouw AI-matchresultaten uit de PriceShape-feed van vandaag.

    In de feed is elke concurrent-regel al gekoppeld aan onze SKU via de GTIN
    (sku_id == GTIN). Dat is per definitie een exacte EAN-match, dus elk
    vendor-aanbod levert één AiMatchResult van het type "Exact" met
    confidence 1.0. Bestaande rijen van vandaag worden vervangen zodat de
    matching de actuele feed weerspiegelt.
    """
    today = date.today()

    products = {
        p.sku_id: p for p in db.query(
            models.DimProduct.sku_id,
            models.DimProduct.current_price,
            models.DimProduct.ean,
        ).all()
    }

    rows = db.query(
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
        models.FactCompetitorPriceDaily.url,
    ).filter(models.FactCompetitorPriceDaily.date == today).all()

    # Bewaar analistenbeoordelingen: een eerder goed-/afgekeurd paar behoudt
    # zijn status ook wanneer de matches uit de verse feed worden herbouwd.
    review_status: dict[tuple[str, str], str] = {
        (r.own_sku_id, r.competitor_name): r.status
        for r in db.query(
            models.AiMatchResult.own_sku_id,
            models.AiMatchResult.competitor_name,
            models.AiMatchResult.status,
        ).filter(models.AiMatchResult.status.in_(["APPROVED", "REJECTED"])).all()
    }

    db.query(models.AiMatchResult).filter(
        models.AiMatchResult.run_date == today
    ).delete(synchronize_session=False)

    matches: list[dict] = []
    for sku_id, naam, price, url in rows:
        if not naam or price is None:
            continue
        prod = products.get(sku_id)
        own = float(prod.current_price) if prod and prod.current_price else None
        comp = float(price)
        diff_pct = round((own - comp) / comp * 100, 2) if own and comp > 0 else None
        ean = prod.ean if prod else None
        # De feed koppelt op itemGroupId wanneer er geen GTIN/EAN aanwezig is
        # (standaard PriceShape-exportfeed). ean_match wordt alleen True gezet
        # als het product daadwerkelijk een EAN heeft; anders is de koppeling
        # via itemGroupId (ook een exacte feed-koppeling, maar geen EAN-match).
        has_ean = bool(ean)
        if has_ean:
            explanation = (
                f"Exacte EAN-koppeling uit de PriceShape-feed: aanbod van {naam} "
                f"is gekoppeld op EAN {ean}."
            )
        else:
            explanation = (
                f"Feed-koppeling via itemGroupId ({sku_id}): aanbod van {naam} "
                f"is door PriceShape aan dit product gekoppeld (feed bevat geen GTIN)."
            )
        matches.append({
            "own_sku_id": sku_id,
            "competitor_name": naam,
            "competitor_sku": ean,
            "competitor_url": url,
            "match_type": "Exact",
            "confidence": 1.0,
            "explanation_nl": explanation,
            "ean_match": has_ean,
            "mpn_match": False,
            "oem_match": False,
            "brand_match": False,
            "product_type_match": True,
            "price_segment_match": True,
            "competitor_price": comp,
            "own_price": own,
            "price_diff_pct": diff_pct,
            "status": review_status.get((sku_id, naam), "PENDING"),
            "run_date": today,
        })

    for chunk in _chunks(matches):
        db.bulk_insert_mappings(models.AiMatchResult, chunk)
    db.commit()
    return len(matches)
