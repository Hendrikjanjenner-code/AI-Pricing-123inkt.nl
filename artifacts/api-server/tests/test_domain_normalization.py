"""
Domeinnormalisatie en sync-reconciliatie voor concurrenten (taak: varianten
als https://www.example.nl / WWW.example.nl / example.nl zijn één concurrent).

Dekt:
- de centrale normalisatiehelper;
- feed-ingest: varianten → één canoniek domein, alias herleidbaar,
  reconciliatie-samenvatting per sync;
- persistentie: sync → discovery → goedkeuren → nieuwe sync met andere
  schrijfwijze → géén duplicaat-kandidaat, goedkeuring intact;
- de eenmalige merge van bestaande varianten (niet-destructief).
"""
import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import models
from main import app
from database import SessionLocal
from services.domain_normalize import (
    normalize_domain, merge_competitor_domain_variants,
    _MARKER_ENTITY, _MARKER_ACTION,
)

PFX = "dntest"
DOM = f"{PFX}-dup.nl"
SKU1 = f"{PFX}-sku-1"
SKU2 = f"{PFX}-sku-2"


# ── 1. Normalisatiehelper ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("https://www.Example.nl/", "example.nl"),
    ("http://example.nl", "example.nl"),
    ("WWW.EXAMPLE.NL", "example.nl"),
    ("example.nl/", "example.nl"),
    ("example.nl/shop/product?x=1", "example.nl"),
    ("  example.nl  ", "example.nl"),
    ("example.nl.", "example.nl"),
    ("Bol.com", "bol.com"),
    ("", ""),
    (None, ""),
])
def test_normalize_domain_varianten(raw, expected):
    assert normalize_domain(raw) == expected


def test_normalize_domain_verliest_identiteit_nooit():
    # Niet-domeinachtige naam: alleen trimmen/kleinschrijven.
    assert normalize_domain("Mijn Winkel") == "mijn winkel"
    # Degenerate input levert nooit een lege identiteit op.
    assert normalize_domain("www.") != ""
    assert normalize_domain("https://") != ""


# ── 2. Feed-ingest + reconciliatie + discovery-persistentie ────────────────

def _feed_content(domain_variant_1: str, domain_variant_2: str) -> bytes:
    """Minimale JSON-feed: twee producten, zelfde concurrent in twee
    schrijfwijzen (op verschillende SKU's zodat beide de parser bereiken)."""
    return json.dumps([
        {
            "gtin": SKU1, "productTitle": "Dntest Product Een",
            "priceInclVat": "10.0", "costPriceExclVat": "6.0",
            "vendors": [{"domain": domain_variant_1, "price": "9.50",
                         "productUrl": f"https://{DOM}/p1"}],
        },
        {
            "gtin": SKU2, "productTitle": "Dntest Product Twee",
            "priceInclVat": "20.0", "costPriceExclVat": "12.0",
            "vendors": [{"domain": domain_variant_2, "price": "19.50"}],
        },
    ]).encode()


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login",
                       json={"username": "dev_admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def shop():
    db = SessionLocal()
    # Residu van eerdere (afgebroken) runs opruimen zodat matched/new-tellers
    # deterministisch zijn.
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.competitor_name.like(f"{PFX}%")
    ).delete(synchronize_session=False)
    db.query(models.CompetitorDiscoveryQueue).filter(
        models.CompetitorDiscoveryQueue.domain.like(f"{PFX}%")
    ).delete(synchronize_session=False)
    for c in db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name.like(f"{PFX}%")).all():
        db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.competitor_id == c.competitor_id
        ).delete(synchronize_session=False)
        db.delete(c)
    db.commit()
    # Herbruik een eventueel residu van een eerdere (afgebroken) run.
    s = db.query(models.DimShop).filter_by(shop_code=f"{PFX}-shop").first()
    if s is None:
        s = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(s)
        db.commit()
    sid = s.id
    try:
        yield sid
    finally:
        db.rollback()
        from sqlalchemy import text
        for stmt in [
            "DELETE FROM fact_competitor_offer_daily WHERE competitor_id IN "
            "(SELECT competitor_id FROM dim_competitor WHERE competitor_name LIKE :pfx)",
            "DELETE FROM fact_competitor_price_daily WHERE shop_id = :sid",
            "DELETE FROM fact_price_daily WHERE shop_id = :sid",
            "DELETE FROM competitor_discovery_queue WHERE shop_id = :sid",
            "DELETE FROM competitor_discovery_run WHERE shop_id = :sid",
            "DELETE FROM competitor_profiles WHERE shop_id = :sid",
            "DELETE FROM pim_attribute_value WHERE sku_id IN "
            "(SELECT sku_id FROM dim_product WHERE shop_id = :sid)",
            "DELETE FROM dim_product WHERE shop_id = :sid",
            "DELETE FROM cost_usage_records WHERE shop_id = :sid",
        ]:
            try:
                db.execute(text(stmt), {"sid": sid, "pfx": f"{PFX}%"})
                db.commit()
            except Exception:
                db.rollback()
        db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name.like(f"{PFX}%")).delete(
            synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == sid).delete()
        db.commit()
        db.close()


def test_sync_discovery_goedkeuring_geen_duplicaat(client, admin_headers, shop):
    import feed_ingest
    from engine.competitor_discovery import run_discovery

    db = SessionLocal()
    try:
        # Eerste sync: twee schrijfwijzen van hetzelfde domein.
        res = feed_ingest.ingest_feed(
            db, content=_feed_content(f"https://www.{DOM}/", DOM.upper()),
            shop_id=shop)

        # Eén canoniek domein in de factrijen; alias herleidbaar per rij.
        rows = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == shop).all()
        assert {r.competitor_name for r in rows} == {DOM}
        aliased = [r for r in rows if (r.raw_attributes or {}).get("_domain_alias")]
        assert aliased, "oorspronkelijke schrijfwijze moet als alias bewaard blijven"

        # Reconciliatie-samenvatting van deze sync.
        rec = res["competitor_reconciliation"]
        assert rec["feed_unique"] == 1
        assert rec["new"] == 1 and rec["matched"] == 0
        assert rec["rows_written"] == 2
        assert rec["duplicates_prevented"] == 1
        assert any("Concurrent-reconciliatie" in w for w in res["warnings"])

        # Register: canoniek domein met aliassen en last_seen_date.
        comp = db.query(models.DimCompetitor).filter_by(
            competitor_name=DOM).one()
        assert comp.last_seen_date == date.today()
        assert any(a.lower().startswith(("https://www.", DOM[:4].upper()[:4].lower()))
                   or a for a in (comp.aliases or [])), comp.aliases

        # Discovery: precies één kandidaat voor het canonieke domein.
        run_discovery(db, min_confidence=0.0, shop_id=shop)
        items = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.shop_id == shop).all()
        assert [i.domain for i in items] == [DOM]

        # Goedkeuren via de API.
        item_id = items[0].id
        r = client.post(f"/api/competition/discovery/{item_id}/approve",
                        params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200, r.text

        # Goedkeuring staat óók op de canonieke master (taak #288).
        db.expire_all()
        comp = db.query(models.DimCompetitor).filter_by(
            competitor_name=DOM).one()
        assert comp.approval_status == "APPROVED"
        assert comp.approved_by == "dev_admin"
        assert comp.approved_at is not None

        # Gesimuleerde herstart (taak #288): sessie sluiten en een nieuwe
        # app-lifespan starten vóór de tweede sync — de goedkeuring moet
        # louter uit de database komen, niet uit proces-/sessiestate.
        db.close()
        restart_client = TestClient(app)
        restart_client.__enter__()
        try:
            db = SessionLocal()
            comp = db.query(models.DimCompetitor).filter_by(
                competitor_name=DOM).one()
            assert comp.approval_status == "APPROVED", \
                "goedkeuring op de master moet een herstart overleven"

            # Tweede sync met wéér een andere schrijfwijze + nieuwe discovery-run.
            res2 = feed_ingest.ingest_feed(
                db, content=_feed_content(f"WWW.{DOM}", f"http://{DOM}/x"),
                shop_id=shop)
            assert res2["competitor_reconciliation"]["matched"] == 1
            assert res2["competitor_reconciliation"]["new"] == 0
            run_discovery(db, min_confidence=0.0, shop_id=shop)

            db.expire_all()
            items = db.query(models.CompetitorDiscoveryQueue).filter(
                models.CompetitorDiscoveryQueue.shop_id == shop).all()
            assert len(items) == 1, "variant mag nooit een duplicaat-kandidaat opleveren"
            assert items[0].status == "APPROVED", "goedkeuring moet intact blijven"

            # Masterstatus na herstart + tweede sync: nog steeds APPROVED —
            # feed-upsert mag goedkeuringsvelden nooit overschrijven.
            db.expire_all()
            comp = db.query(models.DimCompetitor).filter_by(
                competitor_name=DOM).one()
            assert comp.approval_status == "APPROVED"
            assert comp.approved_by == "dev_admin"
        finally:
            try:
                restart_client.__exit__(None, None, None)
            except Exception:
                pass
    finally:
        db.close()


def test_blokkeren_en_reconciliatietrechter(client, admin_headers, shop):
    """Taak #288: blokkeren sluit een concurrent uit van lijsten/rankings en
    de reconciliatietrechter toont de tellers shop-gescoped."""
    from services.competitor_master import blocked_competitor_names
    db = SessionLocal()
    try:
        item = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.shop_id == shop,
            models.CompetitorDiscoveryQueue.domain == DOM).one()

        # Trechter vóór blokkade: canoniek=1, goedgekeurd=1.
        r = client.get("/api/competition/reconciliation",
                       params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200, r.text
        steps = {s["key"]: s["count"] for s in r.json()["steps"]}
        assert steps["canonical"] == 1
        assert steps["approved"] == 1
        assert steps["feed_unique"] >= steps["canonical"]
        assert r.json()["blocked_count"] == 0

        # CIS-snapshot vóór de blokkade: DOM krijgt een score-rij.
        from engine.competitor_influence import run_cis_engine
        run_cis_engine(db, sku_ids=[SKU1])
        db.commit()
        assert db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU1,
            models.CompetitorInfluenceScore.competitor_name == DOM
        ).count() > 0

        # Blokkeren via de API.
        r = client.post(f"/api/competition/discovery/{item.id}/block",
                        params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        comp = db.query(models.DimCompetitor).filter_by(
            competitor_name=DOM).one()
        assert comp.blocked is True and comp.blocked_by == "dev_admin"
        assert DOM in blocked_competitor_names(db)
        assert db.get(models.CompetitorDiscoveryQueue, item.id).status == "BLOCKED"

        # Geblokkeerd: buiten de goedgekeurd-teller, wel zichtbaar als blocked.
        r = client.get("/api/competition/reconciliation",
                       params={"shop_id": shop}, headers=admin_headers)
        steps = {s["key"]: s["count"] for s in r.json()["steps"]}
        assert steps["approved"] == 0
        assert r.json()["blocked_count"] == 1

        # Concurrenten-lijst sluit geblokkeerde namen uit.
        r = client.get("/api/competition/competitors",
                       params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200
        assert DOM not in [i["competitor_name"] for i in r.json()["items"]]

        # Historische leesroutes tonen geblokkeerde namen evenmin.
        r = client.get("/api/competition/rankings/history",
                       params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200
        assert DOM not in r.json().get("history", {})

        # CIS/legacy-concurrentie: het vóór de blokkade berekende snapshot
        # mag de geblokkeerde concurrent niet meer tonen of laten meewegen
        # in de referentieprijs — en een herberekening evenmin.
        r = client.get(f"/api/concurrentie/sku/{SKU1}", headers=admin_headers)
        assert r.status_code == 200, r.text
        namen = [c["concurrent"] for c in r.json().get("concurrenten", [])]
        assert DOM not in namen, "geblokkeerde concurrent zichtbaar in CIS-snapshot"
        run_cis_engine(db, sku_ids=[SKU1])
        db.commit()
        rows = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU1,
            models.CompetitorInfluenceScore.competitor_name == DOM).count()
        assert rows == 0, "herberekening schreef rijen voor geblokkeerde concurrent"

        # Deblokkeren herstelt niets destructiefs: kandidaat terug naar
        # PROPOSED, masterblokkade weg (eerdere goedkeuring blijft bewaard).
        r = client.post(f"/api/competition/discovery/{item.id}/unblock",
                        params={"shop_id": shop}, headers=admin_headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        comp = db.query(models.DimCompetitor).filter_by(
            competitor_name=DOM).one()
        assert comp.blocked is False
        assert comp.approval_status == "APPROVED"
    finally:
        # CIS-rijen van de test-SKU opruimen (geen shop-FK, dus geen cascade).
        db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU1).delete()
        db.commit()
        db.close()


def test_auto_approve_synct_master_zonder_herstart(shop):
    """Taak #288: een automatische goedkeuring (boven de drempel) moet de
    canonieke master direct bijwerken — niet pas na een herstart-backfill."""
    import feed_ingest
    from engine.competitor_discovery import run_discovery
    from services import competition_settings as cs

    dom2 = f"{PFX}-auto.nl"
    db = SessionLocal()
    try:
        # Feed met een nieuwe concurrent (twee schrijfwijzen).
        feed_ingest.ingest_feed(
            db, content=json.dumps([{
                "gtin": SKU1, "productTitle": "Dntest Product Een",
                "priceInclVat": "10.0", "costPriceExclVat": "6.0",
                "vendors": [{"domain": f"https://www.{dom2}/", "price": "9.50"}],
            }]).encode(), shop_id=shop)

        # Auto-approve alles voor deze testshop.
        cs.upsert_settings(db, shop, {"auto_approve_threshold": 0.0}, "test")
        run_discovery(db, min_confidence=0.0, shop_id=shop)

        db.expire_all()
        item = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.shop_id == shop,
            models.CompetitorDiscoveryQueue.domain == dom2).one()
        assert item.status == "APPROVED"
        assert item.approved_by == "auto-approve"

        # Master direct synchroon, zonder herstart/backfill.
        comp = db.query(models.DimCompetitor).filter_by(
            competitor_name=dom2).one()
        assert comp.approval_status == "APPROVED"
        assert comp.approved_by == "auto-approve"
        assert comp.approved_at is not None
    finally:
        # Settings-rij opruimen, anders faalt de shop-teardown op de FK.
        db.query(models.CompetitionSetting).filter(
            models.CompetitionSetting.shop_id == shop).delete()
        db.commit()
        db.close()


def test_recent_niet_gezien_is_shop_gescoped(shop):
    """Een waarneming in shop A mag de markering van shop B niet beïnvloeden."""
    from datetime import timedelta
    from routes.competition import _seen_info_bulk
    db = SessionLocal()
    other = models.DimShop(shop_code=f"{PFX}-shop2", name=f"{PFX} Shop 2",
                           active=True)
    db.add(other)
    db.commit()
    dom2 = f"{PFX}-seen.nl"
    today = date.today()
    try:
        db.add_all([
            # Shop B (test-shop): concurrent 5 dagen niet gezien, feed zelf
            # wél vers (andere concurrent vandaag gezien).
            models.FactCompetitorPriceDaily(
                date=today - timedelta(days=5), sku_id=SKU1,
                competitor_name=dom2, price=1.0, source="priceshape",
                shop_id=shop),
            models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU1, competitor_name=f"{PFX}-other.nl",
                price=1.0, source="priceshape", shop_id=shop),
            # Shop A: dezelfde concurrent vandaag gezien.
            models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU1, competitor_name=dom2, price=1.0,
                source="priceshape", shop_id=other.id),
        ])
        db.commit()
        info_b = _seen_info_bulk(db, shop, [dom2])[dom2]
        assert info_b["recently_unseen"] is True
        info_a = _seen_info_bulk(db, other.id, [dom2])[dom2]
        assert info_a["recently_unseen"] is False
    finally:
        db.rollback()
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id.in_([shop, other.id]),
            models.FactCompetitorPriceDaily.competitor_name.like(f"{PFX}%"),
        ).delete(synchronize_session=False)
        db.commit()
        db.query(models.DimShop).filter(models.DimShop.id == other.id).delete()
        db.commit()
        db.close()


def test_upload_endpoint_normaliseert_en_bewaart_alias(client, admin_headers, shop):
    """Directe CSV-upload: variant-schrijfwijze wordt canoniek opgeslagen én
    blijft herleidbaar als alias in het concurrentenregister."""
    db = SessionLocal()
    try:
        if not db.query(models.DimProduct).filter_by(sku_id=SKU1).first():
            db.add(models.DimProduct(sku_id=SKU1, product_name="Dntest P1",
                                     shop_id=shop))
            db.commit()
        csv = (f"sku_id,date,competitor_name,competitor_price_inc_vat\n"
               f"{SKU1},{date.today().isoformat()},HTTPS://WWW.{DOM}/,9.95\n"
               ).encode()
        resp = client.post("/api/uploads/competitor-prices",
                           files={"file": ("comp.csv", csv, "text/csv")},
                           headers=admin_headers)
        assert resp.status_code == 200, resp.text
        rows = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == SKU1,
            models.FactCompetitorPriceDaily.competitor_name.like(f"%{DOM}%"),
        ).all()
        assert rows and all(r.competitor_name == DOM for r in rows)
        reg = db.query(models.DimCompetitor).filter_by(
            competitor_name=DOM).one()
        assert f"HTTPS://WWW.{DOM}/" in (reg.aliases or [])
        assert reg.last_seen_date is not None
    finally:
        db.rollback()
        db.close()


def test_priceshape_persist_normaliseert_en_bewaart_alias(shop):
    """persist_competitor_rows (upload/REST-pad): canonieke naam + alias."""
    from routes.priceshape import persist_competitor_rows
    db = SessionLocal()
    dom = f"{PFX}-rest.nl"
    try:
        if not db.query(models.DimProduct).filter_by(sku_id=SKU1).first():
            db.add(models.DimProduct(sku_id=SKU1, product_name="Dntest P1",
                                     shop_id=shop))
            db.commit()
        persist_competitor_rows(
            db, [{"sku": SKU1, "competitor_name": f"https://WWW.{dom}/x",
                  "competitor_price": "12.34",
                  "timestamp": date.today().isoformat()}],
            mode="append", username="dev_admin", filename="test.csv")
        db.commit()
        row = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.competitor_name == dom).first()
        assert row is not None
        reg = db.query(models.DimCompetitor).filter_by(
            competitor_name=dom).one()
        assert f"https://WWW.{dom}/x" in (reg.aliases or [])
    finally:
        db.rollback()
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.competitor_name == dom).delete(
            synchronize_session=False)
        db.commit()
        db.close()


def test_opgeslagen_variant_uitsluiting_blijft_werken(shop):
    """Een eerder opgeslagen uitsluiting als 'https://www.x.nl' moet ook de
    genormaliseerde invoer 'x.nl' blijven uitsluiten — op de vergelijking,
    bij het uitlezen én in het PriceShape-persistpad."""
    import services.import_settings as imps
    from routes.priceshape import persist_competitor_rows
    dom = f"{PFX}-excl.nl"
    # 1. Defensieve vergelijking: beide zijden genormaliseerd.
    settings = {"disabled_competitors": [f"https://WWW.{dom}/"]}
    assert imps.competitor_disabled(settings, dom) is True
    assert imps.competitor_disabled({"disabled_competitors": [dom]},
                                    f"HTTPS://www.{dom}") is True
    db = SessionLocal()
    try:
        # 2. Opslaan + uitlezen canoniseert.
        imps.save_settings(db, {}, [f"https://WWW.{dom}/"], "test")
        stored = imps.get_settings(db)
        assert dom in stored["disabled_competitors"]
        # 3. PriceShape-persist: variant-uitsluiting blokkeert de rij echt.
        if not db.query(models.DimProduct).filter_by(sku_id=SKU1).first():
            db.add(models.DimProduct(sku_id=SKU1, product_name="Dntest P1",
                                     shop_id=shop))
            db.commit()
        result = persist_competitor_rows(
            db, [{"sku": SKU1, "competitor_name": f"www.{dom}",
                  "competitor_price": "9.99",
                  "timestamp": date.today().isoformat()}],
            mode="append", username="dev_admin", filename="excl.csv")
        db.commit()
        assert result.get("skipped_by_settings", 0) >= 1
        assert db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.competitor_name == dom
        ).count() == 0
    finally:
        db.rollback()
        # Uitsluiting weer opruimen zodat andere tests er geen last van hebben.
        try:
            imps.save_settings(db, {}, [], "test")
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_rest_variant_lookup_resolvet_canoniek(client, admin_headers, shop):
    """GET met variant-schrijfwijze in het pad resolvet dezelfde concurrent
    als de canonieke naam (geen 404 door normalisatieverschil)."""
    dom = f"{PFX}-restlookup.nl"
    db = SessionLocal()
    try:
        db.add(models.CompetitorScoreResult(
            shop_id=shop, competitor_name=dom, run_date=date.today()))
        db.add(models.CompetitorProfile(shop_id=shop, competitor_name=dom,
                                        assortment_size=3))
        db.commit()
        # (een volledige URL met '/' kan nooit als één padsegment binnenkomen)
        for variant in (dom, f"WWW.{dom}", f"www.{dom}"):
            r = client.get(f"/api/competition/competitor-scores/{variant}",
                           params={"shop_id": shop}, headers=admin_headers)
            assert r.status_code == 200, (variant, r.text)
            r2 = client.get(f"/api/competition/competitors/{variant}",
                            params={"shop_id": shop}, headers=admin_headers)
            assert r2.status_code == 200, (variant, r2.text)
    finally:
        db.rollback()
        db.query(models.CompetitorScoreResult).filter(
            models.CompetitorScoreResult.competitor_name == dom).delete(
            synchronize_session=False)
        db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name == dom).delete(
            synchronize_session=False)
        db.commit()
        db.close()


# ── 3. Eenmalige merge van bestaande varianten ──────────────────────────────

def test_merge_bestaande_varianten_niet_destructief(shop):
    db = SessionLocal()
    mdom = f"{PFX}-merge.nl"
    today = date.today()
    try:
        # Bestaande situatie: twee variant-identiteiten in register, queue en facts.
        db.add_all([
            models.DimCompetitor(competitor_name=mdom),
            models.DimCompetitor(competitor_name=f"https://www.{mdom}"),
            models.CompetitorDiscoveryQueue(
                domain=f"www.{mdom}", competitor_name=f"www.{mdom}",
                status="APPROVED", approved_by="analist",
                approved_at=datetime.utcnow(), shop_id=shop, confidence=0.9),
            models.CompetitorDiscoveryQueue(
                domain=mdom, competitor_name=mdom,
                status="PROPOSED", shop_id=shop, confidence=0.5),
            # Botsende factrijen: zelfde sleutel, één canoniek en één variant.
            models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU1, competitor_name=mdom, price=5.0,
                source="priceshape", shop_id=shop),
            models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU1, competitor_name=f"WWW.{mdom}",
                price=5.5, source="priceshape", shop_id=shop),
            # Niet-botsende variantrij: moet hernoemd worden, niet verwijderd.
            models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU2, competitor_name=f"https://{mdom}/",
                price=6.0, source="priceshape", shop_id=shop),
            # UNIQUE-constraint-tabel (shop_id+competitor_name): variant +
            # canoniek → merge mag nooit een IntegrityError geven.
            models.CompetitorProfile(
                shop_id=shop, competitor_name=mdom, assortment_size=10),
            models.CompetitorProfile(
                shop_id=shop, competitor_name=f"WWW.{mdom}", assortment_size=5),
        ])
        db.commit()

        # FK-verwijzingen naar de VERLIEZER-registerrij: die moeten naar de
        # winnaar herwezen worden vóór de delete (anders FK-fout of wezen).
        loser = db.query(models.DimCompetitor).filter_by(
            competitor_name=f"https://www.{mdom}").one()
        winner_id = db.query(models.DimCompetitor).filter_by(
            competitor_name=mdom).one().competitor_id
        db.add_all([
            models.ProductMatch(own_sku_id=SKU1, competitor_id=loser.competitor_id,
                                match_type="EAN", active=True),
            models.FactMonitoringAlert(date=today, own_sku_id=SKU1,
                                       competitor_id=loser.competitor_id,
                                       alert_type="PRICE_DROP"),
        ])
        db.commit()
        match_id = db.query(models.ProductMatch).filter_by(
            own_sku_id=SKU1, competitor_id=loser.competitor_id).one().match_id

        # Marker van de startup-run verwijderen zodat de merge echt draait.
        db.query(models.AuditLog).filter(
            models.AuditLog.entity_type == _MARKER_ENTITY,
            models.AuditLog.action == _MARKER_ACTION).delete()
        db.commit()
        report = merge_competitor_domain_variants(db)
        assert report, "merge moet iets samengevoegd rapporteren"

        # Register: één canonieke rij met alias.
        comps = db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name.like(f"%{mdom}%")).all()
        assert [c.competitor_name for c in comps] == [mdom]
        assert f"https://www.{mdom}" in (comps[0].aliases or [])

        # Queue: één rij, goedkeuring behouden (nooit gedowngraded).
        q = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.shop_id == shop,
            models.CompetitorDiscoveryQueue.domain == mdom).all()
        assert len(q) == 1
        assert q[0].status == "APPROVED" and q[0].approved_by == "analist"
        assert not db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain == f"www.{mdom}").count()

        # Facts: variant hernoemd; botsing niet dubbel, historie niet gewist.
        facts = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == shop,
            models.FactCompetitorPriceDaily.competitor_name.like(f"%{mdom}%"),
        ).all()
        assert {f.competitor_name for f in facts} == {mdom}
        assert {f.sku_id for f in facts} == {SKU1, SKU2}
        assert len([f for f in facts if f.sku_id == SKU1]) == 1

        # FK-verwijzingen herwezen naar de winnaar (goedkeuring/match intact).
        m = db.query(models.ProductMatch).filter_by(match_id=match_id).one()
        assert m.competitor_id == winner_id
        alert = db.query(models.FactMonitoringAlert).filter_by(
            own_sku_id=SKU1, alert_type="PRICE_DROP").one()
        assert alert.competitor_id == winner_id

        # Unieke-constraint-tabel: één profiel over, canonieke rij wint.
        profs = db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.shop_id == shop,
            models.CompetitorProfile.competitor_name.like(f"%{mdom}%")).all()
        assert len(profs) == 1
        assert profs[0].competitor_name == mdom
        assert profs[0].assortment_size == 10

        # Idempotent: tweede aanroep doet niets meer (marker staat).
        assert merge_competitor_domain_variants(db) == {}
    finally:
        db.rollback()
        db.query(models.ProductMatch).filter(
            models.ProductMatch.own_sku_id == SKU1).delete(
            synchronize_session=False)
        db.query(models.FactMonitoringAlert).filter(
            models.FactMonitoringAlert.own_sku_id == SKU1).delete(
            synchronize_session=False)
        db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name.like(f"%{mdom}%")
        ).delete(synchronize_session=False)
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.competitor_name.like(f"%{mdom}%")
        ).delete(synchronize_session=False)
        db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain.like(f"%{mdom}%")
        ).delete(synchronize_session=False)
        db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name.like(f"%{mdom}%")
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
