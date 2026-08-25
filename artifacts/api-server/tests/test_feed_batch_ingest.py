"""
Batchgewijze feed-ingest (taak 299): het schijf-spool/batchpad moet exact
dezelfde resultaten opleveren als het klassieke lijstpad — replace-snapshot,
dedupe, clamp-waarschuwingen en tellingen incluis — terwijl er nooit meer dan
één batch tegelijk in het geheugen staat (_CHUNK klein gemonkeypatcht).
"""
import os
import sys
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
import feed_ingest

PFX = f"T299-{uuid.uuid4().hex[:6]}"
COMP1 = f"{PFX.lower()}-comp1.nl"
COMP2 = f"{PFX.lower()}-comp2.nl"
LONG_CAT = "X" * 400  # dwingt een clamp-waarschuwing af (category, VARCHAR(255))


def _feed(prefix: str, n: int = 8) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "gtin": f"{prefix}-{i:03d}",
            "productTitle": f"Product {i}",
            "PPC_ProductType": LONG_CAT if i == 0 else "Inkt",
            "priceInclVat": f"{10 + i}.50",
            "costPriceExclVat": f"{5 + i}.00",
            "vendors": [
                {"domain": COMP1, "price": f"{9 + i}.99", "inStock": "true",
                 "deliveryDays": "2",
                 "scrapedAt": "2026-08-25T06:00:00"},
                {"domain": COMP2, "price": f"{11 + i}.25"},
                # duplicaat-domein binnen hetzelfde record → gededupet
                {"domain": COMP1, "price": "1.00"},
            ],
        })
    # duplicaat-gtin → eerste voorkomen wint
    rows.append(dict(rows[0], productTitle="DUPLICAAT"))
    return rows


@pytest.fixture()
def shops():
    db = SessionLocal()
    a = models.DimShop(shop_code=f"{PFX}-a", name=f"{PFX} A")
    b = models.DimShop(shop_code=f"{PFX}-b", name=f"{PFX} B")
    db.add_all([a, b])
    db.commit()
    yield db, a.id, b.id
    for model, col in [
        (models.FactCompetitorOfferDaily, models.FactCompetitorOfferDaily.own_sku_id),
        (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.sku_id),
        (models.FactPriceDaily, models.FactPriceDaily.sku_id),
        (models.DimProduct, models.DimProduct.sku_id),
    ]:
        db.query(model).filter(col.like(f"{PFX}%")).delete(synchronize_session=False)
    db.query(models.DimCompetitor).filter(
        models.DimCompetitor.competitor_name.in_([COMP1, COMP2])).delete(
        synchronize_session=False)
    for sid in (a.id, b.id):
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
    db.query(models.DimShop).filter(
        models.DimShop.shop_code.in_([f"{PFX}-a", f"{PFX}-b"])).delete(
        synchronize_session=False)
    db.commit()
    db.close()


def _spooled(feed):
    """Bootst het streaming pad na: normaliseer naar schijf-spools."""
    cat, comp = feed_ingest._RowSpool(), feed_ingest._RowSpool()
    feed_ingest._normalize_stream(iter(feed), cat, comp)
    return cat, comp


def test_batch_spool_path_equals_list_path(shops, monkeypatch):
    db, sid_a, sid_b = shops
    feed_a = _feed(f"{PFX}-A")
    feed_b = _feed(f"{PFX}-B")

    # Referentie: klassiek lijstpad, grote _CHUNK.
    monkeypatch.setattr(feed_ingest, "_read_feed",
                        lambda *a, **k: feed_ingest._normalize(iter(feed_a)))
    res_list = feed_ingest.ingest_feed(db, source="priceshape", shop_id=sid_a)

    # Batchpad: schijf-spools + _CHUNK=3 → meerdere batches per pass.
    monkeypatch.setattr(feed_ingest, "_CHUNK", 3)
    monkeypatch.setattr(feed_ingest, "_read_feed",
                        lambda *a, **k: _spooled(feed_b))
    res_spool = feed_ingest.ingest_feed(db, source="priceshape", shop_id=sid_b)

    # Identieke tellingen (dedupe gtin + domein, offers, eigen prijzen).
    for key in ("products_new", "products_updated", "products_total",
                "own_prices", "competitor_rows", "offer_rows",
                "skipped_by_settings"):
        assert res_spool[key] == res_list[key], key
    assert res_list["products_total"] == 8
    # 8 producten × 2 unieke domeinen + 2 extra van het duplicaat-gtin-record
    # (dedupe is per record; bestaande semantiek van het lijstpad).
    assert res_list["competitor_rows"] == 18
    assert res_list["offer_rows"] == 9  # COMP1-rijen met voorraaddata

    # Clamp-waarschuwingen: geaggregeerd (één per kolom), ook over batches.
    def _clamps(res):
        return sorted(w.split("Voorbeeld")[0] for w in res["warnings"]
                      if "afgekapt" in w)
    assert len(_clamps(res_spool)) == len(_clamps(res_list)) == 1
    assert "category" in _clamps(res_spool)[0]

    # Rijen in de DB identiek qua inhoud per winkel (behalve shop/sku-prefix).
    def _rows(sid, prefix):
        prods = db.query(models.DimProduct).filter(
            models.DimProduct.shop_id == sid).order_by(models.DimProduct.sku_id).all()
        comps = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == sid).order_by(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name).all()
        return ([(p.sku_id.replace(prefix, ""), p.product_name, p.brand,
                  float(p.current_price)) for p in prods],
                [(c.sku_id.replace(prefix, ""), c.competitor_name,
                  float(c.price), c.in_stock, c.observed_at) for c in comps])
    assert _rows(sid_a, f"{PFX}-A") == _rows(sid_b, f"{PFX}-B")

    # Datetime overleeft de spool-roundtrip (observed_at uit scrapedAt).
    row = db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.shop_id == sid_b,
        models.FactCompetitorPriceDaily.competitor_name == COMP1).first()
    assert isinstance(row.observed_at, datetime)


def _wide_csv(prefix: str, n: int = 8) -> str:
    """Breed PriceShape-exportformaat: vendor_N-kolommen, geen gtin — de
    standaard-feed. Inclusief duplicaatrij (eerste voorkomen wint)."""
    header = ("itemGroupId,name,PPC_ProductType,priceInclVat,costPriceExclVat,"
              "vendor_1 domain,vendor_1 price,vendor_1 stockStatus,"
              "vendor_2 domain,vendor_2 price")
    lines = [header]
    for i in range(n):
        cat = LONG_CAT if i == 0 else "Inkt"
        lines.append(f"{prefix}-{i:03d},Product {i},{cat},{10 + i}.50,{5 + i}.00,"
                     f"{COMP1},{9 + i}.99,true,{COMP2},{11 + i}.25")
    lines.append(lines[1].replace("Product 0", "DUPLICAAT"))  # dubbele sku
    return "\n".join(lines) + "\n"


def test_wide_csv_spool_path_equals_buffered_path(shops, monkeypatch, tmp_path):
    """Het CSV-vanaf-schijf-spoolpad (standaard-feedformaat) levert exact
    dezelfde DB-inhoud en tellingen als het gebufferde lijstpad, ook met
    kleine batches."""
    db, sid_a, sid_b = shops
    csv_a = _wide_csv(f"{PFX}-A")
    csv_b = _wide_csv(f"{PFX}-B")

    # Referentie: gebufferd pad (content= → _parse_content → lijsten).
    res_list = feed_ingest.ingest_feed(db, source="priceshape", shop_id=sid_a,
                                       content=csv_a.encode(), content_type="text/csv")

    # Spoolpad: CSV op schijf, rij-voor-rij → _RowSpool, _CHUNK=3.
    p = tmp_path / "feed.csv"
    p.write_text(csv_b, encoding="utf-8")
    monkeypatch.setattr(feed_ingest, "_CHUNK", 3)
    monkeypatch.setattr(feed_ingest, "_read_feed",
                        lambda *a, **k: feed_ingest._spool_csv_file(str(p)))
    res_spool = feed_ingest.ingest_feed(db, source="priceshape", shop_id=sid_b)

    for key in ("products_new", "products_total", "own_prices",
                "competitor_rows", "offer_rows"):
        assert res_spool[key] == res_list[key], key
    assert res_list["products_total"] == 8
    assert res_list["competitor_rows"] == 16  # feedbrede (sku, domein)-dedupe

    def _rows(sid, prefix):
        prods = db.query(models.DimProduct).filter(
            models.DimProduct.shop_id == sid).order_by(models.DimProduct.sku_id).all()
        comps = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == sid).order_by(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name).all()
        return ([(p.sku_id.replace(prefix, ""), p.product_name, p.category,
                  float(p.current_price)) for p in prods],
                [(c.sku_id.replace(prefix, ""), c.competitor_name,
                  float(c.price), c.in_stock) for c in comps])
    assert _rows(sid_a, f"{PFX}-A") == _rows(sid_b, f"{PFX}-B")


def test_late_legacy_encoding_yields_each_row_exactly_once(tmp_path):
    """Een cp1252-byte laat in een groot CSV-bestand mag nooit tot dubbele
    rijen leiden: de encoding wordt in een pre-pass gekozen vóór er ook maar
    één rij wordt ge-yield (geen tweede parse-pass na deels yielden)."""
    n = 2000
    lines = ["gtin,productTitle,priceInclVat,domain,price"]
    for i in range(n):
        # Ruim > tekstbuffer (8 KB) aan geldige UTF-8 vóór de kapotte byte.
        lines.append(f"G{i:05d},Product {i} {'x' * 40},9.99,comp.nl,8.88")
    body = "\n".join(lines).encode("utf-8")
    body += "\nGLAST,Caf\xe9 sp\xe9cial,1.00,comp.nl,0.99\n".encode("cp1252")
    p = tmp_path / "legacy.csv"
    p.write_bytes(body)

    rows = list(feed_ingest._iter_csv_rows(str(p)))
    assert len(rows) == n + 1  # elke bronrij precies één keer
    assert len({r["gtin"] for r in rows}) == n + 1
    assert rows[-1]["producttitle"] == "Café spécial"  # legacy-decodering klopt


def test_empty_spool_feed_triggers_guard_before_any_delete(shops, monkeypatch):
    """Lege feed via het spoolpad: zelfde last-known-good-guard als het
    lijstpad — er wordt vóór welke delete dan ook afgebroken."""
    db, sid_a, _ = shops
    today = date.today()
    sku = f"{PFX}-A-guard"
    db.add(models.DimProduct(sku_id=sku, product_name="Guard", shop_id=sid_a,
                             current_price=9.0, import_source="seed"))
    db.add(models.FactPriceDaily(date=today, sku_id=sku, price=9.0,
                                 shop_id=sid_a))
    db.commit()

    monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: _spooled([]))
    with pytest.raises(ValueError):
        feed_ingest.ingest_feed(db, source="priceshape", shop_id=sid_a)
    db.rollback()
    assert db.query(models.FactPriceDaily).filter(
        models.FactPriceDaily.sku_id == sku).count() == 1
