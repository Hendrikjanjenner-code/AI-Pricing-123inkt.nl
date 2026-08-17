"""
Google Ads connector.

Credentials (DB via ConnectorConfig of omgevingsvariabelen):
  - developer_token  (GOOGLE_ADS_DEVELOPER_TOKEN)
  - customer_id      (GOOGLE_ADS_CUSTOMER_ID)     zonder streepjes, bijv. 1234567890
  - client_id        (GOOGLE_ADS_CLIENT_ID)
  - client_secret    (GOOGLE_ADS_CLIENT_SECRET)
  - refresh_token    (GOOGLE_ADS_REFRESH_TOKEN)

Campagnekosten landen in FactMarketingCostDaily (sea_*-velden, sku_id="CAMPAGNE:<id>").
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://googleads.googleapis.com/v17"

REQUIRED_KEYS = ["developer_token", "customer_id", "client_id", "client_secret", "refresh_token"]
ENV_KEYS = {
    "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
    "customer_id": "GOOGLE_ADS_CUSTOMER_ID",
    "client_id": "GOOGLE_ADS_CLIENT_ID",
    "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
    "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
}


class ConnectorError(Exception):
    """Configuratie- of verbindingsfout voor de Google Ads connector."""


def _get_credentials(db=None) -> dict:
    if db is not None:
        try:
            import models
            from connectors.crypto import decrypt_credentials
            cfg = db.query(models.ConnectorConfig).filter(
                models.ConnectorConfig.connector_name == "google_ads"
            ).first()
            if cfg and cfg.encrypted_credentials:
                creds = decrypt_credentials(cfg.encrypted_credentials)
                if all(creds.get(k) for k in REQUIRED_KEYS):
                    return creds
        except Exception:
            logger.warning("Google Ads DB-config kon niet worden gelezen; val terug op env.", exc_info=True)
    creds = {k: os.environ.get(env, "").strip() for k, env in ENV_KEYS.items()}
    if not all(creds.values()):
        raise ConnectorError(
            "Google Ads is niet geconfigureerd. Sla developer token, customer ID "
            "en OAuth-gegevens op via de Connectoren-pagina."
        )
    return creds


def _access_token(creds: dict) -> str:
    import httpx
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(TOKEN_URL, data={
                "grant_type": "refresh_token",
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "refresh_token": creds["refresh_token"],
            })
    except Exception as exc:
        raise ConnectorError(f"OAuth-tokenserver niet bereikbaar: {str(exc)[:150]}")
    if resp.status_code != 200:
        raise ConnectorError(f"OAuth-refresh mislukt (HTTP {resp.status_code}): {resp.text[:150]}")
    token = resp.json().get("access_token")
    if not token:
        raise ConnectorError("OAuth-respons bevat geen access_token.")
    return token


def check_connection(db=None) -> dict:
    try:
        creds = _get_credentials(db=db)
    except ConnectorError as exc:
        return {"status": "not_configured", "message": str(exc)}
    try:
        _access_token(creds)
        return {"status": "ok",
                "message": f"OAuth-verbinding met Google Ads geslaagd (customer {creds['customer_id']})."}
    except ConnectorError as exc:
        msg = str(exc)
        if "invalid_grant" in msg or "401" in msg:
            return {"status": "auth_error", "message": msg}
        return {"status": "unreachable" if "bereikbaar" in msg else "error", "message": msg}


def fetch_campaign_costs(date_from: str, date_to: str, db=None) -> list[dict]:
    """
    Haal campagnekosten op via GAQL searchStream en upsert ze (per campagne per dag)
    naar FactMarketingCostDaily.
    """
    creds = _get_credentials(db=db)
    token = _access_token(creds)
    customer = creds["customer_id"].replace("-", "")

    query = (
        "SELECT segments.date, campaign.id, campaign.name, metrics.cost_micros, "
        "metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value "
        f"FROM campaign WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'"
    )
    import httpx
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{API_BASE}/customers/{customer}/googleAds:searchStream",
            headers={
                "Authorization": f"Bearer {token}",
                "developer-token": creds["developer_token"],
                "Content-Type": "application/json",
            },
            json={"query": query},
        )
    if resp.status_code in (401, 403):
        raise ConnectorError(f"Toegang geweigerd ({resp.status_code}) door de Google Ads API. "
                             "Controleer developer token en accountrechten.")
    if resp.status_code != 200:
        raise ConnectorError(f"Google Ads API-fout: HTTP {resp.status_code}: {resp.text[:150]}")

    rows: list[dict] = []
    for batch in resp.json() if isinstance(resp.json(), list) else [resp.json()]:
        rows.extend(batch.get("results", []))
    if db is not None and rows:
        _persist_rows(db, rows, kanaal="Google Ads")
    return rows


def _persist_rows(db, rows: list[dict], kanaal: str) -> None:
    import models
    parsed = []
    for r in rows:
        seg, camp, met = r.get("segments", {}), r.get("campaign", {}), r.get("metrics", {})
        try:
            d = datetime.strptime(seg.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        parsed.append((d, camp, met))
    if not parsed:
        return
    dates = {p[0] for p in parsed}
    sku_ids = {f"CAMPAGNE:{p[1].get('id')}" for p in parsed}
    db.query(models.FactMarketingCostDaily).filter(
        models.FactMarketingCostDaily.date.in_(dates),
        models.FactMarketingCostDaily.sku_id.in_(sku_ids),
    ).delete(synchronize_session=False)
    for d, camp, met in parsed:
        cost = float(met.get("costMicros") or 0) / 1_000_000
        db.add(models.FactMarketingCostDaily(
            date=d,
            sku_id=f"CAMPAGNE:{camp.get('id')}"[:50],
            sku_name=(camp.get("name") or "")[:500],
            category=kanaal,
            sea_cost=cost,
            sea_impressions=int(met.get("impressions") or 0),
            sea_clicks=int(met.get("clicks") or 0),
            sea_conversions=int(float(met.get("conversions") or 0)),
            sea_revenue=float(met.get("conversionsValue") or 0),
            total_marketing_cost=cost,
        ))
    db.commit()
