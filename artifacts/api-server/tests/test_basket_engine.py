"""
Regressietests voor de basket-engine (§16) en de promotie-halo (§19).

Bewaakt met kleine synthetische basket-/orderdata dat de rekenlogica niet
stilletjes regresseert na modelwijzigingen:
- run_basket_engine: support/confidence/lift met vooraf bekende waarden,
  lift-richting (>1 vs <1), relatie-typeclassificatie (bundle / upsell /
  basket_filler), bundelmarge, idempotent herdraaien en signaalpublicatie
- get_frequently_bought_together / get_basket_association_dashboard
- analyze_promotion: halo_pct gebruikt de juiste gerelateerde SKU's via
  BasketAssociation (en blijft None zonder associaties)

Synthetische dataset (co_purchase_counts, totaal = 200):
  A→B: 50   → support 0.25, confidence 0.50, P(B)=0.25, lift 2.00  (bundle)
  A→C: 25   → support 0.125, confidence 0.25, P(C)=0.625, lift 0.40 (filler, C=€10)
  A→U: 25   → support 0.125, confidence 0.25, P(U)=0.125, lift 2.00 (upsell, U=€30)
  D→C: 100  → support 0.50, confidence 1.00, P(C)=0.625, lift 1.60  (filler)
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine.basket_engine import (
    run_basket_engine,
    get_basket_association_dashboard,
    get_frequently_bought_together,
)
from engine.promotion_engine import analyze_promotion, PROMOTION_DEFAULT_CONFIG

PFX = f"BKTEST{uuid.uuid4().hex[:6]}"
CAT = f"{PFX}-cat"

SKU_A = f"{PFX}-A"   # antecedent met 3 consequenten
SKU_B = f"{PFX}-B"   # sterke associatie met A → bundle (lift 2.0)
SKU_C = f"{PFX}-C"   # goedkoop (€10) → basket_filler
SKU_U = f"{PFX}-U"   # duur (€30) → upsell vanaf A (€20)
SKU_D = f"{PFX}-D"   # antecedent met confidence 1.0
SKU_PROMO = f"{PFX}-HALOPROMO"   # gepromote SKU voor halo-test
SKU_HALO = f"{PFX}-HALOREL"      # basket-gerelateerde SKU met bekende halo-uplift
SKU_NOASSOC = f"{PFX}-NOASSOC"   # gepromote SKU zonder associaties → halo None

RUN_DATE = date(2026, 8, 18)


@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(scope="module")
def shop(db):
    shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Basket Shop", active=True)
    db.add(shop)
    db.commit()
    sid = shop.id
    yield shop
    # Teardown — alle testdata van deze shop opruimen (incl. FK-afhankelijkheden)
    for model, col in [
        (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
        (models.BasketAssociation, models.BasketAssociation.shop_id),
        (models.FactBasketAffinity, models.FactBasketAffinity.shop_id),
        (models.FactPromotionEffect, models.FactPromotionEffect.shop_id),
        (models.FactSalesDaily, models.FactSalesDaily.shop_id),
        (models.CostUsageRecord, models.CostUsageRecord.shop_id),
    ]:
        db.query(model).filter(col == sid).delete(synchronize_session=False)
    db.query(models.Promotion).filter(models.Promotion.sku_id.like(f"{PFX}%")).delete(
        synchronize_session=False)
    db.query(models.DimProduct).filter(models.DimProduct.shop_id == sid).delete(
        synchronize_session=False)
    db.query(models.DimShop).filter(models.DimShop.id == sid).delete(synchronize_session=False)
    db.commit()


def _add_product(db, sid, sku, name, price, cost=None):
    db.add(models.DimProduct(
        sku_id=sku, product_name=name, category=CAT, shop_id=sid,
        current_price=price, cost_price=cost if cost is not None else price * 0.6,
        stock_quantity=100, is_active=True))


def _add_affinity(db, sid, a, b, count, score):
    db.add(models.FactBasketAffinity(
        shop_id=sid, sku_id_a=a, sku_id_b=b,
        co_purchase_count=count, affinity_score=score))


@pytest.fixture(scope="module")
def basket_run(db, shop):
    sid = shop.id
    _add_product(db, sid, SKU_A, "Product A", price=20.0, cost=12.0)  # marge €8
    _add_product(db, sid, SKU_B, "Product B", price=20.0, cost=12.0)  # marge €8
    _add_product(db, sid, SKU_C, "Filler C", price=10.0, cost=6.0)    # marge €4
    _add_product(db, sid, SKU_U, "Upsell U", price=30.0, cost=18.0)
    _add_product(db, sid, SKU_D, "Product D", price=20.0, cost=12.0)

    _add_affinity(db, sid, SKU_A, SKU_B, 50, 0.90)
    _add_affinity(db, sid, SKU_A, SKU_C, 25, 0.40)
    _add_affinity(db, sid, SKU_A, SKU_U, 25, 0.50)
    _add_affinity(db, sid, SKU_D, SKU_C, 100, 0.95)
    # count 0 → mag géén associatie opleveren
    _add_affinity(db, sid, SKU_D, SKU_B, 0, 0.10)
    db.commit()

    result = run_basket_engine(db, run_date=RUN_DATE, shop_id=sid)
    assocs = db.query(models.BasketAssociation).filter(
        models.BasketAssociation.shop_id == sid,
        models.BasketAssociation.run_date == RUN_DATE).all()
    return result, {(a.antecedent_sku, a.consequent_sku): a for a in assocs}


class TestBasketEngine:
    def test_run_resultaat(self, basket_run):
        result, assocs = basket_run
        assert result["associations"] == 4  # count-0-rij overgeslagen
        assert result["skus"] == 5
        assert set(assocs) == {(SKU_A, SKU_B), (SKU_A, SKU_C), (SKU_A, SKU_U), (SKU_D, SKU_C)}

    def test_support_confidence_lift_bekende_waarden(self, basket_run):
        _, assocs = basket_run
        ab = assocs[(SKU_A, SKU_B)]
        # totaal 200 co-purchases; A→B = 50; A totaal = 100; B als consequent = 50
        assert float(ab.support) == pytest.approx(0.25, abs=1e-4)
        assert float(ab.confidence) == pytest.approx(0.50, abs=1e-3)
        assert float(ab.lift) == pytest.approx(2.0, abs=0.01)

        dc = assocs[(SKU_D, SKU_C)]
        assert float(dc.support) == pytest.approx(0.50, abs=1e-4)
        assert float(dc.confidence) == pytest.approx(1.0, abs=1e-3)  # geplafonneerd op 1.0
        assert float(dc.lift) == pytest.approx(1.6, abs=0.01)

    def test_lift_richting_positief_vs_negatief(self, basket_run):
        _, assocs = basket_run
        # A+B vaker samen dan verwacht (lift > 1); A+C juist minder vaak (lift < 1)
        assert float(assocs[(SKU_A, SKU_B)].lift) > 1.0
        assert float(assocs[(SKU_A, SKU_C)].lift) == pytest.approx(0.4, abs=0.01)
        assert float(assocs[(SKU_A, SKU_C)].lift) < 1.0

    def test_relatie_typen(self, basket_run):
        _, assocs = basket_run
        assert assocs[(SKU_A, SKU_B)].relation_type == "bundle"        # lift 2.0 ≥ 1.5
        assert assocs[(SKU_A, SKU_C)].relation_type == "basket_filler"  # C €10 ≤ €15 en A duurder
        assert assocs[(SKU_A, SKU_U)].relation_type == "upsell"        # €30 ≥ 1.25 × €20
        assert assocs[(SKU_D, SKU_C)].relation_type == "basket_filler"

    def test_bundelmarge_en_mandwaarde(self, basket_run):
        _, assocs = basket_run
        ab = assocs[(SKU_A, SKU_B)]
        assert float(ab.bundle_margin_eur) == pytest.approx(16.0, abs=0.01)  # €8 + €8
        assert float(ab.avg_basket_value) == pytest.approx(40.0, abs=0.01)
        assert ab.antecedent_name == "Product A"
        assert ab.consequent_name == "Product B"
        assert ab.model_version, "associatie moet een modelversie dragen"

    def test_herdraaien_is_idempotent(self, db, shop, basket_run):
        run_basket_engine(db, run_date=RUN_DATE, shop_id=shop.id)
        n = db.query(models.BasketAssociation).filter(
            models.BasketAssociation.shop_id == shop.id,
            models.BasketAssociation.run_date == RUN_DATE).count()
        assert n == 4, "herdraaien op dezelfde run_date mag geen duplicaten geven"

    def test_signalen_gepubliceerd_voor_sterkste_associaties(self, db, shop, basket_run):
        sigs = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.engine == "basket",
            models.IntelligenceSignal.signal_type == "strong_product_association",
            models.IntelligenceSignal.status == "active").all()
        assert len(sigs) >= 1
        # Hoogste affinity_score (D→C, 0.95) moet erbij zitten
        by_entity = {(s.entity_id, s.evidence.get("paired_sku")) for s in sigs}
        assert (SKU_D, SKU_C) in by_entity

    def test_fbt_gesorteerd_op_confidence(self, db, shop, basket_run):
        fbt = get_frequently_bought_together(db, SKU_A, shop_id=shop.id)
        assert [r["sku_id"] for r in fbt][0] == SKU_B  # hoogste confidence eerst
        assert {r["sku_id"] for r in fbt} == {SKU_B, SKU_C, SKU_U}
        assert fbt[0]["confidence"] == pytest.approx(0.5, abs=1e-3)

    def test_dashboard(self, db, shop, basket_run):
        dash = get_basket_association_dashboard(db, shop_id=shop.id)
        assert dash["run_date"] == str(RUN_DATE)
        assert dash["totaal_associaties"] == 4
        assert dash["per_type"] == {"bundle": 1, "upsell": 1, "basket_filler": 2}
        # Gemiddelde mandmarge: (16 + 12 + 20 + 12) / 4 = 15.0
        assert dash["gemiddelde_mandmarge"] == pytest.approx(15.0, abs=0.01)

    def test_geen_data_geeft_no_data(self, db):
        # Aparte lege shop → geen associaties, nette no-data-respons
        empty = models.DimShop(shop_code=f"{PFX}-empty", name=f"{PFX} Empty", active=True)
        db.add(empty)
        db.commit()
        try:
            result = run_basket_engine(db, run_date=RUN_DATE, shop_id=empty.id)
            assert result["associations"] == 0
            assert "detail" in result
            assert get_frequently_bought_together(db, SKU_A, shop_id=empty.id) == []
        finally:
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == empty.id).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == empty.id).delete(
                synchronize_session=False)
            db.commit()


# ── Promotie-halo via BasketAssociation ──────────────────────────────────────

def _seed_sales(db, sid, sku, days, units_fn, price=10.0, margin_unit=4.0, end=None):
    end = end or date.today() - timedelta(days=1)
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        u = int(units_fn(i, d))
        db.add(models.FactSalesDaily(
            date=d, sku_id=sku, shop_id=sid, units_sold=u,
            revenue=u * price, cost=u * (price - margin_unit), margin=u * margin_unit))


@pytest.fixture(scope="module")
def halo_effects(db, shop, basket_run):
    sid = shop.id
    today = date.today()
    p_start = today - timedelta(days=14)
    p_end = today - timedelta(days=1)

    # Gepromote SKU: baseline 10/dag, tijdens promo 20/dag
    db.add(models.DimProduct(
        sku_id=SKU_PROMO, product_name="Halo promo product", category=f"{CAT}-promo",
        shop_id=sid, current_price=20.0, cost_price=10.0, stock_quantity=1000, is_active=True))
    _seed_sales(db, sid, SKU_PROMO, 14, lambda i, d: 10, price=20.0, margin_unit=10.0,
                end=p_start - timedelta(days=1))
    _seed_sales(db, sid, SKU_PROMO, 14, lambda i, d: 20, price=16.0, margin_unit=6.0, end=p_end)
    promo = models.Promotion(sku_id=SKU_PROMO, promotion_type="percentage_off",
                             discount_value=20.0, start_date=p_start, end_date=p_end)
    db.add(promo)

    # Basket-gerelateerde SKU (andere categorie): baseline 10/dag → 15/dag tijdens promo
    db.add(models.DimProduct(
        sku_id=SKU_HALO, product_name="Halo related product", category=f"{CAT}-halo",
        shop_id=sid, current_price=10.0, cost_price=6.0, stock_quantity=1000, is_active=True))
    _seed_sales(db, sid, SKU_HALO, 14, lambda i, d: 10, end=p_start - timedelta(days=1))
    _seed_sales(db, sid, SKU_HALO, 14, lambda i, d: 15, end=p_end)
    db.add(models.BasketAssociation(
        run_date=RUN_DATE, shop_id=sid,
        antecedent_sku=SKU_PROMO, consequent_sku=SKU_HALO,
        support=0.2, confidence=0.6, lift=1.8, co_purchase_count=30,
        relation_type="cross_sell", model_version="test"))

    # Gepromote SKU zónder basket-associaties → halo moet None blijven
    db.add(models.DimProduct(
        sku_id=SKU_NOASSOC, product_name="No-assoc promo", category=f"{CAT}-noassoc",
        shop_id=sid, current_price=20.0, cost_price=10.0, stock_quantity=1000, is_active=True))
    _seed_sales(db, sid, SKU_NOASSOC, 28, lambda i, d: 10, price=20.0, margin_unit=10.0,
                end=p_end)
    promo2 = models.Promotion(sku_id=SKU_NOASSOC, promotion_type="percentage_off",
                              discount_value=10.0, start_date=p_start, end_date=p_end)
    db.add(promo2)
    db.commit()

    eff = analyze_promotion(db, promo, today, "test", sid, PROMOTION_DEFAULT_CONFIG)
    eff2 = analyze_promotion(db, promo2, today, "test", sid, PROMOTION_DEFAULT_CONFIG)
    db.commit()
    return eff, eff2


class TestPromotionHalo:
    def test_halo_gebruikt_basket_gerelateerde_skus(self, halo_effects):
        eff, _ = halo_effects
        assert eff is not None
        # Gerelateerde SKU: 10/dag → 15/dag = +50% halo
        assert eff.halo_pct is not None
        assert float(eff.halo_pct) == pytest.approx(50.0, abs=1.0)

    def test_halo_none_zonder_associaties(self, halo_effects):
        _, eff2 = halo_effects
        assert eff2 is not None
        assert eff2.halo_pct is None

    def test_halo_onafhankelijk_van_uplift(self, halo_effects):
        eff, _ = halo_effects
        # De promo zelf had +100% uplift; halo meet alléén de gerelateerde SKU's
        assert float(eff.uplift_pct) == pytest.approx(100.0, abs=2.0)
        assert float(eff.halo_pct) != pytest.approx(float(eff.uplift_pct), abs=1.0)
