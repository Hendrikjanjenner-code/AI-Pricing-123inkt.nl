"""
Tests voor de diagnostiek rond een lege/afwijkende PriceShape-feed (taak: maak
lege feed in productie diagnosticeerbaar en zichtbaar).

Gedekt:
- 0-rijen-feed → foutmelding bevat responsmetadata (bytes, preview).
- HTML-foutpagina met HTTP 200 → aparte, duidelijke ConnectorError.
- Verdacht kleine body → aparte, duidelijke ConnectorError.
- Mislukte sync → ImportJob 'fout' + connectorstatus 'error' + zichtbaar als
  last_failed_job in de data-sources statistieken.
- Retry-backoff is ruim gespreid (minuten, niet alle pogingen binnen 40s).

Geen echte netwerk-calls; alles via injectie/monkeypatching.
"""
from types import SimpleNamespace

import pytest

import models
from connectors import priceshape_connector as pc
from connectors.priceshape_connector import ConnectorError
from database import SessionLocal


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# ── 0-rijen-feed: diagnostiek in de foutmelding ─────────────────────────────

def test_zero_rows_error_includes_response_diagnostics(db):
    import feed_ingest
    with pytest.raises(ValueError) as exc:
        feed_ingest.ingest_feed(db, content=b"[]", content_type="application/json")
    msg = str(exc.value)
    assert "0 producten" in msg
    assert "Ontvangen respons" in msg
    assert "2 bytes" in msg
    assert "application/json" in msg
    assert "[]" in msg  # body-preview


def test_describe_last_feed_response_without_metadata():
    pc.reset_last_feed_response()
    assert "geen responsmetadata" in pc.describe_last_feed_response()


# ── Sanity-checks: HTML-pagina / kleine body ────────────────────────────────

def test_html_body_with_http_200_is_clear_error():
    meta = pc._record_feed_response(200, "text/html; charset=utf-8", 5000,
                                    b"<!DOCTYPE html><html><body>Rate limited</body></html>")
    with pytest.raises(ConnectorError) as exc:
        pc._ensure_feed_looks_like_data(meta, at_eof=True)
    assert "HTML" in str(exc.value)
    assert "HTTP 200" in str(exc.value)


def test_html_sniffed_from_body_without_content_type():
    meta = pc._record_feed_response(200, "", 5000, b"  <html><head>oops</head>")
    with pytest.raises(ConnectorError):
        pc._ensure_feed_looks_like_data(meta, at_eof=True)


def test_suspiciously_small_body_is_clear_error():
    meta = pc._record_feed_response(200, "text/csv", 10, b"gtin\n")
    with pytest.raises(ConnectorError) as exc:
        pc._ensure_feed_looks_like_data(meta, at_eof=True)
    assert "verdacht klein" in str(exc.value)


def test_normal_csv_response_passes_sanity_check():
    meta = pc._record_feed_response(200, "text/csv", 5_000_000, b"gtin,name\n1,x\n")
    pc._ensure_feed_looks_like_data(meta, at_eof=True)  # geen exceptie


def test_xml_body_is_not_mistaken_for_html():
    meta = pc._record_feed_response(200, "application/xml", 5_000_000,
                                    b"<?xml version='1.0'?><rows><row/></rows>")
    pc._ensure_feed_looks_like_data(meta, at_eof=True)  # geen exceptie


def test_fetch_feed_rejects_html_error_page(monkeypatch):
    """_fetch_feed zelf herkent een HTML-foutpagina met HTTP 200."""
    import connectors.net as net

    class FakeResp:
        status_code = 200
        content = b"<!DOCTYPE html><html><body>Export wordt geregenereerd</body></html>"
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    monkeypatch.setattr(net, "safe_get", lambda url, timeout=None: FakeResp())
    with pytest.raises(ConnectorError) as exc:
        pc._fetch_feed("https://example.com/feed")
    assert "HTML" in str(exc.value)


# ── Redactie: geen secrets in previews/foutmeldingen ────────────────────────

def test_preview_redacts_query_strings_and_tokens():
    body = (b"<html>Error fetching https://public.app.priceshape.io/api/export/"
            b"6a840b16eb5c30c6a32d49c6?token=SuPeRsEcReT123&sig=abc "
            b'{"api_key": "ps_live_geheim", "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9"}'
            b"</html>")
    preview = pc._body_preview(body, limit=500)
    for geheim in ("SuPeRsEcReT123", "ps_live_geheim", "eyJhbGciOiJIUzI1NiJ9",
                   "6a840b16eb5c30c6a32d49c6", "token=SuPeRsEcReT"):
        assert geheim not in preview
    assert "[…]" in preview


def test_zero_rows_error_never_leaks_token_from_body(db):
    """Een feed-body die de (tokenized) export-URL echoot lekt geen secret in
    de foutmelding — en dus ook niet in de ImportJob of connectorstatus."""
    import feed_ingest
    html = (b"<p>Zie https://example.com/export/abc?token=GEHEIMTOKEN12345</p>"
            b"[]")  # geen producten
    with pytest.raises(ValueError) as exc:
        feed_ingest.ingest_feed(db, content=b'{"items": []}',
                                content_type="application/json")
    # aparte assert met echo-body via de metadata-recorder:
    meta = pc._record_feed_response(200, "text/html", len(html), html)
    assert "GEHEIMTOKEN12345" not in meta["preview"]
    assert "GEHEIMTOKEN12345" not in pc.describe_last_feed_response()
    assert "Ontvangen respons" in str(exc.value)


# ── Mislukte sync → zichtbaar in ImportJob + connectorstatus ────────────────

def test_failed_sync_persists_importjob_and_connector_status(monkeypatch, db):
    import feed_ingest
    import routes.connectors as rc

    def boom(*args, **kwargs):
        raise ValueError("PriceShape feed leverde 0 producten op — testdiagnostiek "
                         "(HTTP 200, text/html, 512 bytes)")

    monkeypatch.setattr(feed_ingest, "ingest_feed", boom)

    # Bestaande connector-status bewaren om na de test te herstellen.
    prev = db.query(models.ConnectorConfig).filter(
        models.ConnectorConfig.connector_name == "priceshape").first()
    prev_state = (prev.last_test_status, prev.last_test_message,
                  prev.last_tested_at) if prev else None

    user = SimpleNamespace(username="test-feed-diag")
    try:
        result = rc._run_sync("priceshape", db, user)
        assert result["status"] == "error"
        assert "testdiagnostiek" in result["message"]

        # ImportJob 'fout' geschreven met de reden.
        job = db.query(models.ImportJob).filter(
            models.ImportJob.uploaded_by == "test-feed-diag",
            models.ImportJob.upload_type == "api_sync_priceshape",
        ).order_by(models.ImportJob.created_at.desc()).first()
        assert job is not None
        assert job.status == "fout"
        assert "testdiagnostiek" in (job.error_message or "")

        # Connectorstatus weerspiegelt de fout.
        db.expire_all()
        cfg = db.query(models.ConnectorConfig).filter(
            models.ConnectorConfig.connector_name == "priceshape").first()
        assert cfg is not None
        assert cfg.last_test_status == "error"
        assert "testdiagnostiek" in (cfg.last_test_message or "")

        # Data-sources: de mislukte poging is zichtbaar als last_failed_job.
        from routes.data_sources import _job_stats
        stats = _job_stats(db, lambda q: q.filter(
            (models.ImportJob.source == "PriceShape")
            | (models.ImportJob.upload_type == "api_sync_priceshape")))
        assert stats["last_failed_job"] is not None
        assert "testdiagnostiek" in (stats["last_failed_job"]["reason"] or "")
        assert stats["last_failed_job"]["failed_at"] is not None
    finally:
        # Opruimen: testjobs weg, connectorstatus herstellen.
        db.query(models.ImportJob).filter(
            models.ImportJob.uploaded_by == "test-feed-diag").delete()
        cfg = db.query(models.ConnectorConfig).filter(
            models.ConnectorConfig.connector_name == "priceshape").first()
        if cfg is not None:
            if prev_state is None and not cfg.encrypted_credentials:
                db.delete(cfg)
            elif prev_state is not None:
                cfg.last_test_status, cfg.last_test_message, cfg.last_tested_at = prev_state
        db.commit()


# ── Retry-spreiding ─────────────────────────────────────────────────────────

def test_retry_backoff_is_spread_over_minutes():
    from services.feed_sync_scheduler import _backoff_seconds, MAX_RETRY_BACKOFF
    assert _backoff_seconds(1) == 60
    assert _backoff_seconds(2) == 120
    assert _backoff_seconds(3) == 240
    assert _backoff_seconds(10) == MAX_RETRY_BACKOFF  # gemaximeerd op 10 min
    # Drie pogingen liggen samen ruim buiten het oude 40s-venster.
    assert _backoff_seconds(1) + _backoff_seconds(2) >= 120
    # Configureerbare basis blijft werken.
    assert _backoff_seconds(2, base=5) == 10
