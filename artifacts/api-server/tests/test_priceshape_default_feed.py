"""
Tests voor de ingebouwde standaard-feed-URL van de PriceShape-connector.

Contract: de feed-URL mag nooit stilzwijgend "verdwijnen". Volgorde:
DB-config → omgevingsvariabelen → ingebouwde standaard (DEFAULT_FEED_URL).
"""
import os

import pytest

from connectors import priceshape_connector as pc
from database import SessionLocal
import models
from connectors.crypto import encrypt_credentials


def _clear_env(monkeypatch):
    for k in ("PRICESHAPE_FEED_URL", "PRICESHAPE_FEED_FORMAT",
              "PRICESHAPE_API_URL", "PRICESHAPE_API_KEY", "PRICESHAPE_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _del_db_config(db):
    db.query(models.ConnectorConfig).filter(
        models.ConnectorConfig.connector_name == "priceshape").delete()
    db.commit()


def test_default_feed_url_when_nothing_configured(monkeypatch, db):
    _clear_env(monkeypatch)
    _del_db_config(db)
    cfg = pc._get_feed_config(db=db)
    assert cfg["feed_url"] == pc.DEFAULT_FEED_URL
    assert cfg["feed_format"] == "auto"
    assert pc._get_mode(pc._get_raw_config(db=db)) == "feed"
    assert pc.is_default_feed_active(db=db) is True


def test_env_var_overrides_default(monkeypatch, db):
    _clear_env(monkeypatch)
    _del_db_config(db)
    monkeypatch.setenv("PRICESHAPE_FEED_URL", "https://example.com/custom-feed")
    cfg = pc._get_feed_config(db=db)
    assert cfg["feed_url"] == "https://example.com/custom-feed"
    assert pc.is_default_feed_active(db=db) is False


def test_db_config_overrides_env_and_default(monkeypatch, db):
    _clear_env(monkeypatch)
    _del_db_config(db)
    monkeypatch.setenv("PRICESHAPE_FEED_URL", "https://example.com/env-feed")
    db.add(models.ConnectorConfig(
        connector_name="priceshape",
        encrypted_credentials=encrypt_credentials(
            {"mode": "feed", "feed_url": "https://example.com/db-feed"}),
        fields_configured=["mode", "feed_url"],
    ))
    db.commit()
    try:
        cfg = pc._get_feed_config(db=db)
        assert cfg["feed_url"] == "https://example.com/db-feed"
        assert pc.is_default_feed_active(db=db) is False
    finally:
        _del_db_config(db)


def test_disconnect_falls_back_to_default(monkeypatch, db):
    """Na verwijderen van de DB-config (ontkoppelen) is de standaard weer actief."""
    _clear_env(monkeypatch)
    db.add(models.ConnectorConfig(
        connector_name="priceshape",
        encrypted_credentials=encrypt_credentials(
            {"mode": "feed", "feed_url": "https://example.com/db-feed"}),
        fields_configured=["mode", "feed_url"],
    ))
    db.commit()
    _del_db_config(db)  # = ontkoppelen
    cfg = pc._get_feed_config(db=db)
    assert cfg["feed_url"] == pc.DEFAULT_FEED_URL
    assert pc.is_default_feed_active(db=db) is True


def test_summary_reports_default_source(monkeypatch, db):
    _clear_env(monkeypatch)
    _del_db_config(db)
    from routes import connectors as rc
    summary = rc._connector_summary(db, "priceshape")
    assert summary["configured"] is True
    assert summary["source"] == "default"


def test_summary_never_leaks_default_feed_url(monkeypatch, db):
    """De standaard-feed-URL bevat een opaque export-token en mag nooit in de
    connector-samenvatting (of foutmeldingen daarin) richting de UI lekken."""
    import json
    from urllib.parse import urlparse
    from routes import connectors as rc
    _clear_env(monkeypatch)
    _del_db_config(db)
    token = urlparse(pc.DEFAULT_FEED_URL).path.rstrip("/").split("/")[-1]
    summary = rc._connector_summary(db, "priceshape")
    blob = json.dumps(summary)
    assert pc.DEFAULT_FEED_URL not in blob
    assert token not in blob, "opaque export-token lekt via de connector-samenvatting"


def test_summary_exposes_failed_last_sync(monkeypatch, db):
    """Een mislukte (geplande) sync is als last_sync_status='error' + reden
    zichtbaar in de connector-samenvatting, zodat de kaart kan waarschuwen
    dat de standaard-feed faalt."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from datetime import datetime, timezone
    from engine.import_engine import new_batch_id
    from routes import connectors as rc
    job = models.ImportJob(
        batch_id=new_batch_id(),
        upload_type="api_sync_priceshape",
        filename="handmatige-sync-priceshape",
        source="API-Sync",
        status="fout",
        error_message="Feed onbereikbaar: HTTP 403",
        uploaded_by="system-autosync",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    try:
        summary = rc._connector_summary(db, "priceshape")
        assert summary["last_sync_status"] == "error"
        assert "onbereikbaar" in (summary["last_sync_message"] or "")
        assert summary["last_sync_attempt_at"] is not None
    finally:
        db.delete(job)
        db.commit()


def test_summary_exposes_ok_last_sync(monkeypatch, db):
    """Een geslaagde sync toont last_sync_status='ok' zonder foutbericht."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from datetime import datetime, timezone
    from engine.import_engine import new_batch_id
    from routes import connectors as rc
    job = models.ImportJob(
        batch_id=new_batch_id(),
        upload_type="api_sync_priceshape",
        filename="handmatige-sync-priceshape",
        source="API-Sync",
        status="geimporteerd",
        uploaded_by="system-autosync",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    try:
        summary = rc._connector_summary(db, "priceshape")
        assert summary["last_sync_status"] == "ok"
        assert summary["last_sync_message"] is None
    finally:
        db.delete(job)
        db.commit()


def test_scheduler_failure_after_ingest_shows_error_on_card(monkeypatch, db):
    """Faalt de geplande sync buiten _run_sync (bijv. de modelrun ná een
    geslaagde ingest), dan moet er toch een fout-ImportJob komen zodat de
    connector-kaart 'mislukt' + reden toont in plaats van 'geslaagd'."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from datetime import datetime, timezone
    from engine.import_engine import new_batch_id
    from routes import connectors as rc
    from services import feed_sync_scheduler as fss

    # Simuleer een eerdere geslaagde ingest-job (zou zonder fix 'ok' tonen).
    ok_job = models.ImportJob(
        batch_id=new_batch_id(), upload_type="api_sync_priceshape",
        filename="handmatige-sync-priceshape", source="API-Sync",
        status="geimporteerd", uploaded_by="system-autosync",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(ok_job)
    db.commit()

    def boom():
        raise RuntimeError("modelrun kapot met token abcdefghijklmnopqrstuvwxyz123456")

    monkeypatch.setattr(fss, "_run_sync_once", boom)
    try:
        fss._run_sync_with_retries(max_retries=1, backoff_base=1)
        db.expire_all()
        summary = rc._connector_summary(db, "priceshape")
        assert summary["last_sync_status"] == "error"
        msg = summary["last_sync_message"] or ""
        assert "Geplande sync mislukt" in msg
        # Redactie: lange token-achtige strings mogen niet in de reden staan.
        assert "abcdefghijklmnopqrstuvwxyz123456" not in msg
        assert summary["last_test_status"] == "error"
    finally:
        db.query(models.ImportJob).filter(
            models.ImportJob.upload_type == "api_sync_priceshape",
            models.ImportJob.uploaded_by == "system-autosync",
        ).delete()
        db.query(models.ConnectorConfig).filter(
            models.ConnectorConfig.connector_name == "priceshape").delete()
        db.commit()


def test_failed_sync_message_is_redacted(monkeypatch, db):
    """Een gewone mislukte feed-sync (bijv. onbereikbare feed) mag nooit een
    token/credential-URL in ImportJob, connectorstatus of samenvatting lekken."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from types import SimpleNamespace
    import feed_ingest
    from routes import connectors as rc

    token = "supersecrettoken1234567890abcdef"

    class FakeConnectorError(Exception):
        pass
    FakeConnectorError.__name__ = "PriceShapeConnectorError"

    def boom(db_, source="priceshape"):
        raise FakeConnectorError(
            f"Feed niet bereikbaar: https://feed.example.com/export?key={token} gaf HTTP 403")

    monkeypatch.setattr(feed_ingest, "ingest_feed", boom)
    try:
        result = rc._run_sync("priceshape", db, SimpleNamespace(username="tester"))
        assert result["status"] == "error"
        assert token not in result["message"]
        db.expire_all()
        summary = rc._connector_summary(db, "priceshape")
        assert summary["last_sync_status"] == "error"
        assert token not in (summary["last_sync_message"] or "")
        assert token not in (summary["last_test_message"] or "")
    finally:
        db.rollback()
        db.query(models.ImportJob).filter(
            models.ImportJob.upload_type == "api_sync_priceshape",
            models.ImportJob.uploaded_by == "tester",
        ).delete()
        db.query(models.ConnectorConfig).filter(
            models.ConnectorConfig.connector_name == "priceshape").delete()
        db.commit()


def test_scheduler_treats_default_feed_as_configured(monkeypatch, db):
    """De geplande sync mag de ingebouwde standaard-feed nooit overslaan."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from services.feed_sync_scheduler import _is_priceshape_configured
    assert _is_priceshape_configured(db) is True


def test_save_with_explicit_blank_resets_to_default(monkeypatch, db):
    """Een expliciet leeggemaakte feed-URL reset naar de standaard, ook als er
    al een eigen URL was opgeslagen."""
    _clear_env(monkeypatch)
    _del_db_config(db)
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    login = client.post("/api/auth/login",
                        json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    # Verbindingstest overslaan zodat er geen echte URL nodig is.
    import routes.connectors as rc
    monkeypatch.setattr(rc, "_test_credentials",
                        lambda name, creds: {"status": "ok", "message": "ok"})

    try:
        # 1) Eigen URL opslaan.
        r = client.post("/api/connectors/priceshape/save", headers=headers,
                        json={"credentials": {"mode": "feed",
                                              "feed_url": "https://example.com/custom"}})
        assert r.status_code == 200
        assert pc._get_feed_config(db=db)["feed_url"] == "https://example.com/custom"
        # 2) Expliciet leegmaken → reset naar de standaard.
        r = client.post("/api/connectors/priceshape/save", headers=headers,
                        json={"credentials": {"mode": "feed", "feed_url": ""}})
        assert r.status_code == 200
        db.expire_all()
        assert pc._get_feed_config(db=db)["feed_url"] == pc.DEFAULT_FEED_URL
    finally:
        _del_db_config(db)


def test_rest_env_still_takes_precedence_over_default(monkeypatch, db):
    _clear_env(monkeypatch)
    _del_db_config(db)
    monkeypatch.setenv("PRICESHAPE_API_URL", "https://api.priceshape.com/v1")
    monkeypatch.setenv("PRICESHAPE_API_KEY", "ps_test")
    raw = pc._get_raw_config(db=db)
    assert raw["mode"] == "rest"
    assert pc.is_default_feed_active(db=db) is False


# ── Expliciete-bron-vereiste (taak 299) ─────────────────────────────────────

def test_sync_refuses_unconfirmed_default_feed(monkeypatch, db):
    """Zonder expliciete bron (geen DB-config, geen env) weigert de sync met
    een duidelijke melding, mét fout-ImportJob — en zonder ook maar iets in
    te lezen (ingest_feed mag niet aangeroepen worden)."""
    from types import SimpleNamespace
    import feed_ingest
    import routes.connectors as rc

    _clear_env(monkeypatch)
    _del_db_config(db)

    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("ingest_feed mag niet draaien bij onbevestigde standaard-feed")

    monkeypatch.setattr(feed_ingest, "ingest_feed", boom)
    user = SimpleNamespace(username="test-default-refusal")
    try:
        result = rc._run_sync("priceshape", db, user)
        assert result["status"] == "error"
        assert "geen expliciete bron" in result["message"]
        assert "standaard-feed" in result["message"]
        # Geen stille 'not_configured'-maskering: het is een echte fout.
        assert called["n"] == 0

        job = db.query(models.ImportJob).filter(
            models.ImportJob.uploaded_by == "test-default-refusal",
            models.ImportJob.upload_type == "api_sync_priceshape",
        ).order_by(models.ImportJob.created_at.desc()).first()
        assert job is not None and job.status == "fout"
        assert "geen expliciete bron" in (job.error_message or "")
    finally:
        db.query(models.ImportJob).filter(
            models.ImportJob.uploaded_by == "test-default-refusal").delete()
        cfg = db.query(models.ConnectorConfig).filter(
            models.ConnectorConfig.connector_name == "priceshape").first()
        if cfg is not None and not cfg.encrypted_credentials:
            db.delete(cfg)
        db.commit()


def test_sync_runs_after_default_feed_confirmed_via_save(monkeypatch, db):
    """Bevestiging = opslaan van de feed-config (het save-endpoint persisteert
    bij een leeg feed-URL-veld expliciet DEFAULT_FEED_URL als DB-config).
    Daarna draait de sync gewoon, met de bron zichtbaar in de melding."""
    from types import SimpleNamespace
    import feed_ingest
    import routes.connectors as rc

    _clear_env(monkeypatch)
    _del_db_config(db)
    # Zoals het save-endpoint doet bij een leeg feed_url-veld:
    db.add(models.ConnectorConfig(
        connector_name="priceshape",
        encrypted_credentials=encrypt_credentials(
            {"mode": "feed", "feed_url": pc.DEFAULT_FEED_URL}),
        fields_configured=["mode", "feed_url"],
    ))
    db.commit()

    monkeypatch.setattr(rc, "_ingest_feed_with_retry", lambda *a, **k: {
        "products_new": 1, "products_updated": 0, "products_total": 1,
        "own_prices": 1, "competitor_rows": 2, "offer_rows": 0,
        "skipped_by_settings": 0, "warnings": [],
        "competitor_reconciliation": None,
    })
    user = SimpleNamespace(username="test-default-confirm")
    try:
        result = rc._run_sync("priceshape", db, user)
        assert result["status"] == "ok", result["message"]
        # Effectieve bron zichtbaar in de sync-melding (geredigeerd).
        assert "Bron:" in result["message"]
        assert "eigen configuratie" in result["message"]
    finally:
        db.query(models.ImportJob).filter(
            models.ImportJob.uploaded_by == "test-default-confirm").delete()
        _del_db_config(db)


def test_redact_url_strips_userinfo_query_and_short_path_tokens():
    """Redactie mag nooit afhangen van tokenlengte: basic-auth-userinfo,
    korte pad-tokens, query en fragment verdwijnen allemaal."""
    assert pc.redact_url("https://user:geheim@host.example/export/abc123?...token=x#f") == \
        "https://host.example/[…]"
    assert "geheim" not in pc.redact_url("https://user:geheim@host.example/feed")
    assert pc.redact_url("https://host.example/x7?k=v") == "https://host.example/[…]"
    assert pc.redact_url("https://host.example:8443/") == "https://host.example:8443/"
    assert pc.redact_url("") == ""


def test_effective_source_label_never_leaks_credentials(monkeypatch, db):
    """Ook via describe_feed_source (summary + sync-melding) lekt een
    basic-auth-feed-URL geen credentials of korte tokens."""
    _del_db_config(db)
    monkeypatch.setenv("PRICESHAPE_FEED_URL",
                       "https://user:geheim@feeds.example/exp/ab12?sig=kort")
    src = pc.describe_feed_source(db)
    blob = f"{src['label']} {src['url']}"
    for verboden in ("geheim", "user:", "sig=", "ab12"):
        assert verboden not in blob, verboden
    assert "feeds.example" in src["url"]


def test_summary_exposes_redacted_effective_feed_source(monkeypatch, db):
    from routes import connectors as rc
    _clear_env(monkeypatch)
    _del_db_config(db)
    summary = rc._connector_summary(db, "priceshape")
    src = summary["effective_feed_source"]
    assert src is not None
    assert src["origin"] == "default"
    assert src["mode"] == "feed"
    assert "onbevestigd" in src["label"]
    # Geredigeerd: geen token/querystring (gedekt door de leaktest hierboven).
    assert "?" not in (src["url"] or "")
