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
}

CONNECTOR_LABELS = {
    "priceshape": "PriceShape",
    "drs": "DRS Datareport",
    "ga4": "Google Analytics 4",
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

    result = _run_sync(name, db, current_user)

    # Bijwerken van last_synced_at
    if cfg and result.get("status") in ("ok",):
        cfg.last_synced_at = datetime.now(timezone.utc)
        db.commit()
    elif result.get("status") in ("ok",):
        # Env-only configured — maak een config-rij aan voor de sync-tijdstempel
        pass

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
    return {"status": "error", "message": "Onbekende connector."}


def _run_sync(name: str, db: Session, current_user) -> dict:
    """Trigger de bijbehorende sync-logica en persisteer een ImportJob."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    date_30d = (date.today() - timedelta(days=30)).isoformat()

    status = "ok"
    message = ""
    counts: dict[str, int] = {}
    errors: list[str] = []

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
                message = (
                    f"PriceShape feed-sync voltooid: {res['products_total']} producten "
                    f"({res['products_new']} nieuw, {res['products_updated']} bijgewerkt), "
                    f"{res['competitor_rows']} concurrentprijzen ingelezen. "
                    "Draai een modelrun om aanbevelingen en concurrentie-scores te vernieuwen."
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

    except Exception as exc:
        status = "error" if "ConnectorError" not in type(exc).__name__ else "not_configured"
        message = str(exc)[:300]

    # Persisteer een ImportJob zodat de sync zichtbaar is in de importgeschiedenis
    try:
        from database import SessionLocal
        db_local = SessionLocal()
        try:
            job_status = "geimporteerd" if status == "ok" else ("fout" if status == "error" else "nieuw")
            db_local.add(models.ImportJob(
                upload_type=f"api_sync_{name}",
                filename=f"handmatige-sync-{name}",
                source="API-Sync",
                status=job_status,
                rows_processed=sum(counts.values()),
                rows_failed=0,
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
