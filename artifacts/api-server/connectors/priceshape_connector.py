"""
PriceShape Connector — API-integratie met het PriceShape prijsplatform.

Leest verbindingsconfig uit omgevingsvariabelen:
  PRICESHAPE_API_URL     (vereist)  bijv. https://api.priceshape.com/v1
  PRICESHAPE_API_KEY     (vereist)  geheime API-sleutel
  PRICESHAPE_ACCOUNT_ID  (optioneel) account-/klant-ID voor multi-account omgevingen

Functies retourneren altijd een dict of lijst; bij ontbrekende config of
een netwerk-/API-fout wordt een ConnectorError opgegooid met een beschrijvende melding.

Buiten scope (zie Task #79): dit connector-bestand ondersteunt alleen het
OPHALEN van concurrentieprijsdata uit PriceShape. Het terugschrijven/exporteren
van goedgekeurde prijzen náár PriceShape blijft ongewijzigd via routes/exports.py.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30  # seconden (REST-API-aanroepen)

# Feed-exports kunnen tientallen tot honderden MB's zijn en enkele minuten duren
# om te downloaden. Ruime read-timeout, maar strakke connect-timeout zodat een
# echt onbereikbare host snel faalt.
_FEED_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)


class ConnectorError(Exception):
    """Fout bij verbinding met of data-ophalen uit PriceShape."""


def _get_raw_config(db=None) -> dict:
    """
    Lees de volledige PriceShape-connectorconfig (inclusief `mode`): DB-config
    heeft voorrang op omgevingsvariabelen. Geeft {} terug als niets is ingesteld.

    De connector kent twee modi die náást elkaar bestaan:
      - "rest": klassieke REST-API (api_url + api_key + account_id)
      - "feed": PriceShape output-feed als één URL die CSV/JSON/XML teruggeeft
                (feed_url + feed_format)
    """
    if db is not None:
        try:
            from connectors.crypto import decrypt_credentials
            import models as _models
            cfg = db.query(_models.ConnectorConfig).filter(
                _models.ConnectorConfig.connector_name == "priceshape"
            ).first()
            if cfg and cfg.encrypted_credentials:
                creds = decrypt_credentials(cfg.encrypted_credentials)
                if creds:
                    return creds
        except Exception:
            pass

    env: dict = {}
    feed_url = os.environ.get("PRICESHAPE_FEED_URL", "").strip()
    if feed_url:
        env["mode"] = "feed"
        env["feed_url"] = feed_url
        env["feed_format"] = os.environ.get("PRICESHAPE_FEED_FORMAT", "auto")
        return env

    base_url = os.environ.get("PRICESHAPE_API_URL", "").strip()
    api_key = os.environ.get("PRICESHAPE_API_KEY", "")
    if base_url and api_key:
        env["mode"] = "rest"
        env["api_url"] = base_url
        env["api_key"] = api_key
        env["account_id"] = os.environ.get("PRICESHAPE_ACCOUNT_ID", "")
    return env


def _get_mode(creds: dict) -> str:
    """Bepaal de actieve modus ('rest' | 'feed') uit een config-dict."""
    m = (creds.get("mode") or "").strip().lower()
    if m in ("rest", "feed"):
        return m
    if (creds.get("feed_url") or "").strip():
        return "feed"
    return "rest"


def _get_credentials(db=None) -> dict:
    """
    Lees PriceShape REST-credentials. DB-config heeft voorrang op omgevingsvariabelen.
    Gooit ConnectorError als de REST-modus niet is geconfigureerd.
    """
    raw = _get_raw_config(db=db)
    base_url = (raw.get("api_url") or "").rstrip("/")
    api_key = raw.get("api_key") or ""
    account_id = raw.get("account_id") or ""

    if not base_url or not api_key:
        raise ConnectorError(
            "PriceShape (REST) niet geconfigureerd. Stel PRICESHAPE_API_URL en "
            "PRICESHAPE_API_KEY in als omgevingsvariabelen of gebruik de Connectoren-pagina."
        )
    return {"base_url": base_url, "api_key": api_key, "account_id": account_id}


def _get_feed_config(db=None) -> dict:
    """
    Lees PriceShape feed-config (feed_url + feed_format). DB-config heeft voorrang
    op omgevingsvariabelen. Gooit ConnectorError als de feed-modus niet is ingesteld.
    """
    raw = _get_raw_config(db=db)
    feed_url = (raw.get("feed_url") or "").strip()
    if not feed_url:
        raise ConnectorError(
            "PriceShape feed-URL niet geconfigureerd. Stel PRICESHAPE_FEED_URL in als "
            "omgevingsvariabele of gebruik de Connectoren-pagina."
        )
    return {"feed_url": feed_url, "feed_format": (raw.get("feed_format") or "auto").strip().lower()}


# ── Feed-modus: ophalen + formaatdetectie + parsing (CSV / JSON / XML) ──────

def _fetch_feed(feed_url: str) -> tuple[bytes, str]:
    """
    Haal de PriceShape output-feed op via één URL. Elke (redirect-)hop wordt tegen
    SSRF gevalideerd — export-URL's wijzen vaak door naar opslag/CDN, maar mogen
    niet naar een intern/privaat adres verwijzen. Geeft (ruwe bytes, content-type)
    terug. Gooit ConnectorError bij fouten.
    """
    from connectors.net import safe_get, UnsafeURLError

    try:
        resp = safe_get(feed_url, timeout=_FEED_TIMEOUT)
        if resp.status_code in (401, 403):
            raise ConnectorError(
                f"PriceShape feed weigerde toegang (HTTP {resp.status_code}). "
                "Controleer of de feed-URL (met token) nog geldig is."
            )
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "")
    except UnsafeURLError as exc:
        raise ConnectorError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape feed ophalen mislukt: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape feed niet bereikbaar: {exc}") from exc


_FEED_SAMPLE_MAX_BYTES = 5_000_000  # ~5 MB is ruim genoeg om formaat + kolommen te valideren


def _stream_feed_sample(feed_url: str, max_bytes: int = _FEED_SAMPLE_MAX_BYTES) -> tuple[bytes, str]:
    """
    Haal alleen het BEGIN van de feed op (streaming, tot max_bytes) om formaat en
    kolommen te valideren zonder de volledige — mogelijk honderden MB's — feed te
    downloaden. Zo blijft de 'test verbinding'-aanroep snel (enkele seconden) en
    ruim binnen de client-time-out. Elke redirect-hop wordt SSRF-gevalideerd.
    """
    from connectors.net import safe_stream, UnsafeURLError

    probe_timeout = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)
    try:
        with safe_stream(feed_url, timeout=probe_timeout) as resp:
            if resp.status_code in (401, 403):
                raise ConnectorError(
                    f"PriceShape feed weigerde toegang (HTTP {resp.status_code}). "
                    "Controleer of de feed-URL (met token) nog geldig is."
                )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            buf = bytearray()
            for chunk in resp.iter_bytes(65536):
                buf.extend(chunk)
                if len(buf) >= max_bytes:
                    break
            return bytes(buf), content_type
    except UnsafeURLError as exc:
        raise ConnectorError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape feed ophalen mislukt: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape feed niet bereikbaar: {exc}") from exc


class NotStreamable(Exception):
    """De feed is geen top-level JSON-array en kan niet streamend geparsed worden."""


class _StreamReader:
    """
    File-achtige adapter rond een byte-iterator (httpx `iter_bytes`), zodat ijson
    de feed in stukjes kan lezen zónder de volledige — mogelijk honderden MB's —
    payload in het geheugen te houden. Ondersteunt `read(size)` en `prepend()`
    (om vooruit-gelezen 'peek'-bytes terug te plaatsen).
    """

    def __init__(self, chunk_iter):
        self._it = iter(chunk_iter)
        self._buf = bytearray()
        self._eof = False

    def _fill(self, size: int) -> None:
        while len(self._buf) < size and not self._eof:
            try:
                self._buf += next(self._it)
            except StopIteration:
                self._eof = True

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            for chunk in self._it:
                self._buf += chunk
            self._eof = True
            out = bytes(self._buf)
            self._buf = bytearray()
            return out
        self._fill(size)
        out = bytes(self._buf[:size])
        del self._buf[:size]
        return out

    def prepend(self, data: bytes) -> None:
        self._buf[:0] = data


def stream_json_records(feed_url: str):
    """
    Yield ruwe product-records uit een PriceShape JSON-feed via STREAMING parsing
    (ijson), zodat het piekgeheugen laag blijft: nooit de volledige 206 MB-bytes
    én de geparste ~1 GB Python-structuur tegelijk in het geheugen. Elke
    (redirect-)hop wordt SSRF-gevalideerd.

    Werkt alleen voor een top-level JSON-array (`[ {...}, {...} ]`) — de vorm van
    de PriceShape output-feed. Bij een andere vorm (object-wrapper, CSV, XML)
    wordt `NotStreamable` opgegooid zodat de aanroeper terugvalt op gebufferd lezen.
    """
    import ijson
    from connectors.net import safe_stream, UnsafeURLError

    try:
        with safe_stream(feed_url, timeout=_FEED_TIMEOUT) as resp:
            if resp.status_code in (401, 403):
                raise ConnectorError(
                    f"PriceShape feed weigerde toegang (HTTP {resp.status_code}). "
                    "Controleer of de feed-URL (met token) nog geldig is."
                )
            resp.raise_for_status()

            reader = _StreamReader(resp.iter_bytes(65536))
            head = reader.read(65536)
            first = head.lstrip(b"\xef\xbb\xbf").lstrip()[:1]
            reader.prepend(head)
            if first != b"[":
                raise NotStreamable(
                    "Feed is geen top-level JSON-array — gebufferd lezen vereist."
                )

            for record in ijson.items(reader, "item"):
                yield record
    except UnsafeURLError as exc:
        raise ConnectorError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape feed ophalen mislukt: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape feed niet bereikbaar: {exc}") from exc


def _json_sample_records(text: str, limit: int = 200) -> list:
    """
    Haal tot `limit` complete top-level objecten uit een (mogelijk afgekapte) JSON-
    array-tekst, zonder het hele document te hoeven parsen. Nodig omdat een sample
    van een grote JSON-feed vrijwel altijd midden in een record wordt afgekapt.
    """
    import json as _json

    records: list = []
    depth = 0
    in_str = False
    esc = False
    start = -1
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        records.append(_json.loads(text[start:i + 1]))
                    except _json.JSONDecodeError:
                        pass
                    start = -1
                    if len(records) >= limit:
                        break
    return records


def _parse_feed_sample(content: bytes, content_type: str, fmt: str) -> list[dict]:
    """
    Parse een (mogelijk afgekapte) feed-sample tolerant naar rij-dicts, met dezelfde
    vorm als _parse_feed_rows. Gebruikt door de 'test verbinding'-flow, die maar een
    handvol rijen nodig heeft om formaat + kolommen te valideren.
    """
    import json as _json

    if fmt == "json":
        text = content.decode("utf-8-sig", errors="ignore")
        try:
            records = _json_extract_rows(_json.loads(text))
        except (ValueError, _json.JSONDecodeError):
            records = _json_sample_records(text)
        rows: list[dict] = []
        for r in records:
            if isinstance(r, dict):
                rows.extend(_expand_json_record(r))
        return rows

    if fmt == "csv":
        # Kap de laatste (mogelijk halve) regel af zodat de CSV-parser niet struikelt.
        nl = content.rfind(b"\n")
        trimmed = content[: nl + 1] if nl > 0 else content
        return _parse_feed_rows(trimmed, content_type, "csv")

    # XML: 5 MB omvat doorgaans het hele document, dus een directe parse volstaat.
    return _parse_feed_rows(content, content_type, "xml")


def _detect_feed_format(content: bytes, content_type: str, declared: str) -> str:
    """
    Bepaal het feed-formaat ('csv' | 'json' | 'xml'). Een expliciet gekozen
    formaat wint; anders wordt content-type en daarna de inhoud gesnifft.
    """
    d = (declared or "auto").strip().lower()
    if d in ("csv", "json", "xml"):
        return d

    ct = (content_type or "").lower()
    if "json" in ct:
        return "json"
    if "xml" in ct:
        return "xml"
    if "csv" in ct:
        return "csv"

    head = content[:512].lstrip()
    if head[:1] in (b"{", b"["):
        return "json"
    if head[:1] == b"<":
        return "xml"
    return "csv"


def _stringify(value) -> str:
    """Zet een scalar/complex JSON-waarde om naar een string (mirror van CSV-cellen)."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        import json as _json
        return _json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _json_extract_rows(data) -> list:
    """Vind de lijst met rij-objecten binnen een JSON-payload."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "products", "data", "results", "rows", "records", "prices"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        for val in data.values():
            if isinstance(val, list):
                return val
        return [data]
    return []


_VENDOR_LIST_KEYS = ("vendors", "competitors", "offers", "merchants", "sellers", "listings")


def _find_vendor_list(record: dict):
    """Vind een geneste lijst met concurrent-/vendor-objecten in een productrecord."""
    for key in _VENDOR_LIST_KEYS:
        val = record.get(key)
        if isinstance(val, list) and any(isinstance(v, dict) for v in val):
            return val
    return None


def _expand_json_record(record: dict) -> list[dict]:
    """
    Splits een productrecord met geneste vendor-lijst uit naar één rij per vendor.

    PriceShape-feeds leveren per product één object met een `vendors`-array; elke
    vendor is een concurrent (domain + price + productUrl). Om deze met dezelfde
    platte alias-/matchinglogica te matchen als CSV-uploads, wordt elk product
    'ge-unnest' tot N concurrentrijen. Product-identifiers (gtin/ean/…) en eigen
    prijzen blijven op elke rij; vendorvelden overschrijven bij sleutelbotsing,
    zodat `price`/`domain`/`productUrl` naar de concurrent wijzen. Records zonder
    geneste vendor-lijst worden platgeslagen tot één rij (ongewijzigd gedrag).
    """
    vendors = _find_vendor_list(record)
    if not vendors:
        return [{str(k).strip().lower(): _stringify(v) for k, v in record.items()}]

    product_scalars = {
        k: v for k, v in record.items()
        if not (isinstance(v, list) and any(isinstance(x, dict) for x in v))
    }
    out: list[dict] = []
    for vendor in vendors:
        if not isinstance(vendor, dict):
            continue
        combined = {**product_scalars, **vendor}
        out.append({str(k).strip().lower(): _stringify(v) for k, v in combined.items()})
    return out


def _localname(tag: str) -> str:
    """Strip XML-namespace uit een tag ('{ns}product' -> 'product')."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_record_elements(root) -> list:
    """
    Bepaal welke XML-elementen de records vormen. Dekt de gangbare vormen:
      • lijst:            <products><product>…</product><product>…</product></products>
      • enkel record:     <products><product>…</product></products>
      • dubbele wrapper:  <export><products><product>…</product></products></export>
      • record = root:    <product><sku>…</sku><prijs>…</prijs></product>
      • attribuut-record: <items><item sku=".." price=".."/></items>
    """
    children = list(root)
    if not children:
        # Root zonder kind-elementen: het record zit in de root zelf (attributen).
        return [root]

    # Eén wrapper met een homogene lijst kleinkinderen → daal af naar die lijst.
    if len(children) == 1:
        grand = list(children[0])
        gtags = {_localname(g.tag) for g in grand}
        if grand and len(gtags) == 1:
            return grand

    # Zien de directe kinderen eruit als records (eigen sub-elementen of attributen)?
    have_record_signal = sum(
        1 for c in children if len(list(c)) > 0 or len(c.attrib) > 0
    )
    if have_record_signal == 0:
        # Kinderen zijn platte veld-elementen → de root is één enkel record.
        return [root]
    return children


def _parse_feed_rows(content: bytes, content_type: str, fmt: str) -> list[dict]:
    """
    Parse feed-bytes naar een lijst rij-dicts met kleingeschreven sleutels en
    string-waarden — identiek aan het formaat van engine.import_engine.file_to_rows,
    zodat dezelfde alias-/matchinglogica hergebruikt kan worden.
    """
    if fmt == "json":
        import json as _json
        try:
            data = _json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, _json.JSONDecodeError) as exc:
            raise ConnectorError(f"PriceShape JSON-feed kon niet worden gelezen: {exc}") from exc
        rows: list[dict] = []
        for r in _json_extract_rows(data):
            if isinstance(r, dict):
                rows.extend(_expand_json_record(r))
        return rows

    if fmt == "xml":
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ConnectorError(f"PriceShape XML-feed kon niet worden gelezen: {exc}") from exc
        record_parents = _xml_record_elements(root)
        rows = []
        for el in record_parents:
            row: dict = {}
            for k, v in el.attrib.items():
                row[_localname(str(k)).strip().lower()] = (v or "").strip()
            for child in el:
                row[_localname(child.tag).strip().lower()] = (child.text or "").strip()
            if row:
                rows.append(row)
        return rows

    # CSV (default) — hergebruik de robuuste decoder van de import-engine.
    import csv
    import io
    from engine.import_engine import decode_csv_bytes

    text = decode_csv_bytes(content).replace("\r\n", "\n").replace("\r", "\n")
    delimiter = ","
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        pass
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [{(k or "").strip().lower(): (v or "") for k, v in row.items()} for row in reader]


def fetch_feed_rows(db=None) -> list[dict]:
    """
    Haal de PriceShape output-feed op en parse deze naar rij-dicts.
    Automatische formaatdetectie tenzij feed_format expliciet csv/json/xml is.
    """
    cfg = _get_feed_config(db=db)
    content, content_type = _fetch_feed(cfg["feed_url"])
    fmt = _detect_feed_format(content, content_type, cfg["feed_format"])
    rows = _parse_feed_rows(content, content_type, fmt)
    logger.info("PriceShape feed: %d rijen geparsed (formaat=%s)", len(rows), fmt)
    return rows


def _check_feed_connection(cfg: dict) -> dict:
    """
    Lichtgewicht bereikbaarheidscheck voor de feed-URL. Gebruikt een streaming-
    request zodat een grote feed (tientallen–honderden MB's) NIET volledig wordt
    gedownload; alleen status/headers en de eerste bytes worden gecontroleerd.
    """
    from connectors.net import safe_stream, UnsafeURLError

    feed_url = cfg["feed_url"]
    try:
        # Ruime connect + read: sommige export-endpoints bufferen de hele feed
        # vóór het eerste byte, dus een te korte read geeft valse alarmen.
        probe_timeout = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)
        with safe_stream(feed_url, timeout=probe_timeout) as resp:
            if resp.status_code in (401, 403):
                return {
                    "configured": True, "reachable": True, "status": "auth_error",
                    "message": f"Feed bereikbaar maar toegang geweigerd (HTTP {resp.status_code}). "
                               "Controleer of de feed-URL/token nog geldig is.",
                }
            resp.raise_for_status()
            first = next(resp.iter_bytes(1024), b"")
            if not first:
                return {
                    "configured": True, "reachable": True, "status": "error",
                    "message": "Feed opgehaald maar leeg.",
                }
    except UnsafeURLError as exc:
        return {"configured": True, "reachable": False, "status": "error", "message": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {
            "configured": True, "reachable": True, "status": "error",
            "message": f"PriceShape feed fout: HTTP {exc.response.status_code}",
        }
    except httpx.RequestError as exc:
        return {
            "configured": True, "reachable": False, "status": "unreachable",
            "message": f"PriceShape feed niet bereikbaar: {exc}",
        }

    return {"configured": True, "reachable": True, "status": "ok",
            "message": "PriceShape feed-verbinding succesvol."}


def _make_client(creds: dict) -> httpx.Client:
    headers = {
        "Authorization": f"Bearer {creds['api_key']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if creds.get("account_id"):
        headers["X-Account-ID"] = creds["account_id"]
    return httpx.Client(base_url=creds["base_url"], headers=headers, timeout=_TIMEOUT)


def check_connection(db=None) -> dict:
    """
    Test de PriceShape-verbinding zonder data op te halen.

    Returns:
        {
          'configured': bool,   — env vars of DB-config aanwezig
          'reachable':  bool,   — API reageert op health-check
          'status':     str,    — 'ok' | 'not_configured' | 'unreachable' | 'auth_error' | 'error'
          'message':    str,    — leesbare uitleg
        }
    """
    raw = _get_raw_config(db=db)
    if not raw:
        return {
            "configured": False,
            "reachable": False,
            "status": "not_configured",
            "message": "PriceShape niet geconfigureerd (geen REST-sleutel of feed-URL).",
        }

    if _get_mode(raw) == "feed":
        try:
            return _check_feed_connection(_get_feed_config(db=db))
        except ConnectorError as exc:
            return {"configured": False, "reachable": False,
                    "status": "not_configured", "message": str(exc)}

    try:
        creds = _get_credentials(db=db)
    except ConnectorError as exc:
        return {
            "configured": False,
            "reachable": False,
            "status": "not_configured",
            "message": str(exc),
        }

    try:
        with _make_client(creds) as client:
            resp = client.get("/health")
            if resp.status_code == 401:
                return {
                    "configured": True,
                    "reachable": True,
                    "status": "auth_error",
                    "message": "PriceShape bereikbaar maar API-sleutel geweigerd (HTTP 401).",
                }
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "configured": True,
            "reachable": True,
            "status": "error",
            "message": f"PriceShape API fout: HTTP {exc.response.status_code}",
        }
    except httpx.RequestError as exc:
        return {
            "configured": True,
            "reachable": False,
            "status": "unreachable",
            "message": f"PriceShape niet bereikbaar: {exc}",
        }

    return {
        "configured": True,
        "reachable": True,
        "status": "ok",
        "message": "PriceShape verbinding succesvol.",
    }


def fetch_competitor_prices(
    sku_ids: list[str] | None = None,
    eans: list[str] | None = None,
    updated_after: str | None = None,
    page_size: int = 500,
    db=None,
) -> list[dict]:
    """
    Haal actuele concurrentieprijzen op uit PriceShape.

    Matching-sleutels (minstens één wordt gebruikt door PriceShape om SKU's te
    identificeren): SKU, EAN, OEM/MPN.

    Args:
        sku_ids:       optionele filter op interne SKU-ID's
        eans:          optionele filter op EAN-codes
        updated_after: ISO-datumstring, bijv. '2026-01-01' — alleen wijzigingen sindsdien
        page_size:     paginagrootte voor paginering

    Returns:
        Lijst van dicts met de PriceShape-velden:
        sku_id, ean, oem_code, mpn, competitor_name, competitor_price,
        currency, url, in_stock, scraped_at, import_source
    """
    creds = _get_credentials(db=db)
    params: dict[str, Any] = {"page_size": page_size}
    if sku_ids:
        params["sku_ids"] = ",".join(sku_ids)
    if eans:
        params["eans"] = ",".join(eans)
    if updated_after:
        params["updated_after"] = updated_after

    rows: list[dict] = []
    page = 1

    try:
        with _make_client(creds) as client:
            while True:
                params["page"] = page
                resp = client.get("/competitor-prices", params=params)
                resp.raise_for_status()
                data = resp.json()

                batch = data.get("items", data) if isinstance(data, dict) else data
                if not batch:
                    break
                rows.extend(batch)

                if isinstance(data, dict) and not data.get("has_next", False):
                    break
                if len(batch) < page_size:
                    break
                page += 1

    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape concurrentieprijzen ophalen mislukt: HTTP {exc.response.status_code} "
            f"— {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape verbindingsfout bij ophalen concurrentieprijzen: {exc}") from exc

    logger.info("PriceShape: %d concurrentieprijzen opgehaald", len(rows))
    return rows


def fetch_product_matches(sku_ids: list[str] | None = None) -> list[dict]:
    """
    Haal de productmatching op zoals PriceShape die kent (welke SKU/EAN/OEM
    matcht met welke concurrent-URL's).

    Returns:
        Lijst van dicts: {sku_id, ean, oem_code, mpn, matched_urls, match_confidence}
    """
    creds = _get_credentials()
    params: dict[str, Any] = {}
    if sku_ids:
        params["sku_ids"] = ",".join(sku_ids)

    try:
        with _make_client(creds) as client:
            resp = client.get("/product-matches", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape productmatches ophalen mislukt: HTTP {exc.response.status_code} "
            f"— {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape verbindingsfout bij ophalen productmatches: {exc}") from exc

    rows = data.get("items", data) if isinstance(data, dict) else data
    logger.info("PriceShape: %d productmatches opgehaald", len(rows))
    return rows


def fetch_price_history(
    sku_ids: list[str],
    lookback_days: int = 90,
) -> list[dict]:
    """
    Haal concurrentieprijs-historie op uit PriceShape voor een set SKU's.

    Args:
        sku_ids:       Lijst van SKU-ID's (verplicht)
        lookback_days: Aantal historische dagen (standaard 90)

    Returns:
        Lijst van prijsrijen: {sku_id, date, competitor_name, competitor_price}
    """
    if not sku_ids:
        raise ConnectorError("fetch_price_history vereist minimaal één SKU-ID.")

    creds = _get_credentials()
    date_from = (datetime.utcnow().date() - timedelta(days=lookback_days)).isoformat()

    params: dict[str, Any] = {
        "sku_ids": ",".join(sku_ids),
        "date_from": date_from,
    }

    try:
        with _make_client(creds) as client:
            resp = client.get("/competitor-prices/history", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"PriceShape prijshistorie ophalen mislukt: HTTP {exc.response.status_code} "
            f"— {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"PriceShape verbindingsfout bij ophalen prijshistorie: {exc}") from exc

    rows = data.get("items", data) if isinstance(data, dict) else data
    logger.info(
        "PriceShape: %d prijsrecords opgehaald voor %d SKU's (lookback %dd)",
        len(rows), len(sku_ids), lookback_days,
    )
    return rows
