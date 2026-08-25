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

from sqlalchemy import func, or_ as sa_or
from sqlalchemy.orm import Session

import models
from connectors import priceshape_connector as pc
from engine import competition_engine as ce
from services.domain_normalize import normalize_domain

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


def _chunks(seq: list, size: int | None = None):
    size = size or _CHUNK
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _batches(it, size: int | None = None):
    """Verdeel een willekeurige iterator in lijst-batches van max `size` rijen,
    zodat de pipeline nooit meer dan één batch tegelijk in RAM houdt."""
    size = size or _CHUNK
    buf: list = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


# ── schijf-spool: begrensd RAM voor grote feeds ─────────────────────────────
def _spool_encode(obj):
    """JSON-encoder voor spool-rijen: datetimes verliesvrij als markering."""
    from datetime import datetime as _dt
    if isinstance(obj, _dt):
        return {"__dt__": obj.isoformat()}
    return pc._stringify(obj)


def _spool_decode(d: dict):
    if "__dt__" in d and len(d) == 1:
        parsed = _parse_dt(d["__dt__"])
        return parsed if parsed is not None else d["__dt__"]
    return d


class _RowSpool:
    """
    Schijf-gebufferde rijenverzameling (JSON Lines in een tempbestand).

    Gedraagt zich als een her-itereerbare lijst van dicts (len + meerdere
    sequentiële iteraties), maar houdt nooit meer dan één rij tegelijk in
    het geheugen. Hiermee blijft het piekgeheugen van de feed-ingest begrensd,
    ongeacht hoe groot de feed wordt. Niet bedoeld voor gelijktijdige
    iteraties (de ingest-passes zijn strikt sequentieel).
    """

    def __init__(self):
        import tempfile
        self._f = tempfile.TemporaryFile(
            mode="w+", encoding="utf-8", prefix="feed-spool-")
        self._n = 0

    def append(self, row: dict) -> None:
        self._f.write(json.dumps(row, default=_spool_encode) + "\n")
        self._n += 1

    def __len__(self) -> int:
        return self._n

    def __iter__(self):
        self._f.flush()
        self._f.seek(0)
        for line in self._f:
            if line.strip():
                yield json.loads(line, object_hook=_spool_decode)

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass


def _close_rows(*row_sources) -> None:
    for src in row_sources:
        if isinstance(src, _RowSpool):
            src.close()


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
def _normalize_stream(records, catalog_sink, comp_sink) -> None:
    """
    Zet ruwe JSON-productrecords (lijst of iterator) om naar catalogus- en
    concurrentrijen en schrijf ze direct naar de sinks (lijst of _RowSpool).
    Semantiek identiek aan de klassieke lijst-normalisatie: eerste voorkomen
    van een gtin wint; vendors per record gededupliceerd op domein.
    """
    seen_gtins: set[str] = set()

    for rec in records:
        if not isinstance(rec, dict):
            continue
        gtin = _s(rec.get("gtin"))
        if not gtin:
            continue

        if gtin not in seen_gtins:
            seen_gtins.add(gtin)
            title = _s(rec.get("productTitle")) or gtin
            top, leaf = _split_category(rec.get("PPC_ProductType"))
            catalog_sink.append({
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
            })

        vendors = pc._find_vendor_list(rec) or []
        seen_domains: set[str] = set()
        for v in vendors:
            if not isinstance(v, dict):
                continue
            domain_raw = _s(v.get("domain") or v.get("name"))
            domain = normalize_domain(domain_raw)
            price = _f(v.get("price"))
            if not domain or price is None or domain in seen_domains:
                continue
            seen_domains.add(domain)
            comp_sink.append({
                "sku_id": gtin,
                "competitor_name": domain[:255],
                "competitor_alias": domain_raw if domain_raw != domain else None,
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
                    ({} if domain_raw == domain else {"_domain_alias": domain_raw})
                    | (_raw_leftovers(v, _VENDOR_MAPPED_KEYS) or {}) or None,
                    {
                        "_domain_full": (domain, 255),
                        "_name_full": (_s(v.get("name")), 255),
                        "_currency_full": (_s(_first(v, "currency", "valuta")), 3),
                    },
                ),
            })


def _normalize(records) -> tuple[list[dict], list[dict]]:
    """Klassieke lijst-variant van de normalisatie (kleine feeds, tests)."""
    catalog: list[dict] = []
    comp_rows: list[dict] = []
    _normalize_stream(records, catalog, comp_rows)
    return catalog, comp_rows


def _iter_csv_rows(path: str):
    """
    Itereer rij-dicts (kleingeschreven sleutels, string-waarden) uit een op
    schijf staand CSV-bestand ZONDER het volledige bestand in RAM te laden.
    UTF-8(-BOM) wordt streamend gelezen; alleen bij een legacy-encoding
    (cp1252/mac-roman/latin-1, in de praktijk kleine handmatige exports) valt
    dit terug op de gebufferde decoder van de import-engine.
    """
    import csv

    # Delimiter-sniff op de kop van het bestand (zelfde aanpak als de
    # gebufferde parser in de connector).
    with open(path, "rb") as fb:
        head = fb.read(4096)
    delimiter = ","
    try:
        sample = head.decode("utf-8-sig", "replace").replace("\r\n", "\n").replace("\r", "\n")
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        pass

    def _rows_from(fh):
        reader = csv.DictReader(fh, delimiter=delimiter)
        for row in reader:
            yield {(k or "").strip().lower(): (v or "") for k, v in row.items()}

    # Encoding-keuze in een APARTE pre-pass (chunkgewijs, incrementele decoder,
    # niets in RAM gehouden) VOORDAT er ook maar één rij wordt ge-yield: een
    # decodeerfout halverwege mag nooit tot een tweede parse-pass leiden die
    # eerder ge-yielde rijen dupliceert.
    import codecs
    is_utf8 = True
    dec = codecs.getincrementaldecoder("utf-8")()
    with open(path, "rb") as fb:
        while chunk := fb.read(1 << 20):
            try:
                dec.decode(chunk)
            except UnicodeDecodeError:
                is_utf8 = False
                break
        if is_utf8:
            try:
                dec.decode(b"", final=True)
            except UnicodeDecodeError:
                is_utf8 = False

    if is_utf8:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            yield from _rows_from(fh)
        return

    # Legacy-encoding (cp1252/mac-roman/latin-1): gebufferd decoderen,
    # identiek aan het oude pad — in de praktijk kleine handmatige exports.
    logger.info("Feed-CSV is geen UTF-8 — gebufferde decodering (legacy-encoding).")
    import io
    from engine.import_engine import decode_csv_bytes
    with open(path, "rb") as fb:
        text = decode_csv_bytes(fb.read()).replace("\r\n", "\n").replace("\r", "\n")
    yield from _rows_from(io.StringIO(text))


def _spool_csv_file(path: str) -> tuple["_RowSpool", "_RowSpool"]:
    """
    Normaliseer een CSV-feedbestand streamend naar schijf-spools. Kiest op de
    eerste rij tussen het brede exportformaat (vendor_N-kolommen — de standaard
    PriceShape-feed) en de platte alias-normalisatie, identiek aan de
    lijstgebaseerde `_normalize_flat`.
    """
    import itertools

    cat_spool, comp_spool = _RowSpool(), _RowSpool()
    try:
        rows = _iter_csv_rows(path)
        first = next(rows, None)
        if first is None:
            return cat_spool, comp_spool
        chained = itertools.chain([first], rows)
        if any(_WIDE_VENDOR_RE.match(k) for k in first.keys()):
            _normalize_wide_csv_stream(chained, cat_spool, comp_spool)
        else:
            _normalize_flat_stream(chained, cat_spool, comp_spool)
        return cat_spool, comp_spool
    except Exception:
        _close_rows(cat_spool, comp_spool)
        raise


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
        # Batchgewijs: normaliseer de gestreamde records rechtstreeks naar
        # schijf-spools (JSON Lines) i.p.v. volledige lijsten in RAM — de
        # ingest-pipeline verwerkt de spools daarna in begrensde batches.
        cat_spool, comp_spool = _RowSpool(), _RowSpool()
        try:
            logger.info("Feed-parse: streaming JSON (ijson) → schijf-spool.")
            _normalize_stream(pc.stream_json_records(cfg["feed_url"]),
                              cat_spool, comp_spool)
            return cat_spool, comp_spool
        except pc.NotStreamable:
            _close_rows(cat_spool, comp_spool)
            logger.info(
                "Feed is geen top-level JSON-array — val terug op gebufferd lezen."
            )
        except Exception:
            _close_rows(cat_spool, comp_spool)
            raise

    # Fallback: download STREAMEND naar schijf (nooit de volledige body in
    # RAM) en parse vanaf het bestand. CSV — het formaat van de standaard
    # PriceShape-exportfeed — wordt rij-voor-rij naar schijf-spools
    # genormaliseerd; alleen de zeldzame XML/object-wrapper-JSON-varianten
    # worden nog gebufferd geparsed (vanaf schijf, dus zonder dubbele
    # bytes-kopie in RAM).
    logger.info("Feed-parse: streaming download naar schijf (niet-streambaar JSON).")
    path, content_type = pc.fetch_feed_to_file(cfg["feed_url"])
    try:
        with open(path, "rb") as fb:
            head = fb.read(4096)
        fmt = pc._detect_feed_format(head, content_type, cfg["feed_format"])
        if fmt == "csv":
            logger.info("Feed-parse: CSV rij-voor-rij vanaf schijf → schijf-spool.")
            return _spool_csv_file(path)
        # XML / object-wrapper JSON: gebufferd parsen vanaf schijf.
        logger.info("Feed-parse: gebufferd lezen vanaf schijf (formaat=%s).", fmt)
        with open(path, "rb") as fb:
            content = fb.read()
        return _parse_content(content, content_type, fmt)
    finally:
        pc._cleanup_file(path)


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
    """Klassieke lijst-variant van de brede-CSV-normalisatie (kleine feeds, tests)."""
    catalog: list[dict] = []
    comp_rows: list[dict] = []
    _normalize_wide_csv_stream(rows, catalog, comp_rows)
    return catalog, comp_rows


def _normalize_wide_csv_stream(rows, catalog_sink, comp_sink) -> None:
    """
    Normaliseer het BREDE PriceShape CSV-exportformaat: één product per rij,
    concurrenten in kolomgroepen `vendor_N <veld>` (domain, price, stockStatus,
    productUrl, priceWithShipping, …). Dit is het formaat dat de standaard
    export-feed (public.app.priceshape.io …/export/…) daadwerkelijk levert:
    geen gtin-kolom — `itemGroupId` is de productsleutel.

    Streamvariant: `rows` mag een generator zijn; product- en concurrentrijen
    worden per rij naar de sinks geschreven (lijst of `_RowSpool`), zodat de
    volledige feed nooit als lijst in RAM staat. Semantiek is identiek aan de
    oude lijstvariant: eerste voorkomen van een sku wint (`seen_skus`), en
    offers worden feedbreed gededupliceerd op (sku, domein).
    """
    seen_skus: set[str] = set()
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

        if sku not in seen_skus:
            seen_skus.add(sku)
            title = _s(base.get("name") or base.get("producttitle")) or sku
            top, leaf = _split_category(base.get("ppc_producttype") or base.get("category"))
            raw = {k: v for k, v in base.items()
                   if _s(v) and k not in _WIDE_PRODUCT_MAPPED}
            catalog_sink.append({
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
            })

        for idx in sorted(vendors):
            v = vendors[idx]
            domain_raw = _s(v.get("domain"))
            domain = normalize_domain(domain_raw)
            price = _f(v.get("price"))
            if not domain or price is None:
                continue
            if (sku, domain) in seen_offers:
                continue
            seen_offers.add((sku, domain))
            vraw = {k: val for k, val in v.items()
                    if _s(val) and k not in _WIDE_VENDOR_MAPPED}
            if domain_raw != domain:
                vraw["_domain_alias"] = domain_raw
            comp_sink.append({
                "sku_id": sku, "competitor_name": domain[:255], "price": price,
                "competitor_alias": domain_raw if domain_raw != domain else None,
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


def _normalize_flat(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fallback voor niet-JSON feeds: platte, ge-unneste rijen (alias-gebaseerd)."""
    # Breed exportformaat (vendor_N-kolommen)? Dan de speciale wide-normalisatie.
    if rows and any(_WIDE_VENDOR_RE.match(k) for k in rows[0].keys()):
        return _normalize_wide_csv(rows)
    catalog: list[dict] = []
    comp_rows: list[dict] = []
    _normalize_flat_stream(rows, catalog, comp_rows)
    return catalog, comp_rows


def _normalize_flat_stream(rows, catalog_sink, comp_sink) -> None:
    """
    Streamvariant van de platte normalisatie: `rows` mag een generator zijn;
    rijen gaan direct naar de sinks (lijst of `_RowSpool`). Semantiek identiek
    aan de oude lijstvariant (eerste gtin wint).
    """
    seen_gtins: set[str] = set()
    for r in rows:
        gtin = _s(r.get("gtin") or r.get("ean") or r.get("barcode"))
        if not gtin:
            continue
        if gtin not in seen_gtins:
            seen_gtins.add(gtin)
            title = _s(r.get("producttitle") or r.get("product_name") or r.get("title")) or gtin
            top, leaf = _split_category(r.get("ppc_producttype") or r.get("category"))
            catalog_sink.append({
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
            })
        domain_raw = _s(r.get("domain") or r.get("competitor") or r.get("retailer"))
        domain = normalize_domain(domain_raw)
        price = _f(r.get("price") or r.get("competitor_price"))
        if domain and price is not None:
            comp_sink.append({
                "sku_id": gtin, "competitor_name": domain[:255], "price": price,
                "competitor_alias": domain_raw if domain_raw != domain else None,
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


# ── persisteren ─────────────────────────────────────────────────────────────
def ingest_feed(db: Session, source: str = SOURCE_NAME,
                content: bytes | None = None, content_type: str = "",
                shop_id: int = 1) -> dict:
    """Lees de feed volledig in en persisteer catalogus + prijzen + concurrenten.

    `content` kan een reeds opgehaalde feed-body zijn (bijv. van schijf), zodat
    een eenmalige bulk-load de trage download kan overslaan.

    `shop_id` bepaalt voor welke winkel deze sync draait. ALLE replace-deletes
    en alle geschreven rijen zijn strikt tot die winkel beperkt: een sync voor
    winkel A mag nooit producten, dagprijzen of concurrentrijen van winkel B
    wissen of overschrijven (twee-winkel-isolatie).
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

    # Centrale bescherming tegen te lange feedwaarden: kap ALLE begrensde
    # stringkolommen af op de kolombreedte (origineel blijft bewaard in
    # raw_attributes) zodat één afwijkende waarde nooit de complete
    # catalogus-import laat crashen op "value too long for varchar(N)".
    clamp_warnings: list[str] = []

    try:
        return _ingest_rows(db, source, catalog, comp_rows, today, settings,
                            shop_id, clamp_warnings)
    finally:
        # Schijf-spools (streaming pad) altijd opruimen.
        _close_rows(catalog, comp_rows)


def _ingest_rows(db: Session, source: str, catalog, comp_rows, today,
                 settings, shop_id: int, clamp_warnings: list[str]) -> dict:
    """
    Batchgewijze persistentie van genormaliseerde catalogus- + concurrentrijen.

    `catalog` en `comp_rows` zijn her-itereerbare rijenbronnen (lijsten voor
    kleine/gebufferde feeds, `_RowSpool` voor het streaming pad). De pipeline
    verwerkt ze in meerdere sequentiële passes met batches van max `_CHUNK`
    rijen, zodat het piekgeheugen begrensd blijft — met exact dezelfde
    replace-snapshot-semantiek en veiligheidskleppen als de klassieke
    lijst-implementatie (empty-feed-guard vóór elke delete, shop-scoping,
    sku-quarantaine, importinstellingen als no-op).
    """
    from services import import_settings as imps

    # Pass 0 (alleen lezen): sku-inventarisatie + quarantaine van te lange
    # sku's. Identiteit (sku_id, primary key) mag NOOIT afgekapt worden: twee
    # verschillende te lange sku's zouden na truncatie op elkaar (of op een
    # bestaand product) kunnen mappen en zo andermans rijen overschrijven of
    # de replace-deletes corrumperen.
    _sku_limit = _string_limits(models.DimProduct)["sku_id"]
    catalog_skus: set[str] = set()
    oversized: set[str] = set()
    for p in catalog:
        sku = p["sku_id"]
        if len(sku) > _sku_limit:
            oversized.add(sku)
        else:
            catalog_skus.add(sku)
    if oversized:
        example = next(iter(oversized))
        clamp_warnings.append(
            f"{len(oversized)} product(en) overgeslagen: sku/gtin langer dan "
            f"{_sku_limit} tekens (identiteit wordt nooit afgekapt). "
            f"Voorbeeld — {example[:80]}…"
        )
        logger.warning("Feed-ingest: %s", clamp_warnings[-1])

    _identity = frozenset({"sku_id"})
    prod_hits: dict[str, dict] = {}
    comp_hits: dict[str, dict] = {}

    # Bestaand/vreemd (alleen lezen — er is nog niets gewijzigd):
    # producten van andere winkels mogen nooit door deze sync geraakt worden.
    existing_ids = {row[0] for row in db.query(models.DimProduct.sku_id).filter(
        models.DimProduct.shop_id == shop_id).all()}
    foreign_ids: set[str] = set()
    _sku_list = sorted(catalog_skus)
    for i in range(0, len(_sku_list), 10_000):
        foreign_ids.update(row[0] for row in db.query(models.DimProduct.sku_id).filter(
            models.DimProduct.sku_id.in_(_sku_list[i:i + 10_000]),
            models.DimProduct.shop_id != shop_id).all())
    if foreign_ids:
        logger.warning(
            "Feed-sync (shop %s): %d sku's overgeslagen omdat ze al bij een "
            "andere winkel horen.", shop_id, len(foreign_ids))
    known = (catalog_skus - foreign_ids) | existing_ids

    # Uitgevinkte onderdelen zijn een echte no-op: de betreffende kolommen
    # worden niet geschreven, zodat bestaande waarden behouden blijven.
    own_on = imps.component_enabled(settings, "own_prices")
    cost_on = imps.component_enabled(settings, "cost_prices")
    attrs_on = imps.component_enabled(settings, "extra_attributes")
    avail_on = imps.component_enabled(settings, "availability")
    comp_on = imps.component_enabled(settings, "competitor_prices")

    # Pass 1 (alleen lezen/filteren, GEEN databasewrites): concurrentrijen
    # batchgewijs clampen + importselectie toepassen en de te schrijven rijen
    # naar een gefilterde spool wegschrijven. Zo zijn alle aantallen bekend
    # vóórdat ook maar één delete plaatsvindt (empty-feed-guard hieronder).
    skipped_competitor_rows = 0
    comp_after_settings = 0  # na importselectie, vóór known/foreign-filter
    feed_variants: set[str] = set()
    feed_canonical: set[str] = set()
    alias_by_canon: dict[str, set[str]] = {}
    written_names: set[str] = set()
    offer_sku_ids: set[str] = set()
    offer_names: set[str] = set()
    comp_kept = _RowSpool()
    try:
        for batch in _batches(r for r in comp_rows
                              if r["sku_id"] not in oversized):
            _clamp_batch(models.FactCompetitorPriceDaily, batch, comp_hits,
                         skip_fields=_identity)
            for r in batch:
                if settings["disabled_competitors"] and imps.competitor_disabled(
                        settings, r["competitor_name"]):
                    skipped_competitor_rows += 1
                    continue
                if not comp_on:
                    skipped_competitor_rows += 1
                    continue
                comp_after_settings += 1
                # Reconciliatie-basis: ná de importselectie — unieke ruwe
                # schrijfwijzen versus canonieke domeinen.
                feed_variants.add(
                    (r.get("competitor_alias") or r["competitor_name"]).lower())
                feed_canonical.add(r["competitor_name"])
                if r.get("competitor_alias"):
                    alias_by_canon.setdefault(r["competitor_name"], set()).add(
                        r["competitor_alias"])
                if r["sku_id"] not in known:
                    continue
                written_names.add(r["competitor_name"])
                if r.get("in_stock") is not None or r.get("delivery_days") is not None:
                    offer_sku_ids.add(r["sku_id"])
                    offer_names.add(r["competitor_name"])
                comp_kept.append(r)

        return _ingest_write(
            db, source, catalog, today, settings, shop_id, clamp_warnings,
            catalog_skus=catalog_skus, oversized=oversized,
            existing_ids=existing_ids, foreign_ids=foreign_ids,
            prod_hits=prod_hits, comp_hits=comp_hits, _identity=_identity,
            own_on=own_on, cost_on=cost_on, attrs_on=attrs_on, avail_on=avail_on,
            skipped_competitor_rows=skipped_competitor_rows,
            comp_after_settings=comp_after_settings,
            feed_variants=feed_variants, feed_canonical=feed_canonical,
            alias_by_canon=alias_by_canon, written_names=written_names,
            offer_sku_ids=offer_sku_ids, offer_names=offer_names,
            comp_kept=comp_kept,
        )
    finally:
        comp_kept.close()


def _ingest_write(db: Session, source: str, catalog, today, settings,
                  shop_id: int, clamp_warnings: list[str], *,
                  catalog_skus, oversized, existing_ids, foreign_ids,
                  prod_hits, comp_hits, _identity,
                  own_on, cost_on, attrs_on, avail_on,
                  skipped_competitor_rows, comp_after_settings,
                  feed_variants, feed_canonical, alias_by_canon,
                  written_names, offer_sku_ids, offer_names,
                  comp_kept) -> dict:
    from services import import_settings as imps

    # Veiligheidsklep: een lege feed (netwerkhik, verlopen token, kapotte export)
    # mag NOOIT de bestaande dagdata wissen. Zonder producten én zonder
    # concurrentprijzen breken we af vóór welke delete dan ook, zodat de app
    # blijft draaien op de laatst-goede data ("never break").
    if not catalog_skus and not comp_after_settings:
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

    # 1. Producten: batchgewijs clampen, onderdelen-toggles toepassen en
    # splitsen in nieuw vs bestaand — ALLEEN binnen deze winkel. Sku's die al
    # bij een ANDERE winkel horen worden volledig overgeslagen: de sku_id is
    # de primary key, dus een insert zou crashen en een update zou de rij van
    # die andere winkel overschrijven.
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

    def _prepared_products():
        """Eén logische pass over de catalogus: quarantaine/vreemde sku's
        overslaan, clampen (geaggregeerde hits) en toggles toepassen."""
        for batch in _batches(p for p in catalog
                              if p["sku_id"] not in oversized
                              and p["sku_id"] not in foreign_ids):
            _clamp_batch(models.DimProduct, batch, prod_hits,
                         skip_fields=_identity)
            for p in batch:
                if not own_on:
                    p["current_price"] = None  # alleen gebruikt bij NIEUWE producten (insert)
                    p["price_incl_vat"] = None
                if not cost_on:
                    p["cost_price"] = None  # idem: updates laten de kolom ongemoeid
                if not attrs_on:
                    p["raw_attributes"] = None
                p["shop_id"] = shop_id
            yield batch

    products_new = products_updated = products_total = 0
    own_price_count = 0
    cats: set[tuple] = set()
    for batch in _prepared_products():
        products_total += len(batch)
        ins = [p for p in batch if p["sku_id"] not in existing_ids]
        upd = [_upd_map(p) for p in batch if p["sku_id"] in existing_ids]
        products_new += len(ins)
        products_updated += len(upd)
        for p in batch:
            if p["category"]:
                cats.add((p["category"], p["subcategory"]))
            if own_on and p["current_price"] is not None:
                own_price_count += 1
        if ins:
            db.bulk_insert_mappings(models.DimProduct, ins)
        if upd:
            db.bulk_update_mappings(models.DimProduct, upd)
    db.commit()

    # 2. Categorieën + strategie-mapping (idempotent).
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
    # Batchgewijs: het aantal vervangende prijzen (`own_price_count`) is in de
    # productenpass geteld, dus de delete-guard beslist vóór de eerste insert.
    own_prices_written = 0
    if not own_on:
        logger.info("Feed-sync: eigen prijzen uitgevinkt in importinstellingen — overgeslagen.")
    elif own_price_count:
        existing_costs: dict = {}
        if not cost_on:
            # Kostprijzen uitgevinkt: bestaande kostprijs van vandaag behouden in
            # de vervangende dagprijsrijen (replace mag niets wissen).
            existing_costs = dict(db.query(
                models.FactPriceDaily.sku_id, models.FactPriceDaily.cost_price,
            ).filter(models.FactPriceDaily.date == today,
                     models.FactPriceDaily.shop_id == shop_id).all())
        # Replace-delete strikt tot DEZE winkel beperkt: dagprijzen van andere
        # winkels blijven altijd staan.
        db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.date == today,
            models.FactPriceDaily.shop_id == shop_id,
        ).delete(synchronize_session=False)
        for batch in _batches(p for p in catalog
                              if p["sku_id"] not in oversized
                              and p["sku_id"] not in foreign_ids
                              and p["current_price"] is not None):
            maps = [{
                "date": today, "sku_id": p["sku_id"], "price": p["current_price"],
                "cost_price": (p["cost_price"] if cost_on
                               else existing_costs.get(p["sku_id"])),
                "shop_id": shop_id,
            } for p in batch]
            db.bulk_insert_mappings(models.FactPriceDaily, maps)
            own_prices_written += len(maps)
        db.commit()
    else:
        logger.warning(
            "Feed-sync: 0 eigen dagprijzen ontvangen — bestaande dagprijzen "
            "van vandaag blijven behouden (niet gewist)."
        )

    # 4. Concurrentprijzen — vervang die van deze bron voor vandaag.
    # Zelfde bescherming: zonder vervangende concurrentprijzen NIET wissen, zodat
    # een gedeeltelijke feed-uitval (wel producten, geen concurrenten) de
    # bestaande concurrent-snapshot van vandaag niet vernietigt. De gefilterde
    # spool (`comp_kept`, zonder DB-writes opgebouwd in pass 1) levert het
    # aantal vervangende rijen vóór de delete.
    existing_today: dict = {}
    if len(comp_kept) and (not avail_on or not attrs_on):
        # Uitgevinkt onderdeel = no-op: neem de bestaande waarden van vandaag
        # over in de vervangende rijen, zodat de replace niets wist.
        existing_today = {
            (rec.sku_id, rec.competitor_name): rec
            for rec in db.query(models.FactCompetitorPriceDaily).filter(
                models.FactCompetitorPriceDaily.date == today,
                models.FactCompetitorPriceDaily.source == source,
                models.FactCompetitorPriceDaily.shop_id == shop_id,
            ).all()
        }

    def _to_comp_map(r: dict) -> dict:
        m = {
            "date": today, "sku_id": r["sku_id"], "competitor_name": r["competitor_name"],
            "price": r["price"], "url": r["url"], "source": source, "shop_id": shop_id,
            "in_stock": r.get("in_stock"), "delivery_days": r.get("delivery_days"),
            "currency": r.get("currency"), "vendor_name": r.get("vendor_name"),
            "observed_at": r.get("observed_at"), "raw_attributes": r.get("raw_attributes"),
        }
        if not avail_on or not attrs_on:
            prev = existing_today.get((m["sku_id"], m["competitor_name"]))
            if not avail_on:
                m["in_stock"] = prev.in_stock if prev else None
                m["delivery_days"] = prev.delivery_days if prev else None
            if not attrs_on:
                m["raw_attributes"] = prev.raw_attributes if prev else None
        return m

    competitor_rows_written = 0
    if len(comp_kept):
        # Volledige vervanging van de snapshot van vandaag (normale pad), maar
        # uitgevinkte concurrenten behouden hun bestaande data (worden nooit
        # gewist door een sync waarin ze niet meegenomen worden).
        # Replace-delete strikt tot DEZE winkel beperkt: concurrentrijen van
        # andere winkels (zelfde datum en bron) blijven altijd staan.
        delete_q = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.date == today,
            models.FactCompetitorPriceDaily.source == source,
            models.FactCompetitorPriceDaily.shop_id == shop_id,
        )
        disabled = settings["disabled_competitors"]
        if disabled:
            delete_q = delete_q.filter(
                ~func.lower(models.FactCompetitorPriceDaily.competitor_name).in_(disabled)
            )
        delete_q.delete(synchronize_session=False)
        for batch in _batches(comp_kept):
            db.bulk_insert_mappings(
                models.FactCompetitorPriceDaily, [_to_comp_map(r) for r in batch])
            competitor_rows_written += len(batch)
        db.commit()
    else:
        logger.warning(
            "Feed-sync: 0 concurrentprijzen ontvangen — bestaande concurrent-"
            "snapshot van vandaag blijft behouden (niet gewist)."
        )

    # 5. Beschikbaarheid van concurrenten (fact_competitor_offer_daily) — alleen
    # wanneer het onderdeel aan staat én de feed daadwerkelijk voorraaddata levert.
    # Snapshot vóór _persist_offers: die upsert vult het register alvast,
    # waardoor 'nieuw' anders ten onrechte als 'gematcht' zou tellen.
    _recon_names = sorted(feed_canonical | written_names)
    pre_existing: set[str] = set()
    for _chunk in (_recon_names[i:i + 1000]
                   for i in range(0, len(_recon_names), 1000)):
        pre_existing.update(
            n for (n,) in db.query(models.DimCompetitor.competitor_name)
            .filter(models.DimCompetitor.competitor_name.in_(_chunk)).all())

    offers_written = 0
    if avail_on:
        offers_written = _persist_offers(
            db, today, (_to_comp_map(r) for r in comp_kept),
            offer_names=offer_names, offer_sku_ids=offer_sku_ids)

    # 6. Concurrentenregister + reconciliatie-samenvatting.
    reconciliation = _reconcile_competitors(
        db, today, written_names, competitor_rows_written,
        feed_variants, feed_canonical, alias_by_canon, pre_existing)
    if reconciliation:
        clamp_warnings.insert(0, (
            "Concurrent-reconciliatie: "
            f"{reconciliation['feed_unique']} uniek in feed, "
            f"{reconciliation['matched']} gematcht, "
            f"{reconciliation['new']} nieuw, "
            f"{reconciliation['rows_written']} prijsrijen bijgewerkt, "
            f"{reconciliation['duplicates_prevented']} duplicaatvarianten voorkomen."
        ))

    # Geaggregeerde clamp-waarschuwingen (één per kolom, over alle batches).
    _emit_clamp_warnings(models.DimProduct, prod_hits, clamp_warnings,
                         skip_fields=_identity)
    _emit_clamp_warnings(models.FactCompetitorPriceDaily, comp_hits,
                         clamp_warnings, skip_fields=_identity)

    return {
        "competitor_reconciliation": reconciliation,
        "products_new": products_new,
        "products_updated": products_updated,
        "products_total": products_total,
        "own_prices": own_prices_written,
        "competitor_rows": competitor_rows_written,
        "offer_rows": offers_written,
        "skipped_by_settings": skipped_competitor_rows,
        "warnings": clamp_warnings,
    }


def cleanup_vanished_competitors(db: Session, source: str = SOURCE_NAME,
                                 shop_id: int = 1) -> dict:
    """Verwijder historische concurrentprijzen van concurrenten die volledig
    uit de feed verdwenen zijn (volledige-sync-opschoning, feed-modus).

    De feed-ingest vervangt alleen de snapshot van vandaag; concurrenten die
    niet meer in de feed staan behouden daardoor eeuwig hun oude dagrijen.
    Deze opschoning draait alleen bij een volledige sync en verwijdert de
    rijen van vóór vandaag van concurrenten die vandaag géén enkele rij meer
    hebben, strikt beperkt tot deze bron en deze winkel.

    Veiligheidskleppen:
    - Lege snapshot van vandaag → geen opschoning (last-known-good: een
      mislukte/lege feed mag nooit historie wissen).
    - Uitgevinkte concurrenten (importinstellingen) tellen als bewust
      overgeslagen, niet als verdwenen — hun historie blijft staan.
    """
    today = date.today()
    from services import import_settings as imps
    settings = imps.get_settings(db, "priceshape")
    disabled = set(settings.get("disabled_competitors") or [])

    present_today = {
        (name or "").lower()
        for (name,) in db.query(models.FactCompetitorPriceDaily.competitor_name)
        .filter(
            models.FactCompetitorPriceDaily.date == today,
            models.FactCompetitorPriceDaily.source == source,
            models.FactCompetitorPriceDaily.shop_id == shop_id,
        ).distinct().all()
    }
    if not present_today:
        # Geen snapshot van vandaag → sync leverde niets; niets opschonen.
        return {"removed_rows": 0, "removed_competitors": []}

    historical = {
        (name or "").lower(): name
        for (name,) in db.query(models.FactCompetitorPriceDaily.competitor_name)
        .filter(
            models.FactCompetitorPriceDaily.date < today,
            models.FactCompetitorPriceDaily.source == source,
            models.FactCompetitorPriceDaily.shop_id == shop_id,
        ).distinct().all()
    }
    vanished_lower = set(historical) - present_today - disabled
    if not vanished_lower:
        return {"removed_rows": 0, "removed_competitors": []}

    removed = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(
            models.FactCompetitorPriceDaily.date < today,
            models.FactCompetitorPriceDaily.source == source,
            models.FactCompetitorPriceDaily.shop_id == shop_id,
            func.lower(models.FactCompetitorPriceDaily.competitor_name)
            .in_(vanished_lower),
        )
        .delete(synchronize_session=False)
    )

    # Bijbehorende beschikbaarheidsrijen (fact_competitor_offer_daily) van
    # dezelfde bron, beperkt tot SKU's van deze winkel.
    vanished_ids = [
        c.competitor_id
        for c in db.query(models.DimCompetitor)
        .filter(func.lower(models.DimCompetitor.competitor_name).in_(vanished_lower))
        .all()
    ]
    if vanished_ids:
        shop_skus = db.query(models.DimProduct.sku_id).filter(
            models.DimProduct.shop_id == shop_id)
        db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.source == source,
            models.FactCompetitorOfferDaily.competitor_id.in_(vanished_ids),
            models.FactCompetitorOfferDaily.own_sku_id.in_(shop_skus),
        ).delete(synchronize_session=False)
    db.commit()

    names = sorted(historical[low] for low in vanished_lower)
    logger.info(
        "Feed volledige sync: %d historische concurrentprijsrijen opgeschoond "
        "van %d verdwenen concurrent(en): %s",
        removed, len(names), ", ".join(names),
    )
    return {"removed_rows": removed, "removed_competitors": names}


def _persist_offers(db: Session, today: date, comp_maps,
                    offer_names: set[str] | None = None,
                    offer_sku_ids: set[str] | None = None) -> int:
    """
    Schrijf vendor-voorraaddata door naar fact_competitor_offer_daily, zodat het
    bestaande beschikbaarheidsmodel (update_availability) er direct mee kan werken.
    Alleen rijen met een echte voorraad-/levertijdwaarneming worden geschreven;
    zonder zulke data wordt er niets gewist (last-known-good).

    `comp_maps` mag elke (eenmalig te doorlopen) iterator van map-dicts zijn;
    de rijen worden batchgewijs geschreven zodat het geheugen begrensd blijft.
    `offer_names`/`offer_sku_ids` zijn optioneel vooraf berekende sets van
    concurrentnamen en sku's van rijen mét voorraaddata; zonder deze sets wordt
    `comp_maps` gematerialiseerd (klassieke lijst-aanroep).
    """
    if offer_names is None or offer_sku_ids is None:
        comp_maps = [m for m in comp_maps
                     if m.get("in_stock") is not None
                     or m.get("delivery_days") is not None]
        offer_names = {m["competitor_name"] for m in comp_maps}
        offer_sku_ids = {m["sku_id"] for m in comp_maps}
    if not offer_names:
        return 0

    # Concurrentregister bijwerken: domein → competitor_id (idempotent).
    names = offer_names
    existing = {c.competitor_name: c.competitor_id
                for c in db.query(models.DimCompetitor).filter(
                    models.DimCompetitor.competitor_name.in_(names)).all()}
    for name in sorted(names - set(existing)):
        db.add(models.DimCompetitor(competitor_name=name))
    db.flush()
    ids = {c.competitor_name: c.competitor_id
           for c in db.query(models.DimCompetitor).filter(
               models.DimCompetitor.competitor_name.in_(names)).all()}

    # Alleen de eigen (priceshape) rijen van vandaag vervangen voor precies de
    # (SKU, concurrent)-combinaties die opnieuw aangeleverd worden — offers van
    # scrapers, andere shops én uitgevinkte/afwezige concurrenten blijven staan.
    db.query(models.FactCompetitorOfferDaily).filter(
        models.FactCompetitorOfferDaily.date == today,
        models.FactCompetitorOfferDaily.source == "priceshape",
        models.FactCompetitorOfferDaily.own_sku_id.in_(offer_sku_ids),
        models.FactCompetitorOfferDaily.competitor_id.in_(set(ids.values())),
    ).delete(synchronize_session=False)

    written = 0
    def _with_stock():
        for m in comp_maps:
            if m.get("in_stock") is None and m.get("delivery_days") is None:
                continue
            yield {
                "date": today,
                "own_sku_id": m["sku_id"],
                "competitor_id": ids[m["competitor_name"]],
                "product_url": m.get("url"),
                "competitor_price_inc_vat": m.get("price"),
                "in_stock": m.get("in_stock"),
                "delivery_days": int(m["delivery_days"]) if m.get("delivery_days") is not None else None,
                "match_type": "Exact",
                "source": "priceshape",
            }
    for batch in _batches(_with_stock()):
        db.bulk_insert_mappings(models.FactCompetitorOfferDaily, batch)
        written += len(batch)
    db.commit()
    return written


def _reconcile_competitors(db: Session, today: date, written: set[str],
                           rows_written: int,
                           feed_variants: set[str], feed_canonical: set[str],
                           alias_by_canon: dict[str, set[str]],
                           pre_existing: set[str]) -> dict | None:
    """Werk het concurrentenregister (dim_competitor) bij en lever de
    reconciliatie-samenvatting van deze sync.

    - matcht canonieke feeddomeinen tegen het register;
    - maakt registerrijen aan voor nieuwe concurrenten;
    - bewaart afwijkende oorspronkelijke schrijfwijzen als aliassen;
    - markeert alle vandaag geziene concurrenten met last_seen_date (een
      concurrent die uit de feed verdwijnt wordt nooit verwijderd, alleen
      herkenbaar als "recent niet gezien").
    """
    if not feed_canonical and not written:
        return None
    names = sorted(feed_canonical | written)
    existing: dict[str, models.DimCompetitor] = {}
    for chunk in (names[i:i + 1000] for i in range(0, len(names), 1000)):
        existing.update({
            c.competitor_name: c
            for c in db.query(models.DimCompetitor).filter(
                models.DimCompetitor.competitor_name.in_(chunk)).all()})
    # 'gematcht'/'nieuw' t.o.v. het register vóór deze sync (pre_existing):
    # _persist_offers kan het register tussentijds al hebben aangevuld.
    matched = sum(1 for n in names if n in pre_existing)
    new = len(names) - matched
    for n in names:
        comp = existing.get(n)
        if comp is None:
            comp = models.DimCompetitor(competitor_name=n)
            db.add(comp)
        aliases = alias_by_canon.get(n)
        if aliases:
            merged = list(comp.aliases or [])
            for a in sorted(aliases):
                if a not in merged:
                    merged.append(a)
            comp.aliases = merged
        # Elke in de feed waargenomen concurrent geldt als "gezien vandaag",
        # ook als (nog) geen enkele rij op een bekende SKU is geland.
        comp.last_seen_date = today
    db.commit()
    return {
        "feed_unique": len(feed_canonical),
        "matched": matched,
        "new": new,
        "rows_written": rows_written,
        "duplicates_prevented": max(0, len(feed_variants) - len(feed_canonical)),
    }


# ── PCIS-scoring uit echte concurrentprijzen ────────────────────────────────
def _string_limits(model) -> dict[str, int]:
    """Kolomnaam → maximale lengte voor alle begrensde stringkolommen."""
    from sqlalchemy import String as _Str
    return {c.name: c.type.length for c in model.__table__.columns
            if isinstance(c.type, _Str) and getattr(c.type, "length", None)}


def clamp_rows_to_model(model, rows: list[dict],
                        warnings: list[str] | None = None,
                        skip_fields: frozenset[str] = frozenset()) -> list[str]:
    """
    Kap alle te lange stringwaarden centraal af op de kolombreedte van het
    model, zodat één afwijkende feedwaarde nooit de complete bulk-insert kan
    laten crashen ("value too long for type character varying(N)").

    - Werkt op ALLE begrensde stringkolommen van het model — nieuwe kolommen
      zijn automatisch gedekt, dit kan niet per kolom opnieuw breken.
    - Verliesvrij waar mogelijk: als de rij een raw_attributes-dict heeft (of
      kan krijgen), wordt de originele waarde daar bewaard als "_<veld>_full".
    - Elke afgekapte kolom levert één geaggregeerde waarschuwing (met aantal
      en een voorbeeld) voor het importlogboek.

    Retourneert de (eventueel aangevulde) lijst waarschuwingen.
    """
    if warnings is None:
        warnings = []
    hits: dict[str, dict] = {}
    _clamp_batch(model, rows, hits, skip_fields=skip_fields)
    _emit_clamp_warnings(model, hits, warnings, skip_fields=skip_fields)
    return warnings


def _clamp_batch(model, rows: list[dict], hits: dict[str, dict],
                 skip_fields: frozenset[str] = frozenset()) -> None:
    """Batch-variant van clamp_rows_to_model: kap de rijen af en aggregeer de
    treffers in `hits` (over meerdere batches heen), zodat er per kolom
    uiteindelijk maar één waarschuwing komt — hoe veel batches er ook zijn."""
    limits = {k: v for k, v in _string_limits(model).items()
              if k not in skip_fields}
    has_raw = "raw_attributes" in {c.name for c in model.__table__.columns}
    for row in rows:
        for field, limit in limits.items():
            val = row.get(field)
            if not isinstance(val, str) or len(val) <= limit:
                continue
            if has_raw and field != "raw_attributes":
                raw = row.get("raw_attributes")
                row["raw_attributes"] = {**(raw or {}), f"_{field}_full": val}
            row[field] = val[:limit]
            h = hits.setdefault(field, {"count": 0, "example": None})
            h["count"] += 1
            if h["example"] is None:
                ident = row.get("sku_id") or row.get("competitor_name") or "?"
                h["example"] = f"{ident}: {val[:80]}…" if len(val) > 80 else f"{ident}: {val}"


def _emit_clamp_warnings(model, hits: dict[str, dict], warnings: list[str],
                         skip_fields: frozenset[str] = frozenset()) -> None:
    limits = _string_limits(model)
    for field, h in sorted(hits.items()):
        limit = limits[field]
        warnings.append(
            f"Te lange waarde afgekapt: kolom '{field}' (max {limit} tekens) bij "
            f"{h['count']} rij(en); originele waarde bewaard in raw_attributes. "
            f"Voorbeeld — {h['example']}"
        )
        logger.warning("Feed-ingest: %s", warnings[-1])


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_competition(db: Session, shop_id: int = 1) -> int:
    """Bereken SkuCompetitionScore per SKU uit de concurrentprijzen van vandaag.

    `shop_id` scopeert de hele berekening: alleen producten en concurrentprijzen
    van die winkel worden gelezen, en alleen scores van die winkel worden
    gewist/herschreven. Een score-run voor winkel A raakt winkel B dus nooit.
    """
    today = date.today()

    products = {
        p.sku_id: p for p in db.query(
            models.DimProduct.sku_id, models.DimProduct.current_price,
            models.DimProduct.category, models.DimProduct.sheets_per_pack,
        ).filter(models.DimProduct.shop_id == shop_id).all()
    }

    # Concurrentprijzen van vandaag groeperen per SKU.
    # Door analisten afgekeurde matches (REJECTED) tellen niet mee (§match-review).
    from engine.competition_intelligence import rejected_pairs
    rejected = rejected_pairs(db)
    by_sku: dict[str, list[float]] = {}
    # Niet-leverbare concurrenten (in_stock=False) tellen niet mee in de
    # referentieprijs; onbekende voorraad (None) telt wél mee (§task-116).
    # Concurrenten met een onwerkbaar lange levertijd (> drempel) tellen
    # evenmin mee; onbekende levertijd (None) telt wél mee (§task-174).
    from services import import_settings as imps
    settings = imps.get_settings(db)
    outlier_threshold = settings.get("outlier_threshold", imps.DEFAULT_OUTLIER_THRESHOLD)
    out_of_stock_by_sku: dict[str, int] = {}
    bad_delivery_by_sku: dict[str, int] = {}
    # Per-observatie markeringen (taak #266): uitgesloten observaties worden
    # nooit verwijderd, maar krijgen een expliciete reden op de fact-rij.
    fact_marks: list[dict] = []
    # Parallel aan by_sku: de fact-id per prijs, zodat een uitbijter-index uit
    # calculate_reference_price terug te herleiden is naar de fact-rij.
    fact_ids_by_sku: dict[str, list[int]] = {}
    rows = db.query(
        models.FactCompetitorPriceDaily.id,
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
        models.FactCompetitorPriceDaily.in_stock,
        models.FactCompetitorPriceDaily.delivery_days,
    ).filter(
        models.FactCompetitorPriceDaily.date == today,
        models.FactCompetitorPriceDaily.shop_id == shop_id,
    ).all()
    for fact_id, sku_id, competitor_name, price, in_stock, delivery_days in rows:
        if price is None:
            continue
        if (sku_id, competitor_name) in rejected:
            # Afgekeurde productmatch: prijs telt niet mee, maar de uitsluiting
            # blijft zichtbaar op de fact-rij (reconciliatie, nooit stil).
            fact_marks.append({"id": fact_id, "excluded_reason": ce.EXCLUSION_BAD_MATCH,
                               "exclusion_detail": None})
            continue
        if in_stock is False:
            out_of_stock_by_sku[sku_id] = out_of_stock_by_sku.get(sku_id, 0) + 1
            fact_marks.append({"id": fact_id, "excluded_reason": ce.EXCLUSION_OUT_OF_STOCK,
                               "exclusion_detail": None})
            continue
        if imps.delivery_excluded(settings, delivery_days):
            bad_delivery_by_sku[sku_id] = bad_delivery_by_sku.get(sku_id, 0) + 1
            fact_marks.append({"id": fact_id, "excluded_reason": ce.EXCLUSION_BAD_DELIVERY,
                               "exclusion_detail": {
                                   "delivery_days": delivery_days,
                                   "max_delivery_days": settings.get("max_delivery_days"),
                               }})
            continue
        by_sku.setdefault(sku_id, []).append(float(price))
        fact_ids_by_sku.setdefault(sku_id, []).append(fact_id)

    db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.run_date == today,
        models.SkuCompetitionScore.shop_id == shop_id,
    ).delete(synchronize_session=False)

    def _merge_stock_delivery(sku_id: str, excluded: int, reasons: dict | None):
        oos = out_of_stock_by_sku.get(sku_id, 0)
        if oos:
            excluded += oos
            reasons = dict(reasons or {})
            reasons[ce.EXCLUSION_OUT_OF_STOCK] = reasons.get(ce.EXCLUSION_OUT_OF_STOCK, 0) + oos
        bad = bad_delivery_by_sku.get(sku_id, 0)
        if bad:
            excluded += bad
            reasons = dict(reasons or {})
            reasons[ce.EXCLUSION_BAD_DELIVERY] = reasons.get(ce.EXCLUSION_BAD_DELIVERY, 0) + bad
        return excluded, reasons

    def _excluded_only_row(sku_id: str, excluded: int, reasons: dict | None) -> dict:
        """Score-rij voor een SKU waarvan álle concurrentprijzen zijn
        uitgesloten (voorraad/levertijd/uitbijter): geen referentieprijs,
        maar de uitsluitingstellingen blijven zichtbaar in het dashboard."""
        return {
            "sku_id": sku_id, "run_date": today, "shop_id": shop_id,
            "product_comparability_score": 0.0,
            "price_sensitivity_score": 0.0,
            "substitution_score": 0.0,
            "competitor_relevance_score": 0.0,
            "competitor_price_reliability_score": 0.0,
            "basket_dependency_score": 0.0,
            "strategic_importance_score": 0.0,
            "pcis_score": 0.0,
            "competition_class": ce.get_competition_class(0.0),
            "reference_price": None,
            "price_index": None,
            "competitors_used": 0,
            "competitors_excluded": excluded,
            "excluded_reasons": reasons or None,
        }

    score_maps: list[dict] = []
    for sku_id, prices in by_sku.items():
        prod = products.get(sku_id)
        if prod is None or not prices:
            continue
        # Prijs-per-eenheid-normalisatie (taak #269): alleen als de eigen
        # pakgrootte geldig bekend is (sheets_per_pack > 0) mag een vrijwel
        # exact n-voud/1-op-n van de mediaan genormaliseerd meetellen.
        # 0/negatief is elders een datakwaliteitsfout en telt niet als bekend.
        _spp = getattr(prod, "sheets_per_pack", None)
        pack_size_known = _spp is not None and _spp > 0
        ref_price, used, excluded, reasons, outlier_details, normalized_details = \
            ce.calculate_reference_price(
                prices, outlier_threshold=outlier_threshold,
                pack_size_known=pack_size_known)
        fact_ids = fact_ids_by_sku.get(sku_id, [])
        for det in outlier_details:
            idx = det.pop("index")
            if idx < len(fact_ids):
                fact_marks.append({"id": fact_ids[idx],
                                   "excluded_reason": ce.EXCLUSION_OUTLIER,
                                   "exclusion_detail": det})
        # Genormaliseerde observaties tellen mee (geen uitsluitingsreden),
        # maar krijgen een zichtbare markering op de fact-rij.
        for det in normalized_details:
            idx = det.pop("index")
            if idx < len(fact_ids):
                det["normalized"] = True
                fact_marks.append({"id": fact_ids[idx],
                                   "excluded_reason": None,
                                   "exclusion_detail": det})
        excluded, reasons = _merge_stock_delivery(sku_id, excluded, reasons)
        if ref_price is None or used == 0:
            # Alle prijzen uitgesloten (bv. allemaal uitbijters): geen
            # referentieprijs, maar tel de uitsluitingen wel mee.
            if excluded:
                score_maps.append(_excluded_only_row(sku_id, excluded, reasons))
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
            "sku_id": sku_id, "run_date": today, "shop_id": shop_id,
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

    # SKU's waarvan álle concurrentprijzen al vóór de referentieberekening
    # zijn uitgesloten (voorraad/levertijd) komen niet in by_sku voor, maar
    # hun uitsluitingen moeten wél zichtbaar blijven in het dashboard.
    for sku_id in set(out_of_stock_by_sku) | set(bad_delivery_by_sku):
        if sku_id in by_sku or products.get(sku_id) is None:
            continue
        excluded, reasons = _merge_stock_delivery(sku_id, 0, None)
        if excluded:
            score_maps.append(_excluded_only_row(sku_id, excluded, reasons))

    for chunk in _chunks(score_maps):
        db.bulk_insert_mappings(models.SkuCompetitionScore, chunk)

    # Markeer uitgesloten observaties op de fact-rijen zelf: eerst eerdere
    # markeringen van deze dag/shop wissen (een rerun kan een observatie weer
    # includeren), dan de actuele redenen zetten. Data wordt nooit verwijderd.
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.date == today,
        models.FactCompetitorPriceDaily.shop_id == shop_id,
        sa_or(
            models.FactCompetitorPriceDaily.excluded_reason.isnot(None),
            models.FactCompetitorPriceDaily.exclusion_detail.isnot(None),
        ),
    ).update({"excluded_reason": None, "exclusion_detail": None}, synchronize_session=False)
    for chunk in _chunks(fact_marks):
        db.bulk_update_mappings(models.FactCompetitorPriceDaily, chunk)
    db.commit()
    return len(score_maps)


def build_ai_matches(db: Session, shop_id: int = 1) -> int:
    """
    Bouw AI-matchresultaten uit de PriceShape-feed van vandaag.

    In de feed is elke concurrent-regel al gekoppeld aan onze SKU via de GTIN
    (sku_id == GTIN). Dat is per definitie een exacte EAN-match, dus elk
    vendor-aanbod levert één AiMatchResult van het type "Exact" met
    confidence 1.0. Bestaande rijen van vandaag worden vervangen zodat de
    matching de actuele feed weerspiegelt.

    `shop_id` scopeert de hele opbouw: alleen producten en concurrentprijzen
    van die winkel worden gelezen, en alleen matches van die winkel worden
    gewist/herschreven. Een match-run voor winkel A raakt winkel B dus nooit.
    """
    today = date.today()

    products = {
        p.sku_id: p for p in db.query(
            models.DimProduct.sku_id,
            models.DimProduct.current_price,
            models.DimProduct.ean,
        ).filter(models.DimProduct.shop_id == shop_id).all()
    }

    rows = db.query(
        models.FactCompetitorPriceDaily.sku_id,
        models.FactCompetitorPriceDaily.competitor_name,
        models.FactCompetitorPriceDaily.price,
        models.FactCompetitorPriceDaily.url,
    ).filter(
        models.FactCompetitorPriceDaily.date == today,
        models.FactCompetitorPriceDaily.shop_id == shop_id,
    ).all()

    # Bewaar analistenbeoordelingen: een eerder goed-/afgekeurd paar behoudt
    # zijn status ook wanneer de matches uit de verse feed worden herbouwd.
    review_status: dict[tuple[str, str], str] = {
        (r.own_sku_id, r.competitor_name): r.status
        for r in db.query(
            models.AiMatchResult.own_sku_id,
            models.AiMatchResult.competitor_name,
            models.AiMatchResult.status,
        ).filter(
            models.AiMatchResult.status.in_(["APPROVED", "REJECTED"]),
            models.AiMatchResult.shop_id == shop_id,
        ).all()
    }

    db.query(models.AiMatchResult).filter(
        models.AiMatchResult.run_date == today,
        models.AiMatchResult.shop_id == shop_id,
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
            "shop_id": shop_id,
        })

    for chunk in _chunks(matches):
        db.bulk_insert_mappings(models.AiMatchResult, chunk)
    db.commit()
    return len(matches)
