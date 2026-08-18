"""
Connector-beheer endpoints — status ophalen, testen, opslaan en synchroniseren
voor PriceShape, DRS en Google Analytics 4.

Endpoints:
  GET  /api/connectors                    — overzicht van alle 3 connectors
  GET  /api/connectors/{name}/status      — live verbindingscheck
  POST /api/connectors/{name}/test        — test credentials zonder op te slaan
  POST /api/connectors/{name}/save        — sla credentials versleuteld op
  DELETE /api/connectors/{name}           — ontkoppel (verwijder opgeslagen creds)
  POST /api/connectors/{name}/sync        — handmatige synchronisatie

Geheimen worden versleuteld opgeslagen en nooit als plaintext teruggegeven.
Bestaande omgevingsvariabelen blijven werken als terugval.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date as _date
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
import auth as auth_utils
from connectors.crypto import encrypt_credentials, decrypt_credentials

import hashlib
import logging
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as _pg_insert

_log = logging.getLogger(__name__)


def _advisory_key(name: str) -> int:
    """Stabiele 31-bits sleutel per connector voor een PostgreSQL advisory lock."""
    digest = hashlib.sha256(f"connector_sync:{name}".encode()).hexdigest()
    return int(digest[:15], 16) % 2147483647


@contextmanager
def _sync_lock(name: str):
    """Advisory lock zodat er nooit twee syncs voor dezelfde connector tegelijk
    draaien (de geplande job én de in-process autosync roepen allebei
    ``_run_sync`` aan; ``feed_ingest.ingest_feed`` doet delete-then-insert en zou
    bij overlap dubbele dagrijen kunnen opleveren).

    De lock draait op een **eigen** verbinding (niet de ORM-sessie die de ingest
    uitvoert), zodat een afgebroken ingest-transactie de unlock niet kan
    vergiftigen. Mislukt de unlock toch, dan wordt de fysieke verbinding
    geïnvalideerd; PostgreSQL geeft sessie-locks dan bij disconnect alsnog vrij —
    een lock kan dus nooit permanent blijven hangen en toekomstige syncs blokkeren.

    Levert True als de lock is verkregen, anders False (sync al bezig)."""
    from database import engine
    key = _advisory_key(name)
    conn = engine.connect()
    got = False
    try:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        yield got
    finally:
        try:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                conn.commit()
        except Exception:
            _log.warning(
                "Advisory-unlock voor connector %s mislukt; verbinding wordt geïnvalideerd.",
                name, exc_info=True,
            )
            try:
                conn.invalidate()
            except Exception:
                pass
        finally:
            conn.close()


def touch_last_synced(db: Session, name: str) -> None:
    """Werk ``last_synced_at`` atomisch bij (ook voor env-only connectors zonder
    bestaande config-rij). Gebruikt INSERT ... ON CONFLICT zodat gelijktijdige
    syncs niet racen op de unieke ``connector_name``-sleutel."""
    now = datetime.now(timezone.utc)
    stmt = (
        _pg_insert(models.ConnectorConfig)
        .values(connector_name=name, last_synced_at=now, created_at=now, updated_at=now)
        .on_conflict_do_update(
            index_elements=["connector_name"],
            set_={"last_synced_at": now, "updated_at": now},
        )
    )
    db.execute(stmt)
    db.commit()


# ── SSRF guard ─────────────────────────────────────────────────────────────

from connectors.net import validate_external_url as _validate_url, UnsafeURLError


def _validate_external_url(url: str) -> None:
    """
    Blokkeer SSRF via de gedeelde validator (connectors/net.py) en vertaal een
    onveilige URL naar een HTTP 400 voor de API-laag.
    """
    try:
        _validate_url(url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


# ── Connector-definitie ────────────────────────────────────────────────────

CONNECTOR_FIELDS = {
    "priceshape": [
        {"key": "mode", "label": "Verbindingstype", "required": False, "secret": False,
         "type": "select", "default": "rest", "placeholder": "",
         "options": [
             {"value": "rest", "label": "REST API (endpoint + sleutel)"},
             {"value": "feed", "label": "Output-feed (één URL: CSV/JSON/XML)"},
         ]},
        # REST-modus
        {"key": "api_url",    "label": "API URL",    "required": True,  "secret": False,
         "mode": "rest", "placeholder": "https://api.priceshape.com/v1"},
        {"key": "api_key",    "label": "API Sleutel", "required": True,  "secret": True,
         "mode": "rest", "placeholder": "ps_live_…"},
        {"key": "account_id", "label": "Account ID", "required": False, "secret": False,
         "mode": "rest", "placeholder": "optioneel"},
        # Feed-modus
        {"key": "feed_url", "label": "Feed-URL", "required": True, "secret": True,
         "mode": "feed",
         "placeholder": "https://public.priceshape.io/export/…?token=…"},
        {"key": "feed_format", "label": "Formaat", "required": False, "secret": False,
         "mode": "feed", "type": "select", "default": "auto", "placeholder": "",
         "options": [
             {"value": "auto", "label": "Automatisch detecteren"},
             {"value": "csv",  "label": "CSV"},
             {"value": "json", "label": "JSON"},
             {"value": "xml",  "label": "XML"},
         ]},
    ],
    "drs": [
        {"key": "api_url",   "label": "API URL",    "required": True,  "secret": False,
         "placeholder": "https://api.drs.example.com"},
        {"key": "api_key",   "label": "API Sleutel", "required": True,  "secret": True,
         "placeholder": "drs_…"},
        {"key": "tenant_id", "label": "Tenant ID",  "required": False, "secret": False,
         "placeholder": "optioneel"},
    ],
    "ga4": [
        {"key": "property_id",          "label": "Property ID",         "required": True,  "secret": False,
         "placeholder": "123456789"},
        {"key": "service_account_key",  "label": "Service Account JSON", "required": True,  "secret": True,
         "placeholder": '{"type": "service_account", …}'},
    ],
    "search_console": [
        {"key": "site_url", "label": "Site-URL / property", "required": True, "secret": False,
         "placeholder": "sc-domain:voorbeeld.nl of https://voorbeeld.nl/"},
        {"key": "service_account_key", "label": "Service Account JSON", "required": True, "secret": True,
         "placeholder": '{"type": "service_account", …}'},
    ],
    "google_ads": [
        {"key": "developer_token", "label": "Developer token", "required": True, "secret": True,
         "placeholder": "abc…"},
        {"key": "customer_id", "label": "Customer ID", "required": True, "secret": False,
         "placeholder": "1234567890 (zonder streepjes)"},
        {"key": "client_id", "label": "OAuth Client ID", "required": True, "secret": False,
         "placeholder": "….apps.googleusercontent.com"},
        {"key": "client_secret", "label": "OAuth Client Secret", "required": True, "secret": True,
         "placeholder": "GOCSPX-…"},
        {"key": "refresh_token", "label": "OAuth Refresh Token", "required": True, "secret": True,
         "placeholder": "1//…"},
    ],
    "microsoft_ads": [
        {"key": "developer_token", "label": "Developer token", "required": True, "secret": True,
         "placeholder": "1234ABCD…"},
        {"key": "customer_id", "label": "Customer ID", "required": True, "secret": False,
         "placeholder": "123456789"},
        {"key": "account_id", "label": "Account ID", "required": True, "secret": False,
         "placeholder": "987654321"},
        {"key": "client_id", "label": "OAuth Client ID (app)", "required": True, "secret": False,
         "placeholder": "00000000-0000-0000-0000-000000000000"},
        {"key": "client_secret", "label": "OAuth Client Secret", "required": True, "secret": True,
         "placeholder": "geheim…"},
        {"key": "refresh_token", "label": "OAuth Refresh Token", "required": True, "secret": True,
         "placeholder": "M.R3_BAY…"},
    ],
}

CONNECTOR_LABELS = {
    "priceshape": "PriceShape",
    "drs": "DRS Datareport",
    "ga4": "Google Analytics 4",
    "search_console": "Google Search Console",
    "google_ads": "Google Ads",
    "microsoft_ads": "Microsoft Ads",
}

VALID_CONNECTORS = set(CONNECTOR_FIELDS.keys())


def _validate_name(name: str) -> str:
    if name not in VALID_CONNECTORS:
        raise HTTPException(status_code=404, detail=f"Onbekende connector '{name}'. Kies uit: {', '.join(VALID_CONNECTORS)}")
    return name


def _resolve_mode(fields_def: list[dict], creds: dict) -> Optional[str]:
    """
    Bepaal de actieve modus voor een connector die meerdere verbindingsmodi kent.
    Geeft None terug als de connector geen 'mode'-veld heeft (enkel-modus connector).
    """
    mode_field = next((f for f in fields_def if f["key"] == "mode"), None)
    if not mode_field:
        return None
    valid = {o["value"] for o in mode_field.get("options", [])}
    chosen = (creds.get("mode") or "").strip().lower()
    if chosen in valid:
        return chosen
    return mode_field.get("default") or (next(iter(valid), None))


def _get_config(db: Session, name: str) -> Optional[models.ConnectorConfig]:
    return db.query(models.ConnectorConfig).filter(
        models.ConnectorConfig.connector_name == name
    ).first()


def _mask_fields(fields_configured: list[str] | None) -> dict[str, str]:
    """Geeft per geconfigureerd veld '••••• geconfigureerd' terug."""
    if not fields_configured:
        return {}
    return {k: "••••• geconfigureerd" for k in fields_configured}


def _connector_summary(db: Session, name: str) -> dict:
    cfg = _get_config(db, name)
    fields_def = CONNECTOR_FIELDS[name]
    required_keys = [f["key"] for f in fields_def if f["required"]]
    has_db_creds = bool(cfg and cfg.encrypted_credentials)

    configured_via_env = _check_env_configured(name)
    configured = has_db_creds or configured_via_env
    source = "db" if has_db_creds else ("env" if configured_via_env else None)

    return {
        "name": name,
        "label": CONNECTOR_LABELS[name],
        "configured": configured,
        "source": source,
        "fields": fields_def,
        "fields_filled": (cfg.fields_configured if cfg else None) or [],
        "masked_values": _mask_fields((cfg.fields_configured if cfg else None) or []),
        "last_test_status": cfg.last_test_status if cfg else None,
        "last_test_message": cfg.last_test_message if cfg else None,
        "last_tested_at": cfg.last_tested_at.isoformat() if cfg and cfg.last_tested_at else None,
        "last_synced_at": cfg.last_synced_at.isoformat() if cfg and cfg.last_synced_at else None,
        "configured_by": cfg.configured_by if cfg else None,
    }


def _check_env_configured(name: str) -> bool:
    import os
    if name == "priceshape":
        return bool(
            os.environ.get("PRICESHAPE_FEED_URL")
            or (os.environ.get("PRICESHAPE_API_URL") and os.environ.get("PRICESHAPE_API_KEY"))
        )
    if name == "drs":
        return bool(os.environ.get("DRS_API_URL") and os.environ.get("DRS_API_KEY"))
    if name == "ga4":
        return bool(os.environ.get("GA4_PROPERTY_ID") and os.environ.get("GA4_SERVICE_ACCOUNT_KEY"))
    if name == "search_console":
        return bool(os.environ.get("GSC_SITE_URL") and os.environ.get("GSC_SERVICE_ACCOUNT_KEY"))
    if name == "google_ads":
        from connectors.google_ads_connector import ENV_KEYS as _GA_ENV
        return all(os.environ.get(v) for v in _GA_ENV.values())
    if name == "microsoft_ads":
        from connectors.microsoft_ads_connector import ENV_KEYS as _MS_ENV
        return all(os.environ.get(v) for v in _MS_ENV.values())
    return False


# ── Pydantic request bodies ────────────────────────────────────────────────

class SaveCredsRequest(BaseModel):
    credentials: dict[str, str]


class TestCredsRequest(BaseModel):
    credentials: dict[str, str]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
def list_connectors(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Overzicht van alle 3 connectors met hun huidige configuratiestatus."""
    return [_connector_summary(db, name) for name in VALID_CONNECTORS]


@router.get("/{name}/status")
def get_connector_status(
    name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Live verbindingscheck voor een specifieke connector."""
    _validate_name(name)
    summary = _connector_summary(db, name)

    if not summary["configured"]:
        return {**summary, "live_status": "not_configured",
                "live_message": "Connector is niet geconfigureerd."}

    live = _run_live_check(name, db)
    return {**summary, "live_status": live["status"], "live_message": live["message"]}


@router.post("/{name}/test")
def test_connector(
    name: str,
    body: TestCredsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Test opgegeven credentials zonder ze op te slaan.
    Retourneert verbindingsstatus + bericht.
    """
    _validate_name(name)
    result = _test_credentials(name, body.credentials)
    return result


@router.post("/{name}/save")
def save_connector(
    name: str,
    body: SaveCredsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """
    Sla connector-credentials versleuteld op.
    Lege velden worden behouden vanuit de bestaande opgeslagen config (partial update).
    """
    _validate_name(name)

    # Merge incoming credentials with existing stored creds so "leave empty" works
    existing_creds = _get_decrypted_creds(name, db) or {}
    creds: dict[str, str] = {}
    for k, v in existing_creds.items():
        creds[k] = v
    for k, v in body.credentials.items():
        if v and v.strip():
            creds[k] = v.strip()

    # Bepaal de actieve modus (voor connectors met meerdere verbindingsmodi).
    fields_def = CONNECTOR_FIELDS[name]
    mode = _resolve_mode(fields_def, creds)
    if mode is not None:
        creds["mode"] = mode
        # Verwijder velden van de andere modus zodat de opgeslagen config
        # coherent blijft (geen achtergebleven REST-sleutel bij een feed-config).
        allowed = {
            f["key"] for f in fields_def
            if not f.get("mode") or f.get("mode") == mode
        }
        creds = {k: v for k, v in creds.items() if k in allowed}

    # Controleer vereiste velden (modus-bewust)
    required_keys = [
        f["key"] for f in fields_def
        if f["required"] and (not f.get("mode") or f.get("mode") == mode)
    ]
    missing = [k for k in required_keys if not creds.get(k, "").strip()]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f"Vereiste velden ontbreken: {', '.join(missing)}")

    # Test de verbinding vóór opslaan — alleen opslaan als de test slaagt
    test_result = _test_credentials(name, creds)
    if test_result.get("status") != "ok":
        raise HTTPException(
            status_code=422,
            detail=f"Verbindingstest mislukt ({test_result.get('status')}): "
                   f"{test_result.get('message', 'Onbekende fout')}. "
                   f"Los de verbindingsproblemen op voor je opslaat.",
        )

    # Bepaal welke velden zijn ingevuld (zonder geheimen te bewaren)
    fields_filled = [k for k, v in creds.items() if v and v.strip()]

    encrypted = encrypt_credentials(creds)
    now = datetime.now(timezone.utc)

    cfg = _get_config(db, name)
    if cfg:
        cfg.encrypted_credentials = encrypted
        cfg.fields_configured = fields_filled
        cfg.last_test_status = test_result["status"]
        cfg.last_test_message = test_result["message"]
        cfg.last_tested_at = now
        cfg.configured_by = current_user.username
        cfg.updated_at = now
    else:
        cfg = models.ConnectorConfig(
            connector_name=name,
            encrypted_credentials=encrypted,
            fields_configured=fields_filled,
            last_test_status=test_result["status"],
            last_test_message=test_result["message"],
            last_tested_at=now,
            configured_by=current_user.username,
            created_at=now,
            updated_at=now,
        )
        db.add(cfg)

    db.commit()
    db.refresh(cfg)

    return {
        "success": True,
        "message": "Connector opgeslagen.",
        "test_status": test_result["status"],
        "test_message": test_result["message"],
        "fields_filled": fields_filled,
    }


@router.delete("/{name}")
def disconnect_connector(
    name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """Verwijder opgeslagen credentials voor deze connector (ontkoppelen)."""
    _validate_name(name)
    cfg = _get_config(db, name)
    if cfg:
        db.delete(cfg)
        db.commit()
    return {"success": True, "message": f"Connector '{name}' ontkoppeld."}


@router.post("/{name}/sync")
def sync_connector(
    name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """Handmatige synchronisatie voor een connector."""
    _validate_name(name)

    cfg = _get_config(db, name)
    env_configured = _check_env_configured(name)
    if not cfg and not env_configured:
        raise HTTPException(status_code=400, detail="Connector is niet geconfigureerd.")

    # De sync verwerkt honderdduizenden rijen per DELETE/INSERT en overschrijdt
    # daarmee de strakke 4s request-timeout. Draai de zware ingest daarom op een
    # aparte sessie met ruime statement-timeout (zie database.py), niet op de
    # request-sessie.
    from database import BackgroundSessionLocal

    sync_db = BackgroundSessionLocal()
    try:
        result = _run_sync(name, sync_db, current_user)

        # Bijwerken van last_synced_at zodat de UI de laatste sync toont — óók
        # wanneer de connector alleen via omgevingsvariabelen is geconfigureerd.
        # Zonder dit bestaat er geen config-rij en zou "laatste sync" altijd
        # "nooit" blijven, hoe vaak de sync ook succesvol draait. Atomische
        # upsert voorkomt races.
        if result.get("status") == "ok":
            touch_last_synced(sync_db, name)
    finally:
        sync_db.close()

    return result


# ── Interne helpers ────────────────────────────────────────────────────────

def _get_decrypted_creds(name: str, db: Session) -> Optional[dict]:
    """Lees opgeslagen credentials uit DB. Geeft None als geen DB-config bestaat."""
    cfg = _get_config(db, name)
    if not cfg or not cfg.encrypted_credentials:
        return None
    try:
        return decrypt_credentials(cfg.encrypted_credentials)
    except Exception:
        return None


def _test_credentials(name: str, creds: dict) -> dict:
    """
    Test de opgegeven credentials tegen de externe API.
    Retourneert altijd {'status': str, 'message': str}.
    """
    try:
        if name == "priceshape":
            return _test_priceshape(creds)
        if name == "drs":
            return _test_drs(creds)
        if name == "ga4":
            return _test_ga4(creds)
        if name == "search_console":
            return _test_search_console(creds)
        if name == "google_ads":
            return _test_google_ads(creds)
        if name == "microsoft_ads":
            return _test_microsoft_ads(creds)
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:300]}
    return {"status": "error", "message": "Onbekende connector."}


def _run_live_check(name: str, db: Session) -> dict:
    """Voer een live verbindingscheck uit met de opgeslagen of env-credentials."""
    if name == "priceshape":
        from connectors import priceshape_connector
        return priceshape_connector.check_connection(db=db)
    if name == "drs":
        from connectors import drs_connector
        return drs_connector.check_connection(db=db)
    if name == "ga4":
        from connectors import ga4_connector
        return ga4_connector.check_connection(db=db)
    if name == "search_console":
        from connectors import search_console_connector
        return search_console_connector.check_connection(db=db)
    if name == "google_ads":
        from connectors import google_ads_connector
        return google_ads_connector.check_connection(db=db)
    if name == "microsoft_ads":
        from connectors import microsoft_ads_connector
        return microsoft_ads_connector.check_connection(db=db)
    return {"status": "error", "message": "Onbekende connector."}


def _run_sync(name: str, db: Session, current_user) -> dict:
    """Trigger de bijbehorende sync-logica en persisteer een ImportJob.

    Beschermd met een advisory lock: draait er al een sync voor deze connector
    (bijv. de geplande job én de in-process autosync tegelijk), dan wordt deze
    aanroep netjes overgeslagen in plaats van de delete-then-insert ingest te
    laten overlappen."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    date_30d = (date.today() - timedelta(days=30)).isoformat()

    status = "ok"
    message = ""
    counts: dict[str, int] = {}
    errors: list[str] = []

    with _sync_lock(name) as got_lock:
        if not got_lock:
            return {
                "status": "skipped",
                "message": f"Er draait al een synchronisatie voor {name}; deze is overgeslagen.",
                "counts": {},
            }

        try:
            if name == "priceshape":
                from connectors import priceshape_connector
                raw = priceshape_connector._get_raw_config(db=db)
                if priceshape_connector._get_mode(raw) == "feed":
                    import feed_ingest
                    res = feed_ingest.ingest_feed(db, source="priceshape")
                    counts["producten_nieuw"] = res["products_new"]
                    counts["producten_bijgewerkt"] = res["products_updated"]
                    counts["eigen_prijzen"] = res["own_prices"]
                    counts["concurrentprijzen"] = res["competitor_rows"]
                    counts["beschikbaarheidsrijen"] = res.get("offer_rows", 0)
                    counts["overgeslagen_door_instellingen"] = res.get("skipped_by_settings", 0)
                    skipped_note = (
                        f" {res['skipped_by_settings']} rijen overgeslagen door importinstellingen."
                        if res.get("skipped_by_settings") else ""
                    )
                    message = (
                        f"PriceShape feed-sync voltooid: {res['products_total']} producten "
                        f"({res['products_new']} nieuw, {res['products_updated']} bijgewerkt), "
                        f"{res['competitor_rows']} concurrentprijzen ingelezen."
                        + skipped_note +
                        " Draai een modelrun om aanbevelingen en concurrentie-scores te vernieuwen."
                    )
                else:
                    priceshape_connector._get_credentials(db=db)
                    prices = priceshape_connector.fetch_competitor_prices(db=db)
                    counts["price_records"] = len(prices)
                    message = f"PriceShape sync voltooid: {len(prices)} prijzen opgehaald."

            elif name == "drs":
                from connectors import drs_connector
                drs_connector._get_credentials(db=db)
                products = drs_connector.fetch_product_catalog(db=db)
                counts["products"] = len(products)
                sales = drs_connector.fetch_sales_history(date_from=date_30d, date_to=today, db=db)
                counts["sales_records"] = len(sales)
                stock = drs_connector.fetch_stock_levels(db=db)
                counts["stock_records"] = len(stock)
                message = "DRS sync voltooid."

            elif name == "ga4":
                from connectors import ga4_connector
                ga4_connector._get_credentials(db=db)
                traffic = ga4_connector.fetch_traffic_data(date_from=date_30d, date_to=today, db=db)
                counts["traffic_records"] = len(traffic)
                conversions = ga4_connector.fetch_conversion_data(date_from=date_30d, date_to=today, db=db)
                counts["conversion_records"] = len(conversions)
                message = "GA4 sync voltooid."

            elif name == "search_console":
                from connectors import search_console_connector
                rows = search_console_connector.fetch_search_analytics(
                    date_from=date_30d, date_to=today, db=db)
                counts["zoekterm_records"] = len(rows)
                message = f"Search Console sync voltooid: {len(rows)} zoekterm-rijen opgehaald."

            elif name == "google_ads":
                from connectors import google_ads_connector
                rows = google_ads_connector.fetch_campaign_costs(
                    date_from=date_30d, date_to=today, db=db)
                counts["campagne_kostenrijen"] = len(rows)
                message = f"Google Ads sync voltooid: {len(rows)} campagne-kostenrijen opgehaald."

            elif name == "microsoft_ads":
                from connectors import microsoft_ads_connector
                rows = microsoft_ads_connector.fetch_campaign_costs(
                    date_from=date_30d, date_to=today, db=db)
                counts["campagne_kostenrijen"] = len(rows)
                message = f"Microsoft Ads sync voltooid: {len(rows)} campagne-kostenrijen opgehaald."

        except Exception as exc:
            status = "error" if "ConnectorError" not in type(exc).__name__ else "not_configured"
            message = str(exc)[:300]

        # Persisteer een ImportJob zodat de sync zichtbaar is in de importgeschiedenis
        try:
            from database import SessionLocal
            db_local = SessionLocal()
            try:
                job_status = "geimporteerd" if status == "ok" else ("fout" if status == "error" else "nieuw")
                from engine.import_engine import new_batch_id as _new_batch_id
                db_local.add(models.ImportJob(
                    batch_id=_new_batch_id(),
                    upload_type=f"api_sync_{name}",
                    filename=f"handmatige-sync-{name}",
                    source="API-Sync",
                    status=job_status,
                    rows_processed=sum(counts.values()),
                    rows_failed=0,
                    rows_duplicates=0,
                    error_log=([{"rij": None, "veld": None, "bericht": message}]
                               if status != "ok" else []),
                    error_message=message if status != "ok" else None,
                    uploaded_by=current_user.username,
                    created_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                ))
                db_local.commit()
            finally:
                db_local.close()
        except Exception:
            pass

        return {"status": status, "message": message, "counts": counts}


# ── Connector-specifieke testfuncties ──────────────────────────────────────

def _test_priceshape(creds: dict) -> dict:
    if _resolve_mode(CONNECTOR_FIELDS["priceshape"], creds) == "feed":
        return _test_priceshape_feed(creds)

    api_url = creds.get("api_url", "").rstrip("/")
    api_key = creds.get("api_key", "")
    account_id = creds.get("account_id", "")

    if not api_url or not api_key:
        return {"status": "not_configured", "message": "API URL en API Sleutel zijn verplicht."}

    _validate_external_url(api_url)

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        if account_id:
            headers["X-Account-ID"] = account_id

        with httpx.Client(timeout=10) as client:
            for path in ["/health", "/status", "/ping", "/v1/products"]:
                try:
                    resp = client.get(f"{api_url}{path}", headers=headers)
                    if resp.status_code == 401:
                        return {"status": "auth_error", "message": "Authenticatie mislukt (401). Controleer de API Sleutel."}
                    if resp.status_code == 403:
                        return {"status": "auth_error", "message": "Toegang geweigerd (403). Controleer de API Sleutel / Account ID."}
                    if resp.status_code < 500:
                        return {"status": "ok", "message": f"Verbinding geslaagd (HTTP {resp.status_code} op {path})."}
                except httpx.ConnectError:
                    continue
        return {"status": "unreachable", "message": f"PriceShape API niet bereikbaar op {api_url}."}
    except ImportError:
        return {"status": "error", "message": "httpx niet geïnstalleerd."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:200]}


def _test_priceshape_feed(creds: dict) -> dict:
    """
    Test de PriceShape output-feed: haal de URL op, detecteer het formaat
    (CSV/JSON/XML), parse een sample en controleer of de vereiste kolommen
    (SKU/EAN/OEM + concurrentprijs + concurrentnaam) herkend worden.
    """
    feed_url = (creds.get("feed_url") or "").strip()
    if not feed_url:
        return {"status": "not_configured", "message": "Feed-URL is verplicht."}

    try:
        _validate_external_url(feed_url)
    except HTTPException as exc:
        return {"status": "error", "message": str(exc.detail)}

    from connectors import priceshape_connector
    from connectors.priceshape_connector import ConnectorError
    from routes.priceshape import (
        get_alias, COMPETITOR_PRICE_ALIASES, COMPETITOR_NAME_ALIASES,
        SKU_ALIASES, EAN_ALIASES, OEM_ALIASES,
    )

    declared = creds.get("feed_format") or "auto"
    try:
        # Alleen het begin van de feed ophalen (streaming, ~5 MB): genoeg om formaat
        # en kolommen te valideren zonder de volledige — mogelijk honderden MB's —
        # feed te downloaden. Zo blijft de test snel en binnen de client-time-out.
        content, content_type = priceshape_connector._stream_feed_sample(feed_url)
        detected = priceshape_connector._detect_feed_format(content, content_type, declared)
        rows = priceshape_connector._parse_feed_sample(content, content_type, detected)
    except ConnectorError as exc:
        return {"status": "unreachable", "message": str(exc)[:250]}
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:250]}

    if not rows:
        return {"status": "error",
                "message": f"Feed opgehaald (formaat: {detected}) maar geen rijen gevonden."}

    sample = rows[0]
    has_identifier = bool(
        get_alias(sample, *SKU_ALIASES)
        or get_alias(sample, *EAN_ALIASES)
        or get_alias(sample, *OEM_ALIASES)
    )
    has_price = bool(get_alias(sample, *COMPETITOR_PRICE_ALIASES))
    has_name = bool(get_alias(sample, *COMPETITOR_NAME_ALIASES))

    if not (has_identifier and has_price):
        missing = []
        if not has_identifier:
            missing.append("SKU/EAN/OEM-identifier")
        if not has_price:
            missing.append("concurrentprijs")
        if not has_name:
            missing.append("concurrentnaam")
        cols = ", ".join(sorted(sample.keys())[:12])
        return {
            "status": "error",
            "message": (
                f"Feed opgehaald (formaat: {detected}) maar vereiste kolommen "
                f"ontbreken: {', '.join(missing)}. Gevonden kolommen: {cols}."
            ),
        }

    name_note = "" if has_name else " (let op: concurrentnaam-kolom niet herkend)"
    return {
        "status": "ok",
        "message": (
            f"Feed geldig (formaat: {detected}). Vereiste kolommen herkend"
            f"{name_note}."
        ),
    }


def _test_drs(creds: dict) -> dict:
    api_url = creds.get("api_url", "").rstrip("/")
    api_key = creds.get("api_key", "")
    tenant_id = creds.get("tenant_id", "")

    if not api_url or not api_key:
        return {"status": "not_configured", "message": "API URL en API Sleutel zijn verplicht."}

    _validate_external_url(api_url)

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        with httpx.Client(timeout=10) as client:
            for path in ["/health", "/api/health", "/status", "/api/products"]:
                try:
                    resp = client.get(f"{api_url}{path}", headers=headers)
                    if resp.status_code == 401:
                        return {"status": "auth_error", "message": "Authenticatie mislukt (401). Controleer de API Sleutel."}
                    if resp.status_code == 403:
                        return {"status": "auth_error", "message": "Toegang geweigerd (403)."}
                    if resp.status_code < 500:
                        return {"status": "ok", "message": f"Verbinding geslaagd (HTTP {resp.status_code} op {path})."}
                except httpx.ConnectError:
                    continue
        return {"status": "unreachable", "message": f"DRS API niet bereikbaar op {api_url}."}
    except ImportError:
        return {"status": "error", "message": "httpx niet geïnstalleerd."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:200]}


def _test_ga4(creds: dict) -> dict:
    property_id = creds.get("property_id", "").strip()
    sa_key_raw = creds.get("service_account_key", "").strip()

    if not property_id or not sa_key_raw:
        return {"status": "not_configured", "message": "Property ID en Service Account JSON zijn verplicht."}

    import json as _json
    try:
        sa_key = _json.loads(sa_key_raw)
    except _json.JSONDecodeError as exc:
        return {"status": "error", "message": f"Service Account JSON is ongeldig: {exc}"}

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            sa_key,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        client = BetaAnalyticsDataClient(credentials=credentials)
        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date="yesterday", end_date="yesterday")],
            metrics=[Metric(name="sessions")],
            limit=1,
        )
        client.run_report(request=request)
        return {"status": "ok", "message": f"Verbinding geslaagd met GA4 property {property_id}."}
    except ImportError:
        return {"status": "error",
                "message": "google-analytics-data SDK niet geïnstalleerd. "
                           "Credentials zijn geldig maar kunnen niet live getest worden."}
    except Exception as exc:
        msg = str(exc)
        if "403" in msg or "PERMISSION_DENIED" in msg:
            return {"status": "auth_error", "message": "Toegang geweigerd (403). Controleer de GA4 Viewer-rechten van het service account."}
        if "404" in msg or "NOT_FOUND" in msg:
            return {"status": "error", "message": f"Property ID {property_id} niet gevonden."}
        return {"status": "error", "message": msg[:200]}


def _test_search_console(creds: dict) -> dict:
    site_url = (creds.get("site_url") or "").strip()
    sa_key = (creds.get("service_account_key") or "").strip()
    if not site_url or not sa_key:
        return {"status": "not_configured", "message": "Site-URL en Service Account JSON zijn verplicht."}
    from connectors import search_console_connector as gsc
    try:
        token = gsc._access_token(sa_key)
    except gsc.ConnectorError as exc:
        return {"status": "error", "message": str(exc)}
    try:
        import httpx
        from urllib.parse import quote
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{gsc.API_BASE}/sites/{quote(site_url, safe='')}",
                              headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            return {"status": "ok", "message": f"Verbonden met Search Console-property {site_url}."}
        if resp.status_code in (401, 403):
            return {"status": "auth_error",
                    "message": f"Toegang geweigerd ({resp.status_code}). Voeg het service-account toe als "
                               f"gebruiker (Volledig/Beperkt) op de property in Search Console."}
        if resp.status_code == 404:
            return {"status": "error", "message": f"Property '{site_url}' niet gevonden in Search Console."}
        return {"status": "error", "message": f"Onverwachte respons: HTTP {resp.status_code}."}
    except Exception as exc:
        return {"status": "unreachable", "message": str(exc)[:200]}


def _test_google_ads(creds: dict) -> dict:
    from connectors import google_ads_connector as gads
    missing = [k for k in gads.REQUIRED_KEYS if not (creds.get(k) or "").strip()]
    if missing:
        return {"status": "not_configured", "message": f"Vereiste velden ontbreken: {', '.join(missing)}."}
    try:
        gads._access_token(creds)
        return {"status": "ok",
                "message": f"OAuth-verbinding met Google Ads geslaagd (customer {creds['customer_id']})."}
    except gads.ConnectorError as exc:
        msg = str(exc)
        if "invalid_grant" in msg or "invalid_client" in msg:
            return {"status": "auth_error", "message": msg}
        return {"status": "unreachable" if "bereikbaar" in msg else "error", "message": msg}


def _test_microsoft_ads(creds: dict) -> dict:
    from connectors import microsoft_ads_connector as msads
    missing = [k for k in msads.REQUIRED_KEYS if not (creds.get(k) or "").strip()]
    if missing:
        return {"status": "not_configured", "message": f"Vereiste velden ontbreken: {', '.join(missing)}."}
    try:
        token = msads._access_token(creds)
    except msads.ConnectorError as exc:
        msg = str(exc)
        if "invalid_grant" in msg or "invalid_client" in msg:
            return {"status": "auth_error", "message": msg}
        return {"status": "unreachable" if "bereikbaar" in msg else "error", "message": msg}
    try:
        code = msads._soap_get_user(token, creds["developer_token"])
        if code == 200:
            return {"status": "ok", "message": f"Verbonden met Microsoft Ads (customer {creds['customer_id']})."}
        if code in (401, 403):
            return {"status": "auth_error",
                    "message": f"Toegang geweigerd ({code}). Controleer het developer token."}
        return {"status": "error", "message": f"Microsoft Ads API antwoordde met HTTP {code}."}
    except Exception as exc:
        return {"status": "unreachable", "message": str(exc)[:200]}
