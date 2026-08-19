"""
Tests: concurrentie-instellingen worden echt per shop opgeslagen (taak):
- GET levert defaults als er nog niets is opgeslagen;
- PUT slaat op, persist over nieuwe sessies en blijft per shop gescheiden;
- validatie: gewichten moeten samen 100 zijn, drempels 0–1;
- RBAC: viewer mag lezen maar niet schrijven;
- engines lezen de per-shop drempels (discovery min_confidence/auto-approve,
  matching min_match_confidence).
"""
import os
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from services import competition_settings as cs

_SFX = _uuid.uuid4().hex[:6]

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
VIEWER_LOGIN = {"username": "dev_viewer", "password": "viewer123"}


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


def _headers(client, login):
    resp = client.post("/api/auth/login", json=login)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def admin_headers(client):
    return _headers(client, ADMIN_LOGIN)


@pytest.fixture(scope="module")
def viewer_headers(client, admin_headers):
    """Tijdelijke viewer-gebruiker (niet elke omgeving heeft dev_viewer geseed)."""
    import uuid
    username = f"csettings_viewer_{uuid.uuid4().hex[:8]}"
    password = f"Pw!{uuid.uuid4().hex[:12]}"
    r = client.post("/api/users", headers=admin_headers, json={
        "username": username, "email": f"{username}@test.local",
        "full_name": "CompSettings Viewer", "password": password, "role": "viewer",
    })
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["id"]
    lr = client.post("/api/auth/login", json={"username": username, "password": password})
    assert lr.status_code == 200, lr.text
    yield {"Authorization": f"Bearer {lr.json()['token']}"}
    client.delete(f"/api/users/{user_id}", headers=admin_headers)


@pytest.fixture(scope="module")
def test_shop(client):
    """Aparte shop zodat we per-shop scheiding kunnen testen zonder de
    default-shop-instellingen van andere tests te raken."""
    db = SessionLocal()
    shop = models.DimShop(shop_code=f"CSET-TEST-{_SFX}", name="CompSettings Testshop")
    db.add(shop)
    db.commit()
    sid = shop.id
    db.close()
    yield sid
    _teardown_shop(sid)


def _teardown_shop(sid: int) -> None:
    """Verwijder een testshop incl. afhankelijke rijen (cost-usage-middleware
    schrijft per request rijen met shop-FK; anders faalt de delete op FK)."""
    db = SessionLocal()
    try:
        db.query(models.CompetitionSetting).filter(
            models.CompetitionSetting.shop_id == sid).delete()
        db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.shop_id == sid).delete()
        db.query(models.CompetitorDiscoveryRun).filter(
            models.CompetitorDiscoveryRun.shop_id == sid).delete()
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == sid).delete()
        db.query(models.DimShop).filter(models.DimShop.id == sid).delete()
        db.commit()
    finally:
        db.close()


def test_get_returns_defaults(client, admin_headers, test_shop):
    r = client.get(f"/api/competition/settings?shop_id={test_shop}", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shop_id"] == test_shop
    assert body["settings"] == cs.DEFAULTS


def test_put_persists_and_is_shop_scoped(client, admin_headers, test_shop):
    payload = {
        "min_discovery_confidence": 0.75,
        "min_match_confidence": 0.65,
        "auto_approve_threshold": 0.95,
        "lookback_days": 21,
        "auto_discovery_enabled": True,
        "relevance_weights": {"pricing": 40, "assortment": 20, "traffic": 15,
                              "authority": 15, "coverage": 10},
    }
    r = client.put(f"/api/competition/settings?shop_id={test_shop}",
                   json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["min_discovery_confidence"] == 0.75

    # Persist over een nieuwe sessie (herstart-simulatie)
    db = SessionLocal()
    stored = cs.get_settings(db, test_shop)
    db.close()
    assert stored["min_discovery_confidence"] == 0.75
    assert stored["lookback_days"] == 21
    assert stored["auto_discovery_enabled"] is True
    assert stored["relevance_weights"]["pricing"] == 40

    # Andere shop (default) blijft op eigen/default waarden
    r2 = client.get("/api/competition/settings", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["shop_id"] != test_shop
    assert r2.json()["settings"]["min_discovery_confidence"] != 0.75 or \
        r2.json()["settings"]["lookback_days"] != 21


def test_partial_update_merges_over_existing(client, admin_headers, test_shop):
    r = client.put(f"/api/competition/settings?shop_id={test_shop}",
                   json={"lookback_days": 14}, headers=admin_headers)
    assert r.status_code == 200, r.text
    s = r.json()["settings"]
    assert s["lookback_days"] == 14
    assert s["min_discovery_confidence"] == 0.75  # eerdere waarde blijft


def test_validation_rejects_bad_input(client, admin_headers, test_shop):
    # Gewichten die niet op 100 uitkomen
    r = client.put(
        f"/api/competition/settings?shop_id={test_shop}",
        json={"relevance_weights": {"pricing": 50, "assortment": 20,
                                    "traffic": 15, "authority": 15, "coverage": 10}},
        headers=admin_headers)
    assert r.status_code == 422
    assert "100" in r.json()["detail"]
    # Drempel buiten 0–1
    r = client.put(f"/api/competition/settings?shop_id={test_shop}",
                   json={"min_match_confidence": 55}, headers=admin_headers)
    assert r.status_code == 422
    # lookback buiten bereik
    r = client.put(f"/api/competition/settings?shop_id={test_shop}",
                   json={"lookback_days": 3}, headers=admin_headers)
    assert r.status_code == 422


def test_unknown_shop_404(client, admin_headers):
    r = client.get("/api/competition/settings?shop_id=999999", headers=admin_headers)
    assert r.status_code == 404


def test_rbac_viewer_reads_but_cannot_write(client, viewer_headers, test_shop):
    r = client.get(f"/api/competition/settings?shop_id={test_shop}", headers=viewer_headers)
    assert r.status_code == 200
    r = client.put(f"/api/competition/settings?shop_id={test_shop}",
                   json={"lookback_days": 30}, headers=viewer_headers)
    assert r.status_code == 403


def test_discovery_engine_reads_settings(test_shop):
    """run_discovery zonder expliciete min_confidence gebruikt de shop-instelling."""
    from engine.competitor_discovery import run_discovery
    db = SessionLocal()
    try:
        cs.upsert_settings(db, test_shop, {"min_discovery_confidence": 0.99,
                                           "auto_approve_threshold": 1.0}, "test")
        result = run_discovery(db, shop_id=test_shop)
        run = db.query(models.CompetitorDiscoveryRun).filter(
            models.CompetitorDiscoveryRun.run_id == result["run_id"]).first()
        assert run is not None
        assert run.parameters["min_confidence"] == 0.99
        # Ruim de run + eventuele queue-items van deze run op
        db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.run_id == result["run_id"]).delete()
        db.query(models.CompetitorDiscoveryRun).filter(
            models.CompetitorDiscoveryRun.run_id == result["run_id"]).delete()
        db.commit()
    finally:
        db.close()


def test_settings_are_shop_isolated_in_engines():
    """Twee-shop regressie: hoge drempel in shop A raakt shop B niet.

    Shop A krijgt min_match_confidence 0.999 (blokkeert alles), shop B houdt
    de default 0.5. Beide shops hebben een identiek product + concurrentprijs
    (EAN-match → confidence 0.95): shop B krijgt wél een match, shop A niet.
    """
    from datetime import date
    from engine.ai_matching import run_matching_for_all

    db = SessionLocal()
    shop_a = models.DimShop(shop_code=f"CSET-ISO-A-{_SFX}", name="Iso Shop A")
    shop_b = models.DimShop(shop_code=f"CSET-ISO-B-{_SFX}", name="Iso Shop B")
    db.add_all([shop_a, shop_b])
    db.commit()
    sid_a, sid_b = shop_a.id, shop_b.id
    sku_a, sku_b = "CSET-ISO-A-SKU1", "CSET-ISO-B-SKU1"
    try:
        for sid, sku in ((sid_a, sku_a), (sid_b, sku_b)):
            db.add(models.DimProduct(
                sku_id=sku, product_name="Testproduct Iso", brand="IsoMerk",
                category="IsoTest", current_price=10.0,
                oem_code="8712345678906", shop_id=sid))
            db.add(models.FactCompetitorPriceDaily(
                sku_id=sku, competitor_name="iso-comp.nl", price=9.5,
                date=date.today(), shop_id=sid,
                raw_attributes={"ean": "8712345678906"}))
        db.commit()

        cs.upsert_settings(db, sid_a, {"min_match_confidence": 0.999}, "test")

        run_matching_for_all(db, shop_id=sid_a)
        run_matching_for_all(db, shop_id=sid_b)

        match_a = db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == sku_a).first()
        match_b = db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == sku_b).first()
        assert match_a is None, "drempel van shop A moet matches van shop A blokkeren"
        assert match_b is not None, "drempel van shop A mag shop B niet beïnvloeden"
        assert match_b.shop_id == sid_b, "opgeslagen match moet de eigen shop_id dragen"
    finally:
        db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id.in_([sku_a, sku_b])).delete(
            synchronize_session=False)
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id.in_([sku_a, sku_b])).delete(
            synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([sku_a, sku_b])).delete(
            synchronize_session=False)
        db.commit()
        db.close()
        for sid in (sid_a, sid_b):
            _teardown_shop(sid)


def test_discovery_routes_are_shop_scoped(client, admin_headers):
    """Queue-listing, discovery-log en approve/reject zien alleen items van de
    gekozen shop; muteren over de shop-grens heen geeft 404."""
    db = SessionLocal()
    shop_a = models.DimShop(shop_code=f"CSET-RQA-{_SFX}", name="Route Shop A")
    shop_b = models.DimShop(shop_code=f"CSET-RQB-{_SFX}", name="Route Shop B")
    db.add_all([shop_a, shop_b])
    db.commit()
    sid_a, sid_b = shop_a.id, shop_b.id
    item = models.CompetitorDiscoveryQueue(
        run_id=f"run-{_SFX}", domain=f"route-scoped-{_SFX}.nl",
        status="PENDING", confidence=0.7, shop_id=sid_b)
    db.add(item)
    db.commit()
    item_id = item.id
    try:
        r = client.get(f"/api/competition/discovery?shop_id={sid_a}",
                       headers=admin_headers)
        assert r.status_code == 200
        assert all(i["id"] != item_id for i in r.json()["items"]), \
            "queue-item van shop B mag niet zichtbaar zijn in shop A"
        r = client.get(f"/api/competition/discovery?shop_id={sid_b}",
                       headers=admin_headers)
        assert any(i["id"] == item_id for i in r.json()["items"])

        # Muteren vanuit shop A moet 404 geven; vanuit shop B slagen.
        r = client.post(f"/api/competition/discovery/{item_id}/approve?shop_id={sid_a}",
                        headers=admin_headers)
        assert r.status_code == 404
        r = client.post(f"/api/competition/discovery/{item_id}/approve?shop_id={sid_b}",
                        headers=admin_headers)
        assert r.status_code == 200

        # Discovery-log gescheiden per shop
        run = models.CompetitorDiscoveryRun(run_id=f"runlog-{_SFX}", shop_id=sid_b,
                                            status="completed")
        db.add(run)
        db.commit()
        r = client.get(f"/api/competition/discovery-log?shop_id={sid_a}",
                       headers=admin_headers)
        assert all(x["run_id"] != f"runlog-{_SFX}" for x in r.json()["items"])
        r = client.get(f"/api/competition/discovery-log?shop_id={sid_b}",
                       headers=admin_headers)
        assert any(x["run_id"] == f"runlog-{_SFX}" for x in r.json()["items"])
    finally:
        db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.id == item_id).delete()
        db.query(models.CompetitorDiscoveryRun).filter(
            models.CompetitorDiscoveryRun.run_id == f"runlog-{_SFX}").delete()
        db.commit()
        db.close()
        for sid in (sid_a, sid_b):
            _teardown_shop(sid)


def test_discovery_engine_is_shop_scoped():
    """Discovery voor shop A ziet alleen feed-data van shop A en schrijft
    queue-items met shop_id, zodat winkels elkaar niet beïnvloeden."""
    from datetime import date
    from engine.competitor_discovery import run_discovery

    db = SessionLocal()
    shop_a = models.DimShop(shop_code=f"CSET-DISC-A-{_SFX}", name="Disc Shop A")
    shop_b = models.DimShop(shop_code=f"CSET-DISC-B-{_SFX}", name="Disc Shop B")
    db.add_all([shop_a, shop_b])
    db.commit()
    sid_a, sid_b = shop_a.id, shop_b.id
    sku_a, sku_b = "CSET-DISC-A-SKU1", "CSET-DISC-B-SKU1"
    run_ids = []
    try:
        # Shop A: één SKU met concurrent "disc-only-b.nl" alléén bij shop B
        db.add(models.DimProduct(sku_id=sku_a, product_name="Disc A",
                                 category="DiscTest", current_price=10.0,
                                 shop_id=sid_a))
        db.add(models.DimProduct(sku_id=sku_b, product_name="Disc B",
                                 category="DiscTest", current_price=10.0,
                                 shop_id=sid_b))
        db.add(models.FactCompetitorPriceDaily(
            sku_id=sku_b, competitor_name="disc-only-b.nl", price=9.0,
            date=date.today(), shop_id=sid_b))
        db.commit()

        # Lage drempel zodat elke kandidaat doorkomt
        cs.upsert_settings(db, sid_a, {"min_discovery_confidence": 0.0,
                                       "auto_approve_threshold": 1.0}, "test")
        result_a = run_discovery(db, shop_id=sid_a)
        run_ids.append(result_a["run_id"])
        # Shop A heeft geen eigen feed-rijen → concurrent van shop B mag niet opduiken
        item = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain == "disc-only-b.nl",
            models.CompetitorDiscoveryQueue.shop_id == sid_a).first()
        assert item is None
        assert result_a["candidates_found"] == 0

        cs.upsert_settings(db, sid_b, {"min_discovery_confidence": 0.0,
                                       "auto_approve_threshold": 1.0}, "test")
        result_b = run_discovery(db, shop_id=sid_b)
        run_ids.append(result_b["run_id"])
        item_b = db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.domain == "disc-only-b.nl",
            models.CompetitorDiscoveryQueue.shop_id == sid_b).first()
        assert item_b is not None, "shop B moet zijn eigen concurrent wél vinden"
    finally:
        db.query(models.CompetitorDiscoveryQueue).filter(
            models.CompetitorDiscoveryQueue.run_id.in_(run_ids)).delete(
            synchronize_session=False)
        db.query(models.CompetitorDiscoveryRun).filter(
            models.CompetitorDiscoveryRun.run_id.in_(run_ids)).delete(
            synchronize_session=False)
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id.in_([sku_a, sku_b])).delete(
            synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([sku_a, sku_b])).delete(
            synchronize_session=False)
        db.commit()
        db.close()
        for sid in (sid_a, sid_b):
            _teardown_shop(sid)


def test_matching_engine_filters_below_threshold(test_shop, monkeypatch):
    """Matches onder min_match_confidence worden niet opgeslagen."""
    import engine.ai_matching as aim
    db = SessionLocal()
    try:
        # Drempel zeer hoog voor deze shop; engine leest hem via settings
        cs.upsert_settings(db, test_shop, {"min_match_confidence": 0.999}, "test")
        stored = cs.get_settings(db, test_shop)
        assert stored["min_match_confidence"] == 0.999
        # match_sku_to_competitor levert max 0.95 → alles onder drempel
        before = db.query(models.AiMatchResult).count()
        aim.run_matching_for_all(db, shop_id=test_shop)
        after = db.query(models.AiMatchResult).count()
        assert after == before  # niets nieuws opgeslagen onder de drempel
    finally:
        db.close()
