"""
Regressietests voor de forecast-engine (§20) en de promotion-engine (§19).

Bewaakt met kleine synthetische datasets (bekende uplift, bekend
weekdag-seizoenspatroon) dat de rekenlogica niet stilletjes regresseert:
- _forecast_sku: richting (trend), betrouwbaarheidsband, seizoensfactor,
  minimale historie-eis en confidence-grenzen
- run_forecast_engine: forecasts per type/horizon, stock-forecast en
  risicodetectie (voorraad- en vraagrisico)
- analyze_promotion / run_promotion_engine: uplift-berekening, break-even,
  controlegroep-selectie en verdicts
"""
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine.forecast_engine import _forecast_sku, run_forecast_engine
from engine.promotion_engine import analyze_promotion, run_promotion_engine

PFX = f"FCTEST{uuid.uuid4().hex[:6]}"
CAT = f"{PFX}-cat"
CAT_FC = f"{PFX}-forecast-cat"  # aparte categorie: forecast-fixtures mogen de promotie-controlegroep niet vervuilen

SKU_STOCKRISK = f"{PFX}-STOCK"    # hoge vraag, lage voorraad → stock_risk
SKU_DECLINE = f"{PFX}-DECLINE"    # sterk dalende trend → demand_risk
SKU_STABLE = f"{PFX}-STABLE"      # stabiel, ruime voorraad → geen risico
SKU_PROMO = f"{PFX}-PROMO"        # promotie met bekende uplift
SKU_CONTROL = f"{PFX}-CTL"        # niet-gepromoot, zelfde categorie
SKU_PROMO2 = f"{PFX}-PROMO2"      # tweede gepromote SKU (mag niet in controlegroep)
SKU_LOSER = f"{PFX}-LOSER"        # promo zonder uplift → VERLIESGEVEND


# ── Synthetische rijen voor pure unit-tests (geen DB nodig) ───────────────────

@dataclass
class Row:
    date: date
    units_sold: float
    revenue: float = 0.0
    margin: float = 0.0


def make_rows(days: int, units_fn, price: float = 10.0, margin_unit: float = 4.0,
              end: date | None = None) -> list:
    end = end or date(2026, 8, 18)
    rows = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        u = float(units_fn(i, d))
        rows.append(Row(date=d, units_sold=u, revenue=u * price, margin=u * margin_unit))
    return rows


# ── Unit-tests _forecast_sku ─────────────────────────────────────────────────

class TestForecastSku:
    def test_te_weinig_historie_geeft_none(self):
        rows = make_rows(10, lambda i, d: 10)
        assert _forecast_sku(rows, 30, min_history_days=14) is None

    def test_constante_afzet_forecast_richting_en_band(self):
        # 56 dagen exact 10/dag → 30-dagen forecast ≈ 300, band ≈ 0
        rows = make_rows(56, lambda i, d: 10)
        fc = _forecast_sku(rows, 30)
        assert fc is not None
        assert fc["units"] == pytest.approx(300.0, rel=0.02)
        # Betrouwbaarheidsband: lower ≤ waarde ≤ upper en lower ≥ 0
        assert fc["units_lower"] <= fc["units"] <= fc["units_upper"]
        assert fc["units_lower"] >= 0.0
        # Geen ruis → nauwe band en hoge confidence
        assert fc["units_upper"] - fc["units_lower"] < 1.0
        assert fc["confidence"] >= 0.8
        assert fc["trend_pct_30"] == pytest.approx(0.0, abs=0.5)
        assert fc["seasonality_factor"] == pytest.approx(1.0, abs=0.01)

    def test_weekdag_seizoenspatroon_wordt_opgepikt(self):
        # Zaterdag verkoopt 3x zoveel als andere dagen
        rows = make_rows(56, lambda i, d: 30 if d.weekday() == 5 else 10)
        fc = _forecast_sku(rows, 30)
        assert fc is not None
        # seasonality_factor = max weekdaggem. / totaalgemiddelde > 1
        assert fc["seasonality_factor"] > 1.5
        # Verwachte 30d-afzet: ~4-5 zaterdagen à 30 + rest à 10
        expected = sum(30 if (rows[-1].date + timedelta(days=1 + i)).weekday() == 5 else 10
                       for i in range(30))
        assert fc["units"] == pytest.approx(expected, rel=0.05)

    def test_stijgende_trend_positief_dalende_negatief(self):
        rising = make_rows(56, lambda i, d: 5 + i * 0.5)
        falling = make_rows(56, lambda i, d: 33 - i * 0.5)
        fc_up = _forecast_sku(rising, 30)
        fc_down = _forecast_sku(falling, 30)
        assert fc_up["trend_pct_30"] > 0
        assert fc_down["trend_pct_30"] < 0
        # Richting werkt door in de forecast: stijgend > dalend bij zelfde gemiddelde
        assert fc_up["units"] > fc_down["units"]

    def test_ruis_verlaagt_confidence_en_verbreedt_band(self):
        calm = make_rows(56, lambda i, d: 10)
        noisy = make_rows(56, lambda i, d: 2 if i % 2 == 0 else 18)  # zelfde gemiddelde
        fc_calm = _forecast_sku(calm, 30)
        fc_noisy = _forecast_sku(noisy, 30)
        assert fc_noisy["confidence"] < fc_calm["confidence"]
        band_calm = fc_calm["units_upper"] - fc_calm["units_lower"]
        band_noisy = fc_noisy["units_upper"] - fc_noisy["units_lower"]
        assert band_noisy > band_calm

    def test_confidence_binnen_grenzen(self):
        for rows in (make_rows(14, lambda i, d: 1 if i % 7 == 0 else 20),
                     make_rows(120, lambda i, d: 10)):
            fc = _forecast_sku(rows, 90)
            assert 0.2 <= fc["confidence"] <= 0.95

    def test_langere_horizon_lagere_confidence(self):
        rows = make_rows(56, lambda i, d: 10)
        assert _forecast_sku(rows, 90)["confidence"] < _forecast_sku(rows, 30)["confidence"]


# ── DB-fixtures voor integratietests ─────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(scope="module")
def shop(db):
    shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Forecast Shop", active=True)
    db.add(shop)
    db.commit()
    sid = shop.id
    yield shop
    # Teardown — alle testdata van deze shop opruimen (incl. FK-afhankelijkheden)
    for model, col in [
        (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
        (models.FactForecastDaily, models.FactForecastDaily.shop_id),
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


def _seed_sales(db, sid, sku, days, units_fn, price=10.0, margin_unit=4.0, end=None):
    end = end or date.today() - timedelta(days=1)
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        u = int(units_fn(i, d))
        db.add(models.FactSalesDaily(
            date=d, sku_id=sku, shop_id=sid, units_sold=u,
            revenue=u * price, cost=u * (price - margin_unit), margin=u * margin_unit))


def _add_product(db, sid, sku, name, stock, price=10.0, cost=6.0, category=CAT):
    db.add(models.DimProduct(
        sku_id=sku, product_name=name, category=category, shop_id=sid,
        current_price=price, cost_price=cost, stock_quantity=stock, is_active=True))


# ── Integratie: forecast-engine + risicodetectie ─────────────────────────────

@pytest.fixture(scope="module")
def forecast_run(db, shop):
    sid = shop.id
    # Stock-risico: 10/dag vraag, maar slechts 50 op voorraad (~5 dagen dekking)
    _add_product(db, sid, SKU_STOCKRISK, "Stockrisk product", stock=50, category=CAT_FC)
    _seed_sales(db, sid, SKU_STOCKRISK, 60, lambda i, d: 10)
    # Demand-risico: sterk dalend (van 40 naar ~4)
    _add_product(db, sid, SKU_DECLINE, "Declining product", stock=5000, category=CAT_FC)
    _seed_sales(db, sid, SKU_DECLINE, 60, lambda i, d: max(1, 40 - i * 0.6))
    # Stabiel en ruim op voorraad: geen risico's
    _add_product(db, sid, SKU_STABLE, "Stable product", stock=5000, category=CAT_FC)
    _seed_sales(db, sid, SKU_STABLE, 60, lambda i, d: 10)
    db.commit()
    result = run_forecast_engine(db, shop_id=sid)
    return result


class TestForecastEngine:
    def test_run_resultaat(self, forecast_run):
        assert forecast_run["skus"] == 3
        # 3 SKU's × 2 horizonnen × 4 forecast-types
        assert forecast_run["forecasts"] == 24
        assert forecast_run["risk_signals"] >= 2

    def test_forecast_rijen_per_type_en_horizon(self, db, shop, forecast_run):
        rows = db.query(models.FactForecastDaily).filter(
            models.FactForecastDaily.shop_id == shop.id,
            models.FactForecastDaily.sku_id == SKU_STABLE).all()
        combos = {(r.forecast_type, r.horizon_days) for r in rows}
        assert combos == {(t, h) for t in ("units", "revenue", "margin", "stock")
                          for h in (30, 90)}
        by_type = {(r.forecast_type, r.horizon_days): r for r in rows}
        u30 = by_type[("units", 30)]
        assert u30.forecast_value == pytest.approx(300.0, rel=0.05)
        assert u30.lower_bound <= u30.forecast_value <= u30.upper_bound
        # Revenue = units × €10/eenheid, margin = units × €4/eenheid
        assert by_type[("revenue", 30)].forecast_value == pytest.approx(
            u30.forecast_value * 10.0, rel=0.01)
        assert by_type[("margin", 30)].forecast_value == pytest.approx(
            u30.forecast_value * 4.0, rel=0.01)
        # Stock-eindstand = voorraad − verwachte afzet
        assert by_type[("stock", 30)].forecast_value == pytest.approx(
            5000 - u30.forecast_value, rel=0.01)
        assert u30.model_version, "forecast moet een modelversie dragen"

    def test_stock_risico_gedetecteerd(self, db, shop, forecast_run):
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.engine == "forecast_risk",
            models.IntelligenceSignal.signal_type == "stock_risk",
            models.IntelligenceSignal.entity_id == SKU_STOCKRISK,
            models.IntelligenceSignal.status == "active").first()
        assert sig is not None, "verwacht stock_risk-signaal bij 5 dagen dekking"
        assert sig.severity == "high"  # < 14 dagen dekking
        assert sig.evidence["days_of_stock"] == pytest.approx(5.0, abs=1.0)
        assert sig.explanation and sig.evidence and sig.sources

    def test_demand_risico_gedetecteerd(self, db, shop, forecast_run):
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.signal_type == "demand_risk",
            models.IntelligenceSignal.entity_id == SKU_DECLINE,
            models.IntelligenceSignal.status == "active").first()
        assert sig is not None, "verwacht demand_risk-signaal bij sterk dalende trend"
        assert sig.change_pct is not None and sig.change_pct < -15.0

    def test_stabiel_product_zonder_risico(self, db, shop, forecast_run):
        n = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.engine == "forecast_risk",
            models.IntelligenceSignal.entity_id == SKU_STABLE,
            models.IntelligenceSignal.status == "active").count()
        assert n == 0


# ── Integratie: promotion-engine ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def promo_run(db, shop, forecast_run):
    sid = shop.id
    today = date.today()
    p_start = today - timedelta(days=14)
    p_end = today - timedelta(days=1)

    # Gepromote SKU: baseline 10/dag, tijdens promo 20/dag (bekende uplift 100%).
    # Prijs €20, kost €10; 20% korting → korting €4/stuk.
    _add_product(db, sid, SKU_PROMO, "Promo product", stock=1000, price=20.0, cost=10.0)
    _seed_sales(db, sid, SKU_PROMO, 14, lambda i, d: 10, price=20.0, margin_unit=10.0,
                end=p_start - timedelta(days=1))
    _seed_sales(db, sid, SKU_PROMO, 14, lambda i, d: 20, price=16.0, margin_unit=6.0,
                end=p_end)
    promo = models.Promotion(sku_id=SKU_PROMO, promotion_type="percentage_off",
                             discount_value=20.0, start_date=p_start, end_date=p_end)
    db.add(promo)

    # Controle-SKU: zelfde categorie, vlak (10/dag), niet gepromoot
    _add_product(db, sid, SKU_CONTROL, "Control product", stock=1000)
    _seed_sales(db, sid, SKU_CONTROL, 28, lambda i, d: 10, end=p_end)

    # Tweede gepromote SKU (overlappend) — mag NIET in de controlegroep zitten
    _add_product(db, sid, SKU_PROMO2, "Promo product 2", stock=1000, price=20.0, cost=10.0)
    _seed_sales(db, sid, SKU_PROMO2, 28, lambda i, d: 10, price=20.0, margin_unit=10.0,
                end=p_end)
    db.add(models.Promotion(sku_id=SKU_PROMO2, promotion_type="fixed_amount",
                            discount_value=2.0, start_date=p_start, end_date=p_end))

    # Verliesgevende promo: geen uplift, wel korting en lagere marge tijdens promo
    _add_product(db, sid, SKU_LOSER, "Loser product", stock=1000, price=20.0, cost=10.0)
    _seed_sales(db, sid, SKU_LOSER, 14, lambda i, d: 10, price=20.0, margin_unit=10.0,
                end=p_start - timedelta(days=1))
    _seed_sales(db, sid, SKU_LOSER, 14, lambda i, d: 10, price=14.0, margin_unit=4.0,
                end=p_end)
    db.add(models.Promotion(sku_id=SKU_LOSER, promotion_type="percentage_off",
                            discount_value=30.0, start_date=p_start, end_date=p_end))
    db.commit()

    result = run_promotion_engine(db, shop_id=sid)
    effects = {e.sku_id: e for e in db.query(models.FactPromotionEffect).filter(
        models.FactPromotionEffect.shop_id == sid).all()}
    return result, effects


class TestPromotionEngine:
    def test_run_analyseert_alle_promoties(self, promo_run):
        result, effects = promo_run
        assert result["promotions"] == 3
        assert result["analyzed"] == 3
        assert set(effects) == {SKU_PROMO, SKU_PROMO2, SKU_LOSER}

    def test_uplift_berekening_bekende_uplift(self, promo_run):
        _, effects = promo_run
        eff = effects[SKU_PROMO]
        # 10/dag → 20/dag = +100% bruto uplift
        assert float(eff.uplift_pct) == pytest.approx(100.0, abs=2.0)
        assert float(eff.baseline_units_per_day) == pytest.approx(10.0, abs=0.1)
        assert float(eff.promo_units_per_day) == pytest.approx(20.0, abs=0.1)

    def test_controlegroep_selectie(self, promo_run):
        _, effects = promo_run
        eff = effects[SKU_PROMO]
        assert eff.control_group_used is True
        # Alleen SKU_CONTROL is niet-gepromoot in deze categorie
        assert eff.control_group_size == 1
        # Controlegroep vlak (10/dag) → controle-uplift 0, netto = bruto uplift
        assert float(eff.control_uplift_pct) == pytest.approx(0.0, abs=1.0)
        assert float(eff.net_uplift_pct) == pytest.approx(
            float(eff.uplift_pct) - float(eff.control_uplift_pct), abs=0.1)

    def test_gepromote_skus_niet_in_controlegroep(self, db, shop, promo_run):
        _, effects = promo_run
        # Categorie bevat 4 SKU's; 3 gepromoot → alleen SKU_CONTROL blijft over.
        assert effects[SKU_PROMO].control_group_size == 1
        assert effects[SKU_PROMO2].control_group_size == 1

    def test_break_even_berekening(self, promo_run):
        _, effects = promo_run
        eff = effects[SKU_PROMO]
        # korting €4/stuk; promo-marge €6/stuk; margeverlies = 4 × 10/dag × 14d = €560
        # → break-even = 560/6 ≈ 93.3 extra stuks; gerealiseerd 10×14 = 140 → gehaald
        assert float(eff.break_even_extra_units) == pytest.approx(93.3, abs=1.0)
        assert eff.break_even_achieved is True
        assert eff.verdict == "EFFECTIEF"
        # Incrementele marge: (20×6 − 10×10)/dag × 14d = €280
        assert float(eff.incremental_margin) == pytest.approx(280.0, abs=5.0)

    def test_verliesgevende_promo(self, promo_run):
        _, effects = promo_run
        eff = effects[SKU_LOSER]
        assert float(eff.uplift_pct) == pytest.approx(0.0, abs=2.0)
        assert eff.break_even_achieved is False
        assert float(eff.incremental_margin) < 0
        assert eff.verdict == "VERLIESGEVEND"

    def test_signalen_gepubliceerd(self, db, shop, promo_run):
        eff_sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.signal_type == "promotion_effective",
            models.IntelligenceSignal.entity_id == SKU_PROMO,
            models.IntelligenceSignal.status == "active").first()
        loss_sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop.id,
            models.IntelligenceSignal.signal_type == "promotion_loss_making",
            models.IntelligenceSignal.entity_id == SKU_LOSER,
            models.IntelligenceSignal.status == "active").first()
        assert eff_sig is not None
        assert loss_sig is not None and loss_sig.severity == "high"

    def test_geen_effect_zonder_baseline(self, db, shop, promo_run):
        # Promotie op SKU zonder baseline-verkoop → geen effectrij (return None)
        sku = f"{PFX}-NOBASE"
        _add_product(db, shop.id, sku, "No baseline", stock=10)
        promo = models.Promotion(sku_id=sku, promotion_type="percentage_off",
                                 discount_value=10.0,
                                 start_date=date.today() - timedelta(days=7),
                                 end_date=date.today() - timedelta(days=1))
        db.add(promo)
        db.commit()
        eff = analyze_promotion(db, promo, date.today(), "test", shop.id,
                                {"min_baseline_days": 7, "marginal_uplift_threshold_pct": 5.0})
        assert eff is None
        db.rollback()
