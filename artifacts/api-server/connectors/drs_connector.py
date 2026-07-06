"""
DRS Connector — Dynamisch Retail Systeem integratie.

Leest verbindingsconfig uit omgevingsvariabelen:
  DRS_API_URL     (vereist)  bijv. https://api.drs.example.com/v1
  DRS_API_KEY     (vereist)  geheime API-sleutel
  DRS_TENANT_ID   (optioneel) tenant-/klant-ID voor multi-tenant omgevingen

Functies retourneren altijd een dict of lijst; bij ontbrekende config of
een netwerk-/API-fout wordt een ConnectorError opgegooid met een beschrijvende melding.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import date, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30  # seconden


class ConnectorError(Exception):
    """Fout bij verbinding met of data-ophalen uit DRS."""


def _get_credentials(db=None) -> dict:
    """
    Lees DRS-credentials: DB-config heeft voorrang op omgevingsvariabelen.
    Gooit ConnectorError als geen van beide aanwezig is.
    """
    if db is not None:
        try:
            from connectors.crypto import decrypt_credentials
            import models as _models
            cfg = db.query(_models.ConnectorConfig).filter(
                _models.ConnectorConfig.connector_name == "drs"
            ).first()
            if cfg and cfg.encrypted_credentials:
                creds = decrypt_credentials(cfg.encrypted_credentials)
                base_url = creds.get("api_url", "").rstrip("/")
                api_key = creds.get("api_key", "")
                tenant_id = creds.get("tenant_id", "")
                if base_url and api_key:
                    return {"base_url": base_url, "api_key": api_key, "tenant_id": tenant_id}
        except Exception:
            pass

    base_url = os.environ.get("DRS_API_URL", "").rstrip("/")
    api_key = os.environ.get("DRS_API_KEY", "")
    tenant_id = os.environ.get("DRS_TENANT_ID", "")

    if not base_url or not api_key:
        raise ConnectorError(
            "DRS niet geconfigureerd. Stel DRS_API_URL en DRS_API_KEY in als omgevingsvariabelen of gebruik de Connectoren-pagina."
        )
    return {"base_url": base_url, "api_key": api_key, "tenant_id": tenant_id}


def _make_client(creds: dict) -> httpx.Client:
    headers = {
        "Authorization": f"Bearer {creds['api_key']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if creds.get("tenant_id"):
        headers["X-Tenant-ID"] = creds["tenant_id"]
    return httpx.Client(base_url=creds["base_url"], headers=headers, timeout=_TIMEOUT)


def check_connection(db=None) -> dict:
    """
    Test de DRS-verbinding zonder data op te halen.

    Returns:
        {
          'configured': bool,   — env vars of DB-config aanwezig
          'reachable':  bool,   — API reageert op health-check
          'status':     str,    — 'ok' | 'not_configured' | 'unreachable' | 'auth_error'
          'message':    str,    — leesbare uitleg
        }
    """
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
                    "message": "DRS bereikbaar maar API-sleutel geweigerd (HTTP 401).",
                }
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "configured": True,
            "reachable": True,
            "status": "error",
            "message": f"DRS API fout: HTTP {exc.response.status_code}",
        }
    except httpx.RequestError as exc:
        return {
            "configured": True,
            "reachable": False,
            "status": "unreachable",
            "message": f"DRS niet bereikbaar: {exc}",
        }

    return {
        "configured": True,
        "reachable": True,
        "status": "ok",
        "message": "DRS verbinding succesvol.",
    }


def fetch_product_catalog(
    filters: dict | None = None,
    page_size: int = 500,
    db=None,
) -> list[dict]:
    """
    Haal de volledige productcatalogus op uit DRS.

    Query-parameters (optioneel via filters-dict):
      category    — filter op categoriecode
      updated_after — ISO-datumstring, bijv. '2026-01-01'

    Returns:
        Lijst van product-dicts met de DRS-velden:
        product_id, sku_code, description, category_code,
        cost_price, selling_price, stock_qty, sales_qty_7d,
        sales_qty_30d, last_sale_date, supplier_id
    """
    creds = _get_credentials(db=db)
    params: dict[str, Any] = {"page_size": page_size}
    if filters:
        if "category" in filters:
            params["category"] = filters["category"]
        if "updated_after" in filters:
            params["updated_after"] = filters["updated_after"]

    products: list[dict] = []
    page = 1

    try:
        with _make_client(creds) as client:
            while True:
                params["page"] = page
                resp = client.get("/products", params=params)
                resp.raise_for_status()
                data = resp.json()

                batch = data.get("items", data) if isinstance(data, dict) else data
                if not batch:
                    break
                products.extend(batch)

                # Paginering stoppen als er geen volgende pagina is
                if isinstance(data, dict) and not data.get("has_next", False):
                    break
                if len(batch) < page_size:
                    break
                page += 1

    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"DRS productcatalogus ophalen mislukt: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"DRS verbindingsfout bij ophalen productcatalogus: {exc}") from exc

    logger.info("DRS: %d producten opgehaald", len(products))
    return products


def fetch_sales_history(
    date_from: str,
    date_to: str,
    sku_ids: list[str] | None = None,
    db=None,
) -> list[dict]:
    """
    Haal dagelijkse verkoopdata op uit DRS voor een datumbereik.

    Args:
        date_from:  'YYYY-MM-DD' — beginddatum (inclusief)
        date_to:    'YYYY-MM-DD' — einddatum (inclusief)
        sku_ids:    optionele lijst van SKU-ID's; bij None worden alle SKU's opgehaald

    Returns:
        Lijst van verkooprijen: {sku_id, date, qty_sold, revenue, avg_price}
    """
    creds = _get_credentials(db=db)
    params: dict[str, Any] = {"date_from": date_from, "date_to": date_to}
    if sku_ids:
        params["sku_ids"] = ",".join(sku_ids)

    try:
        with _make_client(creds) as client:
            resp = client.get("/sales/daily", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"DRS verkoopdata ophalen mislukt: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"DRS verbindingsfout bij ophalen verkoopdata: {exc}") from exc

    rows = data.get("items", data) if isinstance(data, dict) else data
    logger.info("DRS: %d verkooprecords opgehaald (%s → %s)", len(rows), date_from, date_to)
    return rows


def fetch_stock_levels(sku_ids: list[str] | None = None, db=None) -> list[dict]:
    """
    Haal actuele voorraadstanden op uit DRS (snapshot van vandaag).

    Args:
        sku_ids: optionele filter op SKU-ID's

    Returns:
        Lijst van voorraad-dicts: {sku_id, stock_qty, warehouse, as_of_date}
    """
    creds = _get_credentials(db=db)
    params: dict[str, Any] = {}
    if sku_ids:
        params["sku_ids"] = ",".join(sku_ids)

    try:
        with _make_client(creds) as client:
            resp = client.get("/inventory/current", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"DRS voorraad ophalen mislukt: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"DRS verbindingsfout bij ophalen voorraad: {exc}") from exc

    rows = data.get("items", data) if isinstance(data, dict) else data
    logger.info("DRS: %d voorraadrecords opgehaald", len(rows))
    return rows


def fetch_price_history(
    sku_ids: list[str],
    lookback_days: int = 90,
) -> list[dict]:
    """
    Haal prijshistorie op uit DRS voor een set SKU's.

    Args:
        sku_ids:       Lijst van SKU-ID's (verplicht)
        lookback_days: Aantal historische dagen (standaard 90)

    Returns:
        Lijst van prijsrijen: {sku_id, date, selling_price, cost_price, margin_pct}
    """
    if not sku_ids:
        raise ConnectorError("fetch_price_history vereist minimaal één SKU-ID.")

    creds = _get_credentials()
    date_from = (
        datetime.utcnow().date() - __import__("datetime").timedelta(days=lookback_days)
    ).isoformat()

    params: dict[str, Any] = {
        "sku_ids": ",".join(sku_ids),
        "date_from": date_from,
    }

    try:
        with _make_client(creds) as client:
            resp = client.get("/prices/history", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"DRS prijshistorie ophalen mislukt: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"DRS verbindingsfout bij ophalen prijshistorie: {exc}") from exc

    rows = data.get("items", data) if isinstance(data, dict) else data
    logger.info(
        "DRS: %d prijsrecords opgehaald voor %d SKU's (lookback %dd)",
        len(rows), len(sku_ids), lookback_days,
    )
    return rows


def push_price_updates(records: list[dict]) -> dict:
    """
    Stuur goedgekeurde prijsadviezen naar DRS via een API-push.

    Args:
        records: Lijst van prijsupdate-dicts, elk met minimaal:
                 {sku_id, recommended_price, min_price, max_price, reason_code}

    Returns:
        {
          'accepted_count': int,   — aantal door DRS bevestigde records
          'response':       Any,   — ruwe DRS-response (indien JSON)
        }

    Raises:
        ConnectorError — bij ontbrekende configuratie, netwerkfout, of een
        niet-2xx antwoord van DRS. Geen enkele record wordt als verwerkt
        beschouwd wanneer deze functie een ConnectorError opgooit.
    """
    if not records:
        raise ConnectorError("push_price_updates vereist minimaal één record.")

    creds = _get_credentials()
    payload = {"updates": records}

    try:
        with _make_client(creds) as client:
            resp = client.post("/prices/update", json=payload)
            resp.raise_for_status()
            try:
                data = resp.json()
            except json.JSONDecodeError:
                data = {}
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(
            f"DRS prijs-push mislukt: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ConnectorError(f"DRS niet bereikbaar bij prijs-push: {exc}") from exc

    accepted_count = data.get("accepted_count", len(records)) if isinstance(data, dict) else len(records)
    logger.info("DRS: %d prijsupdates gepusht (bevestigd: %d)", len(records), accepted_count)
    return {"accepted_count": accepted_count, "response": data}
