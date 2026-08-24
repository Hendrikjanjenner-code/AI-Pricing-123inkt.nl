"""
Tests voor taak #266: prijsuitbijters onderzoeken en verklaarbaar maken.

Dekking:
- Engine: calculate_reference_price levert per uitgesloten prijs een detail
  (afwijking, mediaan, ratio, vermoedelijke oorzaak); classify_outlier_cause
  herkent verpakkingsveelvouden, decimaal-fouten en extreme afwijkingen.
- score_competition markeert uitgesloten fact-rijen met een expliciete reden
  (nooit verwijderen, alleen markeren); een rerun reset eerdere markeringen.
- Configureerbare uitbijterdrempel via import-instellingen.
- /api/data-quality/outliers: totalen per reden, vermoedelijke oorzaken,
  meest geraakte concurrenten/categorieën en voorbeelden (drill-down).
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine import competition_engine as ce

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"OUTREC{uuid.uuid4().hex[:6]}"
SKU = f"{PFX}-sku"
CAT = f"{PFX}-cat"
COMP_OK = f"{PFX}-normaal.nl"
COMP_OUT = f"{PFX}-uitbijter.nl"
COMP_OOS = f"{PFX}-voorraad.nl"
COMP_SLOW = f"{PFX}-traag.nl"
COMP_REJ = f"{PFX}-afgekeurd.nl"


# ── Unit: engine ─────────────────────────────────────────────────────────────

def test_classify_outlier_cause_patterns():
    assert ce.classify_outlier_cause(40.0, 10.0) == ce.CAUSE_PACK_MULTIPLE     # 4×
    assert ce.classify_outlier_cause(2.5, 10.0) == ce.CAUSE_PACK_FRACTION      # 1/4
    assert ce.classify_outlier_cause(1000.0, 10.0) == ce.CAUSE_DECIMAL_SHIFT   # 100×
    assert ce.classify_outlier_cause(0.10, 10.0) == ce.CAUSE_DECIMAL_SHIFT     # 0,01×
    assert ce.classify_outlier_cause(12.1, 10.0) == ce.CAUSE_VAT               # +21%
    assert ce.classify_outlier_cause(34.5, 10.0) == ce.CAUSE_EXTREME           # 3,45× geen patroon
    assert ce.classify_outlier_cause(14.0, 10.0) == ce.CAUSE_ABOVE_THRESHOLD   # +40%, geen patroon


def test_calculate_reference_price_returns_details():
    prices = [10.0, 10.5, 9.8, 40.2]  # laatste ≈ 4× mediaan → uitbijter
    ref, used, excluded, reasons, details, normalized = ce.calculate_reference_price(prices)
    assert normalized == []  # pakgrootte onbekend → geen normalisatie
    assert used == 3 and excluded == 1
    assert reasons == {ce.EXCLUSION_OUTLIER: 1}
    assert len(details) == 1
    det = details[0]
    assert det["index"] == 3
    assert det["price"] == 40.2
    assert det["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE
    assert det["deviation_pct"] > 30
    assert det["threshold_pct"] == 30.0


def test_calculate_reference_price_threshold_configurable():
    prices = [10.0, 10.5, 9.8, 14.0]  # +40% t.o.v. mediaan
    _, used_default, excl_default, _, _, _ = ce.calculate_reference_price(prices)
    assert excl_default == 1
    # Ruimere drempel (60%): geen uitsluiting meer → aantal daalt aantoonbaar.
    _, used_wide, excl_wide, _, details, _ = ce.calculate_reference_price(prices, outlier_threshold=0.60)
    assert excl_wide == 0 and used_wide == 4 and details == []


# ── Unit: prijs-per-eenheid-normalisatie (taak #269) ─────────────────────────

def test_detect_pack_factor_high_confidence_only():
    assert ce.detect_pack_factor(40.0, 10.0) == (4, "multiple")     # exact 4×
    assert ce.detect_pack_factor(40.2, 10.0) == (4, "multiple")     # binnen ±2%
    assert ce.detect_pack_factor(2.5, 10.0) == (4, "fraction")      # exact 1/4
    assert ce.detect_pack_factor(43.0, 10.0) is None                # 4,3× → twijfelgeval
    assert ce.detect_pack_factor(14.0, 10.0) is None                # geen n-voud
    assert ce.detect_pack_factor(40.0, 0) is None
    assert ce.detect_pack_factor(None, 10.0) is None


def test_normalization_includes_pack_multiple_when_pack_size_known():
    prices = [10.0, 10.5, 9.8, 40.2]  # laatste ≈ 4× mediaan
    ref, used, excluded, reasons, details, normalized = ce.calculate_reference_price(
        prices, pack_size_known=True)
    assert excluded == 0 and used == 4 and details == [] and reasons == {}
    assert len(normalized) == 1
    n = normalized[0]
    assert n["index"] == 3 and n["price"] == 40.2
    assert n["pack_factor"] == 4 and n["pack_kind"] == "multiple"
    assert n["normalized_price"] == pytest.approx(10.05)
    assert n["label"] == "genormaliseerd (4\u00d7)"
    # Genormaliseerde prijs telt mee in de referentieprijs (mediaan van 4).
    assert 9.8 <= ref <= 10.5


def test_normalization_fraction_and_doubt_cases():
    # 1/4 van de mediaan, vrijwel exact → genormaliseerd meetellen.
    prices = [10.0, 10.5, 9.8, 2.5]
    ref, used, excluded, _, details, normalized = ce.calculate_reference_price(
        prices, pack_size_known=True)
    assert excluded == 0 and used == 4
    assert normalized[0]["pack_kind"] == "fraction"
    assert normalized[0]["normalized_price"] == pytest.approx(10.0)
    assert normalized[0]["label"] == "genormaliseerd (1/4\u00d7)"

    # Twijfelgeval (4,3× mediaan): buiten de strakke tolerantie → blijft
    # gemarkeerd uitgesloten, ook met bekende pakgrootte.
    prices = [10.0, 10.5, 9.8, 43.0]
    _, used_d, excl_d, _, details_d, normalized_d = ce.calculate_reference_price(
        prices, pack_size_known=True)
    assert excl_d == 1 and used_d == 3 and normalized_d == []
    assert details_d[0]["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE


def test_normalization_independent_of_wide_threshold():
    """Normalisatie staat lós van de uitbijterdrempel: ook met een zeer ruime
    drempel (5.0) telt een n-voud/1-op-n per eenheid genormaliseerd mee, nooit
    rauw — anders vervuilt de totaalprijs van een groot pak de referentieprijs."""
    # n× (4× de mediaan): met drempel 5.0 zou 40.0 rauw includeren zonder fix.
    prices = [10.0, 10.0, 10.0, 40.0]
    ref, used, excluded, _, details, normalized = ce.calculate_reference_price(
        prices, outlier_threshold=5.0, pack_size_known=True)
    assert excluded == 0 and used == 4 and details == []
    assert len(normalized) == 1
    assert normalized[0]["normalized_price"] == pytest.approx(10.0)
    assert normalized[0]["label"] == "genormaliseerd (4\u00d7)"
    assert ref == pytest.approx(10.0)  # niet vervuild door 40.0

    # 1/n (1/4 van de mediaan): idem bij ruime drempel.
    prices = [10.0, 10.0, 10.0, 2.5]
    ref_f, used_f, excl_f, _, details_f, normalized_f = ce.calculate_reference_price(
        prices, outlier_threshold=5.0, pack_size_known=True)
    assert excl_f == 0 and used_f == 4 and details_f == []
    assert normalized_f[0]["normalized_price"] == pytest.approx(10.0)
    assert normalized_f[0]["label"] == "genormaliseerd (1/4\u00d7)"
    assert ref_f == pytest.approx(10.0)

    # Zonder bekende pakgrootte: ruime drempel includeert rauw (bestaand gedrag).
    _, used_raw, excl_raw, _, _, normalized_raw = ce.calculate_reference_price(
        [10.0, 10.0, 10.0, 40.0], outlier_threshold=5.0, pack_size_known=False)
    assert excl_raw == 0 and used_raw == 4 and normalized_raw == []


def test_normalization_disabled_without_pack_size():
    prices = [10.0, 10.5, 9.8, 40.2]
    _, used, excluded, _, details, normalized = ce.calculate_reference_price(
        prices, pack_size_known=False)
    assert excluded == 1 and used == 3 and normalized == []
    assert details[0]["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE


# ── Integratie: markering + endpoint ────────────────────────────────────────

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
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def seed(client):
    """Eigen testshop met vandaag 4 concurrentprijzen op één SKU:
    normaal (10), uitbijter (40 ≈ 4× → pack-veelvoud), out-of-stock, trage levering."""
    db = SessionLocal()
    today = date.today()
    shop_id = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Outlier Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id
        db.add(models.DimProduct(
            sku_id=SKU, product_name=f"Outlier {SKU}", category=CAT,
            current_price=10.0, cost_price=6.0, stock_quantity=5, shop_id=shop_id,
        ))
        rows = [
            dict(competitor_name=COMP_OK, price=10.0, in_stock=True, delivery_days=2.0),
            dict(competitor_name=f"{PFX}-normaal2.nl", price=10.4, in_stock=True, delivery_days=2.0),
            dict(competitor_name=f"{PFX}-normaal3.nl", price=9.8, in_stock=True, delivery_days=2.0),
            dict(competitor_name=COMP_OUT, price=40.2, in_stock=True, delivery_days=2.0),
            dict(competitor_name=COMP_OOS, price=9.9, in_stock=False, delivery_days=2.0),
            dict(competitor_name=COMP_SLOW, price=10.1, in_stock=True, delivery_days=99.0),
            dict(competitor_name=COMP_REJ, price=10.2, in_stock=True, delivery_days=2.0),
        ]
        for r in rows:
            db.add(models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU, shop_id=shop_id, source="priceshape", **r))
        # Door analist afgekeurde match: moet als BAD_MATCH gemarkeerd worden.
        db.add(models.AiMatchResult(
            shop_id=shop_id, own_sku_id=SKU, competitor_name=COMP_REJ,
            match_type="Exact", confidence=0.9, status="REJECTED"))
        db.commit()

        import feed_ingest
        feed_ingest.score_competition(db, shop_id=shop_id)
        yield shop_id
    finally:
        db.rollback()
        try:
            if shop_id:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.SkuCompetitionScore).filter(
                    models.SkuCompetitionScore.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.FactCompetitorPriceDaily).filter(
                    models.FactCompetitorPriceDaily.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimProduct).filter(
                    models.DimProduct.shop_id == shop_id).delete(synchronize_session=False)
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def _fact(db, shop_id, competitor):
    return db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.shop_id == shop_id,
        models.FactCompetitorPriceDaily.competitor_name == competitor,
    ).first()


def test_score_competition_marks_fact_rows(seed):
    db = SessionLocal()
    try:
        ok = _fact(db, seed, COMP_OK)
        assert ok.excluded_reason is None and ok.exclusion_detail is None

        out = _fact(db, seed, COMP_OUT)
        assert out.excluded_reason == ce.EXCLUSION_OUTLIER
        det = out.exclusion_detail
        assert det["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE
        assert det["deviation_pct"] > 30 and det["median"] > 0

        oos = _fact(db, seed, COMP_OOS)
        assert oos.excluded_reason == ce.EXCLUSION_OUT_OF_STOCK
        # Data blijft staan: rij bestaat nog en prijs onaangetast.
        assert float(oos.price) == 9.9

        slow = _fact(db, seed, COMP_SLOW)
        assert slow.excluded_reason == ce.EXCLUSION_BAD_DELIVERY
        assert slow.exclusion_detail["delivery_days"] == 99.0

        rej = _fact(db, seed, COMP_REJ)
        assert rej.excluded_reason == ce.EXCLUSION_BAD_MATCH
        assert float(rej.price) == 10.2  # data blijft staan
    finally:
        db.close()


def test_rerun_resets_stale_marks(seed):
    """Een rerun mag oude markeringen niet laten staan: markeer handmatig een
    inclusieve rij en controleer dat score_competition die reset."""
    import feed_ingest
    db = SessionLocal()
    try:
        ok = _fact(db, seed, COMP_OK)
        ok.excluded_reason = ce.EXCLUSION_OUTLIER
        ok.exclusion_detail = {"suspected_cause": "X"}
        db.commit()
        feed_ingest.score_competition(db, shop_id=seed)
        db.expire_all()
        ok = _fact(db, seed, COMP_OK)
        assert ok.excluded_reason is None and ok.exclusion_detail is None
        out = _fact(db, seed, COMP_OUT)
        assert out.excluded_reason == ce.EXCLUSION_OUTLIER
    finally:
        db.close()


def test_outlier_reconciliation_endpoint(client, admin_headers, seed):
    r = client.get("/api/data-quality/outliers", params={"shop_id": seed}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_date"] == date.today().isoformat()
    assert body["by_reason"][ce.EXCLUSION_OUTLIER] == 1
    assert body["by_reason"][ce.EXCLUSION_OUT_OF_STOCK] == 1
    assert body["by_reason"][ce.EXCLUSION_BAD_DELIVERY] == 1
    assert body["by_reason"][ce.EXCLUSION_BAD_MATCH] == 1
    assert body["total_excluded"] == 4
    assert body["total_observations"] == 7
    assert body["by_suspected_cause"] == {ce.CAUSE_PACK_MULTIPLE: 1}
    assert body["outlier_threshold"] == pytest.approx(0.30)

    comps = {c["competitor_name"] for c in body["top_competitors"]}
    assert {COMP_OUT, COMP_OOS, COMP_SLOW, COMP_REJ} <= comps
    cats = {c["category"]: c["excluded"] for c in body["top_categories"]}
    assert cats.get(CAT) == 4

    ex = body["examples"][ce.EXCLUSION_OUTLIER]
    assert len(ex) == 1
    assert ex[0]["sku_id"] == SKU and ex[0]["competitor_name"] == COMP_OUT
    assert ex[0]["detail"]["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE
    assert body["examples"][ce.EXCLUSION_BAD_MATCH][0]["competitor_name"] == COMP_REJ


def test_outlier_reconciliation_empty_shop(client, admin_headers):
    r = client.get("/api/data-quality/outliers", params={"shop_id": 999999}, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["run_date"] is None and body["by_reason"] == {} and body["total_excluded"] == 0


# ── Integratie: normalisatie (taak #269) ────────────────────────────────────

@pytest.fixture(scope="module")
def norm_seed(client):
    """Eigen shop met een SKU mét bekende pakgrootte (sheets_per_pack) en een
    concurrentprijs die vrijwel exact 4× de mediaan is → genormaliseerd."""
    db = SessionLocal()
    today = date.today()
    sku = f"{PFX}-norm-sku"
    shop_id = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-normshop", name=f"{PFX} Norm Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Norm {sku}", category=CAT,
            current_price=10.0, cost_price=6.0, stock_quantity=5,
            sheets_per_pack=100, shop_id=shop_id,
        ))
        rows = [
            (f"{PFX}-n1.nl", 10.0), (f"{PFX}-n2.nl", 10.4), (f"{PFX}-n3.nl", 9.8),
            (f"{PFX}-npack.nl", 41.6),   # = 4× mediaan (10.4), binnen ±2% → normaliseren
            (f"{PFX}-ndoubt.nl", 45.0),  # 4,33× → twijfelgeval, blijft uitgesloten
        ]
        for name, price in rows:
            db.add(models.FactCompetitorPriceDaily(
                date=today, sku_id=sku, shop_id=shop_id, source="priceshape",
                competitor_name=name, price=price, in_stock=True, delivery_days=2.0))
        db.commit()

        import feed_ingest
        feed_ingest.score_competition(db, shop_id=shop_id)
        yield {"shop_id": shop_id, "sku": sku}
    finally:
        db.rollback()
        try:
            if shop_id:
                db.query(models.SkuCompetitionScore).filter(
                    models.SkuCompetitionScore.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.FactCompetitorPriceDaily).filter(
                    models.FactCompetitorPriceDaily.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimProduct).filter(
                    models.DimProduct.shop_id == shop_id).delete(synchronize_session=False)
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


@pytest.mark.parametrize("bad_pack_size", [None, 0, -5])
def test_invalid_pack_size_disables_normalization(client, bad_pack_size):
    """NULL/0/negatieve sheets_per_pack telt niet als bekende pakgrootte:
    een 4×-prijs blijft dan gemarkeerd uitgesloten (geen normalisatie)."""
    import feed_ingest
    db = SessionLocal()
    today = date.today()
    sku = f"{PFX}-bad{bad_pack_size}-sku"
    shop_id = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-bad{bad_pack_size}",
                              name=f"{PFX} BadPack {bad_pack_size}", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"BadPack {sku}", category=CAT,
            current_price=10.0, cost_price=6.0, stock_quantity=5,
            sheets_per_pack=bad_pack_size, shop_id=shop_id,
        ))
        for name, price in [(f"{PFX}-b1.nl", 10.0), (f"{PFX}-b2.nl", 10.4),
                            (f"{PFX}-b3.nl", 9.8), (f"{PFX}-bpack.nl", 41.6)]:
            db.add(models.FactCompetitorPriceDaily(
                date=today, sku_id=sku, shop_id=shop_id, source="priceshape",
                competitor_name=name, price=price, in_stock=True, delivery_days=2.0))
        db.commit()
        feed_ingest.score_competition(db, shop_id=shop_id)
        db.expire_all()
        pack = _fact(db, shop_id, f"{PFX}-bpack.nl")
        assert pack.excluded_reason == ce.EXCLUSION_OUTLIER
        assert pack.exclusion_detail["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE
        assert not pack.exclusion_detail.get("normalized")
    finally:
        db.rollback()
        try:
            if shop_id:
                db.query(models.SkuCompetitionScore).filter(
                    models.SkuCompetitionScore.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.FactCompetitorPriceDaily).filter(
                    models.FactCompetitorPriceDaily.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimProduct).filter(
                    models.DimProduct.shop_id == shop_id).delete(synchronize_session=False)
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_score_competition_normalizes_pack_multiple(norm_seed):
    db = SessionLocal()
    try:
        shop_id = norm_seed["shop_id"]
        pack = _fact(db, shop_id, f"{PFX}-npack.nl")
        # Genormaliseerd: geen uitsluitingsreden, wél zichtbare markering.
        assert pack.excluded_reason is None
        det = pack.exclusion_detail
        assert det["normalized"] is True
        assert det["pack_factor"] == 4
        assert det["label"] == "genormaliseerd (4\u00d7)"
        assert det["normalized_price"] == pytest.approx(10.4)
        assert float(pack.price) == 41.6  # originele prijs blijft staan

        doubt = _fact(db, shop_id, f"{PFX}-ndoubt.nl")
        assert doubt.excluded_reason == ce.EXCLUSION_OUTLIER
        assert doubt.exclusion_detail["suspected_cause"] == ce.CAUSE_PACK_MULTIPLE

        score = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.shop_id == shop_id,
            models.SkuCompetitionScore.sku_id == norm_seed["sku"]).first()
        # Genormaliseerde prijs telt mee: 4 gebruikt, 1 uitgesloten.
        assert score.competitors_used == 4
        assert score.competitors_excluded == 1
        assert 9.8 <= float(score.reference_price) <= 10.4
    finally:
        db.close()


def test_normalization_rerun_resets_marks(norm_seed):
    """Een rerun reset ook normalisatie-markeringen (excluded_reason NULL,
    detail niet-NULL) en zet ze daarna correct opnieuw."""
    import feed_ingest
    db = SessionLocal()
    try:
        shop_id = norm_seed["shop_id"]
        feed_ingest.score_competition(db, shop_id=shop_id)
        db.expire_all()
        pack = _fact(db, shop_id, f"{PFX}-npack.nl")
        assert pack.excluded_reason is None
        assert pack.exclusion_detail["normalized"] is True
        # Geen dubbele of verouderde markeringen op normale rijen.
        ok = _fact(db, shop_id, f"{PFX}-n1.nl")
        assert ok.excluded_reason is None and ok.exclusion_detail is None
    finally:
        db.close()


def test_outliers_endpoint_reports_normalized(client, admin_headers, norm_seed):
    shop_id = norm_seed["shop_id"]
    r = client.get("/api/data-quality/outliers", params={"shop_id": shop_id},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Aandeel PACK_SIZE_* daalt aantoonbaar: alleen het twijfelgeval blijft.
    assert body["by_suspected_cause"].get(ce.CAUSE_PACK_MULTIPLE) == 1
    assert body["by_reason"][ce.EXCLUSION_OUTLIER] == 1
    norm = body["normalized"]
    assert norm["count"] == 1
    assert norm["by_factor"] == {"genormaliseerd (4\u00d7)": 1}
    ex = norm["examples"][0]
    assert ex["competitor_name"] == f"{PFX}-npack.nl"
    assert ex["detail"]["label"] == "genormaliseerd (4\u00d7)"
    assert ex["detail"]["normalized_price"] == pytest.approx(10.4)


# ── Shop-scope (authz): geen IDOR op reconciliatiedata ──────────────────────

@pytest.fixture()
def scoped_viewer(client, admin_headers, seed):
    """Viewer die uitsluitend tot de test-shop beperkt is; ruimt op."""
    username = f"{PFX.lower()}_viewer_{uuid.uuid4().hex[:6]}"
    password = f"Pw!{uuid.uuid4().hex[:12]}"
    r = client.post("/api/users", headers=admin_headers, json={
        "username": username, "email": f"{username}@test.local",
        "full_name": "Outlier Scoped Viewer", "password": password, "role": "viewer",
    })
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    sr = client.put(f"/api/authz/users/{uid}", headers=admin_headers, json={
        "scopes": [{"scope_type": "shop", "scope_value": str(seed)}],
    })
    assert sr.status_code == 200, sr.text
    from authz_helpers import grant_legacy_views
    grant_legacy_views(username)
    lr = client.post("/api/auth/login", json={"username": username, "password": password})
    assert lr.status_code == 200, lr.text
    yield {"Authorization": f"Bearer {lr.json()['token']}"}
    db = SessionLocal()
    try:
        db.query(models.UserScope).filter(models.UserScope.user_id == uid).delete(
            synchronize_session=False)
        db.query(models.User).filter(models.User.id == uid).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_outliers_foreign_shop_forbidden(client, scoped_viewer):
    r = client.get("/api/data-quality/outliers", params={"shop_id": 1}, headers=scoped_viewer)
    assert r.status_code == 403


def test_outliers_implicit_scope_limits_to_allowed_shops(client, scoped_viewer, seed):
    """Zonder expliciete shop ziet een gescopede gebruiker alleen zijn eigen
    shop-data — geen cross-shop aggregatie."""
    r = client.get("/api/data-quality/outliers", headers=scoped_viewer)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_date"] == date.today().isoformat()
    # Exact de totalen van de eigen test-shop (zie endpoint-test hierboven).
    assert body["total_excluded"] == 4
    assert body["total_observations"] == 7
    comps = {c["competitor_name"] for c in body["top_competitors"]}
    assert comps <= {COMP_OUT, COMP_OOS, COMP_SLOW, COMP_REJ}


# ── Import-instellingen: drempel ─────────────────────────────────────────────

def test_import_settings_outlier_threshold_roundtrip(client, admin_headers):
    get0 = client.get("/api/uploads/priceshape/import-settings", headers=admin_headers)
    assert get0.status_code == 200
    before = get0.json()
    orig = before.get("outlier_threshold")
    assert orig is not None
    try:
        put = client.put("/api/uploads/priceshape/import-settings", headers=admin_headers, json={
            "components": {}, "disabled_competitors": before["disabled_competitors"],
            "outlier_threshold": 0.55,
        })
        assert put.status_code == 200, put.text
        assert put.json()["outlier_threshold"] == pytest.approx(0.55)

        bad = client.put("/api/uploads/priceshape/import-settings", headers=admin_headers, json={
            "components": {}, "disabled_competitors": before["disabled_competitors"],
            "outlier_threshold": 99,
        })
        assert bad.status_code == 400

        # null → terug naar standaard
        reset = client.put("/api/uploads/priceshape/import-settings", headers=admin_headers, json={
            "components": {}, "disabled_competitors": before["disabled_competitors"],
            "outlier_threshold": None,
        })
        assert reset.status_code == 200
        assert reset.json()["outlier_threshold"] == pytest.approx(0.30)
    finally:
        client.put("/api/uploads/priceshape/import-settings", headers=admin_headers, json={
            "components": {}, "disabled_competitors": before["disabled_competitors"],
            "outlier_threshold": orig if orig != 0.30 else None,
        })
