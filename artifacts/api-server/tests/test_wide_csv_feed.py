"""
Tests voor het BREDE PriceShape CSV-exportformaat (vendor_N-kolommen).

De standaard export-feed levert één product per rij, zonder gtin (itemGroupId
is de sleutel) en concurrenten in kolomgroepen `vendor_1 domain`, `vendor_1
price`, `vendor_1 stockStatus`, enz. — met decimale komma's.
"""
import feed_ingest as fi


WIDE_ROWS = [
    {
        "itemgroupid": "224692",
        "name": "BIC Gel-Ocity Quick Dry turkoois",
        "priceinclvat": "2,5",
        "shippingprice": "5,95",
        "costpriceexclvat": "0,94",
        "ppc_producttype": "office supplies > write > pens > ballpoint pens",
        "priceposition": "3",
        "vendor_1 domain": "prooffice.nl",
        "vendor_1 price": "2,42",
        "vendor_1 pricewithshipping": "10,83",
        "vendor_1 stockstatus": "InStock",
        "vendor_1 producturl": "https://example.com/redirect/1",
        "vendor_1 shippingcost": "8,41",
        "vendor_2 domain": "shopxpress.nl",
        "vendor_2 price": "2,49",
        "vendor_2 stockstatus": "OutOfStock",
        "vendor_2 producturl": "",
        "vendor_3 domain": "",
        "vendor_3 price": "",
    },
]


def test_wide_csv_detected_and_normalized():
    catalog, comp = fi._normalize_flat(WIDE_ROWS)
    assert len(catalog) == 1
    p = catalog[0]
    assert p["sku_id"] == "224692"
    assert p["ean"] is None  # geen gtin in de feed → geen verzonnen EAN
    assert p["product_name"] == "BIC Gel-Ocity Quick Dry turkoois"
    assert p["brand"] == "BIC"
    assert p["current_price"] == 2.5
    assert p["cost_price"] == 0.94
    assert p["category"] == "Office Supplies"
    assert p["subcategory"] == "Ballpoint Pens"
    # Niet-gemapte basisvelden verliesvrij in raw
    assert p["raw_attributes"]["shippingprice"] == "5,95"
    assert p["raw_attributes"]["priceposition"] == "3"

    assert len(comp) == 2  # vendor_3 is leeg en wordt overgeslagen
    a, b = comp
    assert a["competitor_name"] == "prooffice.nl"
    assert a["price"] == 2.42
    assert a["in_stock"] is True
    assert a["url"] == "https://example.com/redirect/1"
    assert a["raw_attributes"]["pricewithshipping"] == "10,83"
    assert a["raw_attributes"]["shippingcost"] == "8,41"
    assert b["competitor_name"] == "shopxpress.nl"
    assert b["in_stock"] is False
    assert b["url"] is None


def test_wide_csv_gtin_preferred_when_present():
    rows = [dict(WIDE_ROWS[0], gtin="8712345678901")]
    catalog, _ = fi._normalize_flat(rows)
    assert catalog[0]["sku_id"] == "8712345678901"
    assert catalog[0]["ean"] == "8712345678901"


def test_wide_csv_oversized_title_recoverable():
    rows = [dict(WIDE_ROWS[0], name="X" * 600)]
    catalog, _ = fi._normalize_flat(rows)
    assert catalog[0]["product_name"] == "X" * 500
    assert catalog[0]["raw_attributes"]["_productTitle_full"] == "X" * 600


def test_wide_csv_duplicate_rows_and_domains_deduplicated():
    """Dubbele productrijen of herhaalde vendor-domeinen leveren geen dubbele
    dagobservaties op (eerste voorkomen wint)."""
    row = dict(WIDE_ROWS[0])
    # Zelfde domein nogmaals in dezelfde rij, met andere prijs.
    row["vendor_3 domain"] = "ProOffice.nl"
    row["vendor_3 price"] = "9,99"
    rows = [row, dict(WIDE_ROWS[0])]  # + volledige duplicaatrij
    catalog, comp = fi._normalize_flat(rows)
    assert len(catalog) == 1
    keys = [(c["sku_id"], c["competitor_name"].lower()) for c in comp]
    assert len(keys) == len(set(keys)) == 2
    first = next(c for c in comp if c["competitor_name"] == "prooffice.nl")
    assert first["price"] == 2.42  # eerste voorkomen wint


def test_wide_csv_oversized_domain_keeps_original_casing():
    rows = [dict(WIDE_ROWS[0], **{"vendor_1 domain": "D" * 300 + ".nl"})]
    _, comp = fi._normalize_flat(rows)
    c = next(x for x in comp if x["competitor_name"].startswith("d"))
    assert c["competitor_name"] == ("d" * 300 + ".nl")[:255]
    assert c["raw_attributes"]["_domain_full"] == "D" * 300 + ".nl"


def test_flat_format_still_works():
    """Het oude platte formaat (één concurrent per rij) blijft functioneren."""
    rows = [{
        "gtin": "871", "producttitle": "Test", "priceinclvat": "9,99",
        "domain": "comp.nl", "price": "8,5",
    }]
    catalog, comp = fi._normalize_flat(rows)
    assert catalog[0]["sku_id"] == "871"
    assert comp[0]["competitor_name"] == "comp.nl"
    assert comp[0]["price"] == 8.5
