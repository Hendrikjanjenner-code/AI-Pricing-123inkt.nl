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
    assert summary["default_feed_url"] == pc.DEFAULT_FEED_URL


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
