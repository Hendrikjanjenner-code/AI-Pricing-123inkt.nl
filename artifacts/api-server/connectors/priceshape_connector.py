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

_TIMEOUT = 30  # seconden


class ConnectorError(Exception):
    """Fout bij verbinding met of data-ophalen uit PriceShape."""


def _get_credentials(db=None) -> dict:
    """
    Lees PriceShape-credentials: DB-config heeft voorrang op omgevingsvariabelen.
    Gooit ConnectorError als geen van beide aanwezig is.
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
                base_url = creds.get("api_url", "").rstrip("/")
                api_key = creds.get("api_key", "")
                account_id = creds.get("account_id", "")
                if base_url and api_key:
                    return {"base_url": base_url, "api_key": api_key, "account_id": account_id}
        except Exception:
            pass

    base_url = os.environ.get("PRICESHAPE_API_URL", "").rstrip("/")
    api_key = os.environ.get("PRICESHAPE_API_KEY", "")
    account_id = os.environ.get("PRICESHAPE_ACCOUNT_ID", "")

    if not base_url or not api_key:
        raise ConnectorError(
            "PriceShape niet geconfigureerd. Stel PRICESHAPE_API_URL en "
            "PRICESHAPE_API_KEY in als omgevingsvariabelen of gebruik de Connectoren-pagina."
        )
    return {"base_url": base_url, "api_key": api_key, "account_id": account_id}


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
