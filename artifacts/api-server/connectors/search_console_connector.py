"""
Google Search Console connector.

Credentials (DB via ConnectorConfig of omgevingsvariabelen):
  - site_url             (GSC_SITE_URL)             bijv. "sc-domain:example.nl" of "https://example.nl/"
  - service_account_key  (GSC_SERVICE_ACCOUNT_KEY)  service-account JSON met Search Console leesrechten

Data landt in FactSearchDemandDaily (source="gsc"): impressies, klikken, CTR en
gemiddelde positie per zoekterm.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API_BASE = "https://www.googleapis.com/webmasters/v3"


class ConnectorError(Exception):
    """Configuratie- of verbindingsfout voor de Search Console connector."""


def _get_credentials(db=None) -> dict:
    """DB-config eerst, dan env-variabelen. Raise ConnectorError als niets is geconfigureerd."""
    if db is not None:
        try:
            import models
            from connectors.crypto import decrypt_credentials
            cfg = db.query(models.ConnectorConfig).filter(
                models.ConnectorConfig.connector_name == "search_console"
            ).first()
            if cfg and cfg.encrypted_credentials:
                creds = decrypt_credentials(cfg.encrypted_credentials)
                if creds.get("site_url") and creds.get("service_account_key"):
                    return creds
        except ConnectorError:
            raise
        except Exception:
            logger.warning("Search Console DB-config kon niet worden gelezen; val terug op env.", exc_info=True)
    site_url = os.environ.get("GSC_SITE_URL", "").strip()
    sa_key = os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "").strip()
    if not site_url or not sa_key:
        raise ConnectorError(
            "Search Console is niet geconfigureerd. Sla een Site-URL en "
            "Service Account JSON op via de Connectoren-pagina."
        )
    return {"site_url": site_url, "service_account_key": sa_key}


def _access_token(sa_key_raw: str) -> str:
    try:
        sa_info = json.loads(sa_key_raw)
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Service Account JSON is ongeldig: {exc}")
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
    except ImportError:
        raise ConnectorError("google-auth SDK niet geïnstalleerd.")
    try:
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception as exc:
        raise ConnectorError(f"Kon geen toegangstoken verkrijgen: {str(exc)[:200]}")


def check_connection(db=None) -> dict:
    """Live verbindingscheck: token verkrijgen + site-info opvragen."""
    try:
        creds = _get_credentials(db=db)
    except ConnectorError as exc:
        return {"status": "not_configured", "message": str(exc)}
    try:
        token = _access_token(creds["service_account_key"])
        import httpx
        from urllib.parse import quote
        site = quote(creds["site_url"], safe="")
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{API_BASE}/sites/{site}",
                              headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            return {"status": "ok", "message": f"Verbonden met Search Console-property {creds['site_url']}."}
        if resp.status_code in (401, 403):
            return {"status": "auth_error",
                    "message": f"Toegang geweigerd ({resp.status_code}). Voeg het service-account toe als gebruiker in Search Console."}
        if resp.status_code == 404:
            return {"status": "error", "message": f"Property '{creds['site_url']}' niet gevonden in Search Console."}
        return {"status": "error", "message": f"Onverwachte respons: HTTP {resp.status_code}."}
    except ConnectorError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        return {"status": "unreachable", "message": str(exc)[:200]}


def fetch_search_analytics(date_from: str, date_to: str, db=None, max_rows: int = 5000) -> list[dict]:
    """
    Haal zoekterm-prestaties op (impressies, klikken, CTR, positie) en upsert
    ze naar FactSearchDemandDaily met source='gsc'.
    """
    creds = _get_credentials(db=db)
    token = _access_token(creds["service_account_key"])

    import httpx
    from urllib.parse import quote
    site = quote(creds["site_url"], safe="")
    body = {
        "startDate": date_from,
        "endDate": date_to,
        "dimensions": ["date", "query"],
        "rowLimit": max_rows,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{API_BASE}/sites/{site}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code in (401, 403):
        raise ConnectorError(f"Toegang geweigerd ({resp.status_code}) bij het ophalen van zoekdata.")
    if resp.status_code != 200:
        raise ConnectorError(f"Search Console API-fout: HTTP {resp.status_code}: {resp.text[:150]}")

    rows = resp.json().get("rows", [])
    if db is not None and rows:
        _persist_rows(db, creds["site_url"], rows)
    return rows


def _persist_rows(db, site_url: str, rows: list[dict]) -> None:
    """Idempotente upsert: verwijder bestaande gsc-rijen voor de betrokken datums
    alléén als er vervangende rijen zijn (last-known-good principe)."""
    import models
    parsed = []
    for r in rows:
        keys = r.get("keys", [])
        if len(keys) < 2:
            continue
        try:
            d = datetime.strptime(keys[0], "%Y-%m-%d").date()
        except ValueError:
            continue
        parsed.append((d, keys[1], r))
    if not parsed:
        return
    dates = {p[0] for p in parsed}
    db.query(models.FactSearchDemandDaily).filter(
        models.FactSearchDemandDaily.source == "gsc",
        models.FactSearchDemandDaily.date.in_(dates),
    ).delete(synchronize_session=False)
    for d, query, r in parsed:
        db.add(models.FactSearchDemandDaily(
            date=d,
            entity_type="SITE",
            entity_id=site_url[:200],
            keyword=query[:500],
            keyword_type="GENERIC",
            impressions=int(r.get("impressions") or 0),
            clicks=int(r.get("clicks") or 0),
            ctr=float(r.get("ctr") or 0.0),
            average_position=float(r.get("position") or 0.0),
            source="gsc",
        ))
    db.commit()
