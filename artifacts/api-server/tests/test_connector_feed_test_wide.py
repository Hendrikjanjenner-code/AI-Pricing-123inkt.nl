"""
Verbindingstest van de PriceShape-feed moet het brede exportformaat
(vendor_N-kolommen) herkennen — het standaard exportformaat dat de ingest
zelf volledig ondersteunt (taak #310: bevestiging standaard-feed was
geblokkeerd na de database-reset).
"""
from unittest.mock import patch

from routes.connectors import _test_priceshape_feed


def _fake_sample(rows):
    """Patch de feed-streaming/parse-helpers zodat de test offline draait."""
    return patch.multiple(
        "connectors.priceshape_connector",
        _stream_feed_sample=lambda url: (b"x", "text/csv"),
        _detect_feed_format=lambda content, ct, declared: "csv",
        _parse_feed_sample=lambda content, ct, fmt: rows,
    )


CREDS = {"feed_url": "https://feeds.example.com/export.csv"}


def test_wide_rij_met_itemgroupid_slaagt():
    rows = [{
        "id": "123", "itemgroupid": "IG-1", "name": "Product",
        "priceinclvat": "9.99",
        "vendor_1 domain": "shop.example", "vendor_1 price": "8.99",
    }]
    with _fake_sample(rows):
        res = _test_priceshape_feed(CREDS)
    assert res["status"] == "ok", res


def test_wide_rij_met_gtin_slaagt():
    rows = [{
        "gtin": "8712345678901", "itemgroupid": "IG-1",
        "vendor_1 domain": "shop.example", "vendor_1 price": "8.99",
    }]
    with _fake_sample(rows):
        res = _test_priceshape_feed(CREDS)
    assert res["status"] == "ok", res


def test_wide_rij_zonder_identifier_faalt():
    rows = [{
        "name": "Product",
        "vendor_1 domain": "shop.example", "vendor_1 price": "8.99",
    }]
    with _fake_sample(rows):
        res = _test_priceshape_feed(CREDS)
    assert res["status"] == "error"
    assert "identifier" in res["message"]


def test_smalle_rij_zonder_prijs_faalt_nog_steeds():
    rows = [{"sku": "A1", "name": "Product"}]
    with _fake_sample(rows):
        res = _test_priceshape_feed(CREDS)
    assert res["status"] == "error"
    assert "concurrentprijs" in res["message"]
