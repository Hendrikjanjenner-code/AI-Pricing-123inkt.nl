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
                "brand": _brand_from_title(title),
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

    # Vooraf opgehaalde body (bijv. bulk-load van schijf): parse gebufferd.
    if content is not None:
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


def _normalize_flat(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fallback voor niet-JSON feeds: platte, ge-unneste rijen (alias-gebaseerd)."""
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
                "brand": _brand_from_title(title), "category": top, "subcategory": leaf,
                "product_group": _s(r.get("itemgroupid")) or None,
                "current_price": _f(r.get("priceinclvat")),
                "price_incl_vat": _f(r.get("priceinclvat")),
                "cost_price": _f(r.get("costpriceexclvat")),
                "strategy_type": _DEFAULT_STRATEGY, "lifecycle_status": "active",
                "is_active": True, "import_source": SOURCE_NAME, "data_quality_score": 1.0,
            }
        domain = _s(r.get("domain") or r.get("competitor") or r.get("retailer"))
        price = _f(r.get("price") or r.get("competitor_price"))
        if domain and price is not None:
            comp_rows.append({
                "sku_id": gtin, "competitor_name": domain[:255], "price": price,
                "url": _s(r.get("producturl") or r.get("url")) or None,
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
    catalog, comp_rows = _read_feed(db, content=content, content_type=content_type)

    # Veiligheidsklep: een lege feed (netwerkhik, verlopen token, kapotte export)
    # mag NOOIT de bestaande dagdata wissen. Zonder producten én zonder
    # concurrentprijzen breken we af vóór welke delete dan ook, zodat de app
    # blijft draaien op de laatst-goede data ("never break").
    if not catalog and not comp_rows:
        raise ValueError(
            "PriceShape feed leverde 0 producten en 0 concurrentprijzen op — "
            "sync afgebroken om bestaande data te beschermen (laatst-goede data blijft staan)."
        )

    # 1. Producten: splits in nieuw vs bestaand.
    existing_ids = {row[0] for row in db.query(models.DimProduct.sku_id).all()}
    to_insert = [p for p in catalog if p["sku_id"] not in existing_ids]
    to_update = [p for p in catalog if p["sku_id"] in existing_ids]

    for chunk in _chunks(to_insert):
        db.bulk_insert_mappings(models.DimProduct, chunk)
    if to_update:
        upd = [{
            "sku_id": p["sku_id"], "product_name": p["product_name"], "brand": p["brand"],
            "category": p["category"], "subcategory": p["subcategory"],
            "product_group": p["product_group"], "current_price": p["current_price"],
            "price_incl_vat": p["price_incl_vat"], "cost_price": p["cost_price"],
            "lifecycle_status": "active", "is_active": True, "import_source": source,
        } for p in to_update]
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
    } for r in comp_rows if r["sku_id"] in known]
    if comp_maps:
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.date == today,
            models.FactCompetitorPriceDaily.source == source,
        ).delete(synchronize_session=False)
        for chunk in _chunks(comp_maps):
            db.bulk_insert_mappings(models.FactCompetitorPriceDaily, chunk)
        db.commit()
    else:
        logger.warning(
            "Feed-sync: 0 concurrentprijzen ontvangen — bestaande concurrent-"
            "snapshot van vandaag blijft behouden (niet gewist)."
        )

    return {
        "products_new": len(to_insert),
        "products_updated": len(to_update),
        "products_total": len(catalog),
        "own_prices": len(price_maps),
        "competitor_rows": len(comp_maps),
    }


# ── PCIS-scoring uit echte concurrentprijzen ────────────────────────────────
def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_competition(db: Session) -> int:
    """Bereken SkuCompetitionScore per SKU uit de concurrentprijzen van vandaag."""
    today = date.today()

    products = {
        p.sku_id: p for p in db.query(
            models.DimProduct.sku_id, models.DimProduct.current_price,
            models.DimProduct.category, models.DimProduct.shop_id,
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
        models.FactCompetitorPriceDaily.shop_id,
    ).filter(models.FactCompetitorPriceDaily.date == today).all()
    for sku_id, competitor_name, price, f_shop in rows:
        if price is None or (sku_id, competitor_name) in rejected:
            continue
        prod = products.get(sku_id)
        # Alleen factrijen waarvan de shop overeenkomt met de eigenaar-shop
        # van het product (mis-scoped rijen negeren).
        if prod is None or (f_shop or 1) != (prod.shop_id or 1):
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
            "product_comparability": 0.9,  # GTIN-match → hoge vergelijkbaarheid
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
            models.DimProduct.shop_id,
        ).all()
    }

    rows = db.query(
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
        models.FactCompetitorPriceDaily.url,
        models.FactCompetitorPriceDaily.shop_id,
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
    for sku_id, naam, price, url, f_shop in rows:
        if not naam or price is None:
            continue
        prod = products.get(sku_id)
        # Eigenaar-shop-validatie: factrij moet bij de shop van het product
        # horen, anders geen match (poison/mis-scoped rijen).
        if prod is None or (f_shop or 1) != (prod.shop_id or 1):
            continue
        own = float(prod.current_price) if prod and prod.current_price else None
        comp = float(price)
        diff_pct = round((own - comp) / comp * 100, 2) if own and comp > 0 else None
        ean = prod.ean if prod else None
        matches.append({
            "own_sku_id": sku_id,
            "competitor_name": naam,
            "competitor_sku": ean,
            "competitor_url": url,
            "match_type": "Exact",
            "confidence": 1.0,
            "explanation_nl": (
                f"Exacte GTIN-match uit de PriceShape-feed: aanbod van {naam} "
                f"is gekoppeld op EAN {ean or sku_id}."
            ),
            "ean_match": True,
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
