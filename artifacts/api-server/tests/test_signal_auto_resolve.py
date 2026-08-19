"""
Tests voor auto-resolve van engine-signalen (taak: los waarschuwingssignalen
automatisch op zodra het probleem verholpen is).

Patroon per signaaltype: publiceren (conditie geldt) → verhelpen (brondata
aanpassen) → emitter opnieuw draaien → signaal staat op 'resolved'.
Idempotentie: nog een run raakt het resolved-signaal niet opnieuw aan en
publiceert het niet opnieuw.

De tests draaien tegen de dev-database (zelfde conventie als
test_signal_publisher.py); alle aangemaakte rijen worden opgeruimd.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date as date_type, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine.signal_publisher import (
    publish_signal, auto_resolve_signals, _default_shop_id)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    try:
        s.rollback()
        s.close()
    except Exception:
        pass


def _signal_for(db, sku_id, signal_type=None):
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.entity_id == sku_id)
    if signal_type:
        q = q.filter(models.IntelligenceSignal.signal_type == signal_type)
    return q.order_by(models.IntelligenceSignal.id.desc()).first()


def _cleanup_signals(sku_ids):
    s = SessionLocal()
    try:
        s.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_id.in_(list(sku_ids))
        ).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()


# ══════════════════════════════════════════════════════════════════════════════
# Unit: auto_resolve_signals
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoResolveHelper:
    def _publish(self, db, engine, signal_type, entity_id):
        return publish_signal(
            db, engine=engine, signal_type=signal_type,
            entity_type="sku", entity_id=entity_id,
            explanation="Testsignaal.", evidence={"v": 1}, sources=["t"],
        )

    def test_resolves_signal_not_in_still_active(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig = self._publish(db, "ar_test", "cond_a", eid)
        db.flush()
        n = auto_resolve_signals(db, engine="ar_test", still_active=set())
        assert n >= 1
        assert sig.status == "resolved"

    def test_keeps_signal_still_in_condition(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig = self._publish(db, "ar_test", "cond_a", eid)
        db.flush()
        auto_resolve_signals(db, engine="ar_test",
                             still_active={("cond_a", eid)})
        assert sig.status == "active"

    def test_idempotent_already_resolved_not_touched(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig = self._publish(db, "ar_test", "cond_a", eid)
        db.flush()
        auto_resolve_signals(db, engine="ar_test", still_active=set())
        assert sig.status == "resolved"
        # Tweede run: raakt al-resolved signaal niet opnieuw aan
        n2 = auto_resolve_signals(db, engine="ar_test", still_active=set())
        db.flush()
        # De resolved rij telt niet meer mee (alleen 'active' wordt aangeraakt)
        remaining = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_id == eid,
            models.IntelligenceSignal.status == "active").count()
        assert remaining == 0
        assert sig.status == "resolved"

    def test_signal_types_filter_limits_scope(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig_a = self._publish(db, "ar_test", "cond_a", eid)
        sig_b = self._publish(db, "ar_test", "cond_b", eid)
        db.flush()
        auto_resolve_signals(db, engine="ar_test",
                             signal_types=["cond_a"], still_active=set())
        assert sig_a.status == "resolved"
        assert sig_b.status == "active"

    def test_other_engine_untouched(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig = self._publish(db, "ar_other_engine", "cond_a", eid)
        db.flush()
        auto_resolve_signals(db, engine="ar_test", still_active=set())
        assert sig.status == "active"

    def test_other_shop_signal_untouched(self, db):
        """Regressie: resolutie is shop-gescoped. Een identiek signaal
        (zelfde type + entity) van een andere winkel mag NIET worden
        geresolved op basis van brondata van de default shop."""
        eid = f"SKU-AR-{_unique()}"
        other_shop = models.DimShop(shop_code=f"ARSHOP{_unique()[:6]}",
                                    name="AR testshop", active=True)
        db.add(other_shop)
        db.flush()

        sig_default = self._publish(db, "ar_test", "cond_a", eid)
        sig_other = publish_signal(
            db, engine="ar_test", signal_type="cond_a",
            entity_type="sku", entity_id=eid,
            explanation="Testsignaal andere shop.", evidence={"v": 1},
            sources=["t"], shop_id=other_shop.id)
        db.flush()

        # Zonder expliciete shop_id: alleen default shop wordt geëvalueerd
        auto_resolve_signals(db, engine="ar_test", still_active=set())
        assert sig_default.status == "resolved"
        assert sig_other.status == "active", \
            "Signaal van andere winkel mag niet worden geresolved"

        # Met expliciete shop_id: alleen die shop
        auto_resolve_signals(db, engine="ar_test", still_active=set(),
                             shop_id=other_shop.id)
        assert sig_other.status == "resolved"

    def test_entity_type_filter_limits_scope(self, db):
        eid = f"ENT-AR-{_unique()}"
        sig_sku = self._publish(db, "ar_test", "cond_a", eid)
        sig_comp = publish_signal(
            db, engine="ar_test", signal_type="cond_a",
            entity_type="competitor", entity_id=eid,
            explanation="Testsignaal.", evidence={"v": 1}, sources=["t"])
        db.flush()
        auto_resolve_signals(db, engine="ar_test", entity_type="sku",
                             still_active=set())
        assert sig_sku.status == "resolved"
        assert sig_comp.status == "active"

    def test_dismissed_signal_untouched(self, db):
        eid = f"SKU-AR-{_unique()}"
        sig = self._publish(db, "ar_test", "cond_a", eid)
        db.flush()
        sig.status = "dismissed"
        db.flush()
        auto_resolve_signals(db, engine="ar_test", still_active=set())
        assert sig.status == "dismissed"


# ══════════════════════════════════════════════════════════════════════════════
# Integratie per signaaltype: publiceren → verhelpen → auto-resolve
# ══════════════════════════════════════════════════════════════════════════════

class TestCompetitionAutoResolve:
    def test_pressure_and_opportunity_resolve_when_fixed(self):
        from engine.signal_emitters import emit_competition_signals
        uid = _unique()
        sku_hi = f"SKU-ARP-{uid}"   # duurder → competitive_pressure_increased
        sku_lo = f"SKU-ARO-{uid}"   # goedkoper → price_increase_opportunity

        s = SessionLocal()
        try:
            s.add(models.SkuCompetitionScore(
                sku_id=sku_hi, run_date=date_type.today(), price_index=9.99,
                competition_class="Critical", pcis_score=0.8,
                reference_price=10.0, competitors_used=5, competitors_excluded=0))
            s.add(models.SkuCompetitionScore(
                sku_id=sku_lo, run_date=date_type.today(), price_index=0.01,
                competition_class="Monitor", pcis_score=0.3,
                reference_price=10.0, competitors_used=3, competitors_excluded=0))
            s.commit()

            emit_competition_signals(s)
            s.commit()
            assert _signal_for(s, sku_hi, "competitive_pressure_increased").status == "active"
            assert _signal_for(s, sku_lo, "price_increase_opportunity").status == "active"

            # Verhelpen: prijsindex terug naar neutraal
            s.query(models.SkuCompetitionScore).filter(
                models.SkuCompetitionScore.sku_id.in_([sku_hi, sku_lo])
            ).update({"price_index": 1.0}, synchronize_session=False)
            s.commit()

            emit_competition_signals(s)
            s.commit()
            sig_hi = _signal_for(s, sku_hi, "competitive_pressure_increased")
            sig_lo = _signal_for(s, sku_lo, "price_increase_opportunity")
            assert sig_hi.status == "resolved"
            assert sig_lo.status == "resolved"

            # Idempotent: nog een run publiceert niet opnieuw en laat resolved staan
            emit_competition_signals(s)
            s.commit()
            count_hi = s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == sku_hi).count()
            assert count_hi == 1
            s.refresh(sig_hi)
            assert sig_hi.status == "resolved"
        finally:
            s.query(models.SkuCompetitionScore).filter(
                models.SkuCompetitionScore.sku_id.in_([sku_hi, sku_lo])).delete(
                synchronize_session=False)
            s.commit()
            s.close()
            _cleanup_signals([sku_hi, sku_lo])


class TestEmitterShopIsolation:
    """Regressie: brondata van een niet-default winkel mag niet in de
    default-shop-scope publiceren, en mag daar ook geen signalen resolven."""

    def test_foreign_shop_score_does_not_publish_or_resolve(self):
        from engine.signal_emitters import emit_competition_signals
        uid = _unique()
        sku_id = f"SKU-ARFS-{uid}"

        s = SessionLocal()
        other_id = None
        try:
            other = models.DimShop(shop_code=f"ARFS{uid[:6]}",
                                   name="AR isolatie-shop", active=True)
            s.add(other)
            s.flush()
            other_id = other.id

            # Kwalificerende score in de ANDERE winkel + actief signaal
            # voor dezelfde SKU in die andere winkel
            s.add(models.SkuCompetitionScore(
                sku_id=sku_id, run_date=date_type.today(), price_index=9.99,
                competition_class="Critical", pcis_score=0.8, shop_id=other_id,
                reference_price=10.0, competitors_used=5, competitors_excluded=0))
            other_sig = publish_signal(
                s, engine="competition",
                signal_type="competitive_pressure_increased",
                entity_type="sku", entity_id=sku_id,
                explanation="Signaal andere winkel.", evidence={"v": 1},
                sources=["t"], shop_id=other_id)
            s.commit()
            other_sig_id = other_sig.id

            emit_competition_signals(s)
            s.commit()

            # Niet in default shop gepubliceerd
            default_sigs = s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == sku_id,
                models.IntelligenceSignal.shop_id != other_id).count()
            assert default_sigs == 0, \
                "Score van andere winkel mag geen default-shop-signaal publiceren"
            # Andere-winkelsignaal niet geresolved door default-run
            refreshed = s.query(models.IntelligenceSignal).get(other_sig_id)
            assert refreshed.status == "active", \
                "Default-shop-run mag signaal van andere winkel niet resolven"
        finally:
            s.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            if other_id:
                s.query(models.DimShop).filter_by(id=other_id).delete()
            s.commit()
            s.close()

    def test_foreign_shop_recommendation_ignored(self):
        from engine.signal_emitters import emit_pricing_signals
        uid = _unique()
        sku_id = f"SKU-ARFP-{uid}"
        today = date_type.today()

        s = SessionLocal()
        other_id = None
        try:
            other = models.DimShop(shop_code=f"ARFP{uid[:6]}",
                                   name="AR isolatie-shop 2", active=True)
            s.add(other)
            s.flush()
            other_id = other.id

            s.add(models.FactPricingRecommendationDaily(
                date=today, sku_id=sku_id, shop_id=other_id,
                current_price=10.0, recommended_price=10.5,
                recommended_change_pct=5.0, expected_margin_uplift=0.4,
                expected_revenue=105.0, confidence_score=0.8,
                reason_code="margin_improvement", strategy_type="MARGIN_DEFENSE",
                safety_status="ok", approval_status="pending",
                model_version="pricing-v2"))
            s.commit()

            emit_pricing_signals(s)
            s.commit()
            default_sigs = s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == sku_id,
                models.IntelligenceSignal.shop_id != other_id).count()
            assert default_sigs == 0, \
                "Aanbeveling van andere winkel mag geen default-shop-signaal publiceren"
        finally:
            s.query(models.FactPricingRecommendationDaily).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            if other_id:
                s.query(models.DimShop).filter_by(id=other_id).delete()
            s.commit()
            s.close()


class TestRunSnapshotScoping:
    """Regressies: alleen de laatste run van de eigen winkel telt."""

    def test_stale_qualifying_score_does_not_keep_signal_active(self):
        """SKU kwalificeerde gisteren maar is vandaag neutraal → resolve."""
        from engine.signal_emitters import emit_competition_signals
        uid = _unique()
        sku_id = f"SKU-ARSTALE-{uid}"
        s = SessionLocal()
        try:
            sig = publish_signal(
                s, engine="competition",
                signal_type="competitive_pressure_increased",
                entity_type="sku", entity_id=sku_id,
                explanation="Oude druk.", evidence={"v": 1}, sources=["t"])
            s.commit()
            sig_id = sig.id
            # Oude run: kwalificeert; laatste run: neutraal
            s.add(models.SkuCompetitionScore(
                sku_id=sku_id, run_date=date_type.today() - timedelta(days=1),
                price_index=9.99, competition_class="Critical", pcis_score=0.8,
                reference_price=10.0, competitors_used=5, competitors_excluded=0))
            s.add(models.SkuCompetitionScore(
                sku_id=sku_id, run_date=date_type.today(),
                price_index=1.0, competition_class="Neutral", pcis_score=0.2,
                reference_price=10.0, competitors_used=5, competitors_excluded=0))
            s.commit()

            emit_competition_signals(s)
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "resolved", (
                "Een verouderde kwalificerende score mag een inmiddels "
                "neutraal signaal niet actief houden")
        finally:
            s.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            s.commit()
            s.close()

    def test_newer_foreign_shop_run_does_not_resolve_default_signals(self):
        """Nieuwere run van een andere winkel → default-shop signalen blijven."""
        from engine.signal_emitters import emit_bcg_signals
        uid = _unique()
        own_sku = f"SKU-ARNFR-{uid}"
        foreign_sku = f"SKU-ARNFRF-{uid}"
        today = date_type.today()
        s = SessionLocal()
        other_id = None
        try:
            sid = _default_shop_id(s)
            other = models.DimShop(shop_code=f"ARNF{uid[:6]}",
                                   name="AR nieuwere-run-shop", active=True)
            s.add(other)
            s.flush()
            other_id = other.id
            s.add(models.DimProduct(sku_id=own_sku, product_name="Eigen ster",
                                    shop_id=sid))
            s.add(models.DimProduct(sku_id=foreign_sku, product_name="Vreemd",
                                    shop_id=other_id))
            # Eigen (oudere) run: SKU kwalificeert nog steeds als ster
            s.add(models.FactBcgClassificationDaily(
                date=today - timedelta(days=1), entity_type="SKU",
                entity_id=own_sku, entity_name="Eigen ster",
                hybrid_bcg_class="PRICING_POWER_STAR", pricing_power_score=0.9,
                confidence_score=0.8))
            # Nieuwere run van de ANDERE winkel
            s.add(models.FactBcgClassificationDaily(
                date=today, entity_type="SKU",
                entity_id=foreign_sku, entity_name="Vreemd",
                hybrid_bcg_class="LOW_PRIORITY_DOG", gps_score=0.1,
                confidence_score=0.8))
            sig = publish_signal(
                s, engine="bcg", signal_type="pricing_power_high",
                entity_type="sku", entity_id=own_sku,
                explanation="Ster.", evidence={"v": 1}, sources=["t"])
            s.commit()
            sig_id = sig.id

            emit_bcg_signals(s)
            s.commit()
            # De eigen (oudere) run kwalificeert nog → het signaal moet actief
            # blijven (eventueel als verse superseded-opvolger), en mag zeker
            # niet 'resolved' zijn door de nieuwere run van de andere winkel.
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status != "resolved", (
                "Een nieuwere run van een andere winkel mag signalen van de "
                "default shop niet resolven")
            active = s.query(models.IntelligenceSignal).filter_by(
                entity_id=own_sku, signal_type="pricing_power_high",
                status="active").count()
            assert active == 1, "eigen signaal moet actief blijven"
        finally:
            for sku in (own_sku, foreign_sku):
                s.query(models.FactBcgClassificationDaily).filter_by(entity_id=sku).delete()
                s.query(models.IntelligenceSignal).filter_by(entity_id=sku).delete()
                s.query(models.DimProduct).filter_by(sku_id=sku).delete()
            if other_id:
                s.query(models.DimShop).filter_by(id=other_id).delete()
            s.commit()
            s.close()


class TestPricingAutoResolve:
    def test_resolves_when_recommendation_no_longer_pending(self):
        from engine.signal_emitters import emit_pricing_signals
        uid = _unique()
        sku_id = f"SKU-ARPR-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            rec = models.FactPricingRecommendationDaily(
                date=today, sku_id=sku_id, shop_id=1,
                current_price=10.0, recommended_price=10.5,
                recommended_change_pct=5.0, expected_margin_uplift=0.4,
                expected_revenue=105.0, confidence_score=0.8,
                reason_code="margin_improvement", strategy_type="MARGIN_DEFENSE",
                safety_status="ok", approval_status="pending",
                model_version="pricing-v2")
            s.add(rec)
            s.commit()

            emit_pricing_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "price_increase_recommended").status == "active"

            # Verhelpen: aanbeveling beoordeeld (niet meer pending)
            rec.approval_status = "approved"
            s.commit()

            emit_pricing_signals(s)
            s.commit()
            sig = _signal_for(s, sku_id, "price_increase_recommended")
            assert sig.status == "resolved"
        finally:
            s.query(models.FactPricingRecommendationDaily).filter_by(
                sku_id=sku_id).delete()
            s.commit()
            s.close()
            _cleanup_signals([sku_id])


class TestBcgAutoResolve:
    def test_resolves_when_class_changes(self):
        from engine.signal_emitters import emit_bcg_signals
        uid = _unique()
        eid = f"SKU-ARBCG-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.FactBcgClassificationDaily(
                date=today, entity_type="SKU", entity_id=eid,
                entity_name=f"Test {uid}", hybrid_bcg_class="PRICING_POWER_STAR",
                pricing_power_score=0.82, css_external_score=0.25,
                ibss_score=0.7, gps_score=0.65,
                pricing_strategy="PROTECT_MARGIN", confidence_score=0.78)
            s.add(row)
            s.commit()

            emit_bcg_signals(s)
            s.commit()
            assert _signal_for(s, eid, "pricing_power_high").status == "active"

            row.hybrid_bcg_class = "QUESTION_MARK"
            s.commit()

            emit_bcg_signals(s)
            s.commit()
            assert _signal_for(s, eid, "pricing_power_high").status == "resolved"
        finally:
            s.query(models.FactBcgClassificationDaily).filter_by(entity_id=eid).delete()
            s.commit()
            s.close()
            _cleanup_signals([eid])


class TestTrafficAutoResolve:
    def test_resolves_when_reason_code_clears(self):
        from engine.signal_emitters import emit_traffic_signals
        uid = _unique()
        eid = f"SKU-ARTR-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.FactTrafficIntelligenceDaily(
                date=today, entity_type="SKU", entity_id=eid,
                entity_name=f"Test {uid}",
                conversion_risk_score=0.95, traffic_opportunity_score=0.9,
                traffic_growth=-0.4, conversion_trend=-0.3,
                reason_code="CONVERSION_DROP_DETECTED",
                explanation_nl="Conversie gedaald.")
            s.add(row)
            s.commit()

            emit_traffic_signals(s)
            s.commit()
            assert _signal_for(s, eid, "conversion_drop_detected").status == "active"

            # Verhelpen: geen signaalcode meer op de laatste run
            row.reason_code = "NO_SIGNAL"
            s.commit()

            emit_traffic_signals(s)
            s.commit()
            assert _signal_for(s, eid, "conversion_drop_detected").status == "resolved"
        finally:
            s.query(models.FactTrafficIntelligenceDaily).filter_by(entity_id=eid).delete()
            s.commit()
            s.close()
            _cleanup_signals([eid])


class TestProcurementAutoResolve:
    def test_resolves_when_signal_code_becomes_stable(self):
        from engine.signal_emitters import emit_procurement_signals
        uid = _unique()
        sku_id = f"SKU-ARPC-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.FactProcurementForecastDaily(
                date=today, sku_id=sku_id, sku_name=f"Test {uid}",
                price_change_pct_90d=12.0,
                procurement_opportunity_score=0.9, future_margin_risk_score=0.1,
                signal_code="BUY_NOW", signal_label_nl="Nu inkopen",
                recommended_action_nl="Bestel nu", recommended_order_qty=10,
                lead_time_days=14)
            s.add(row)
            s.commit()

            emit_procurement_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "buy_now").status == "active"

            row.signal_code = "STABLE"
            s.commit()

            emit_procurement_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "buy_now").status == "resolved"
        finally:
            s.query(models.FactProcurementForecastDaily).filter_by(sku_id=sku_id).delete()
            s.commit()
            s.close()
            _cleanup_signals([sku_id])


class TestSwitchingAutoResolve:
    def test_resolves_when_switch_probability_drops(self):
        from engine.signal_emitters import emit_switching_signals
        uid = _unique()
        sku_id = f"SKU-ARSW-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.InternalCompetitionScore(
                sku_id=sku_id, paired_sku_id=f"SKU-PL-{uid}", run_date=today,
                internal_switch_probability=0.6, internal_margin_gap=1.5,
                isv=99.9,  # extreem hoog → altijd in top-selectie
                recommended_internal_action="PRIVATE_LABEL_PUSH",
                a_brand_price=10.0, private_label_price=7.0)
            s.add(row)
            s.commit()

            emit_switching_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "cannibalisation_risk").status == "active"

            row.internal_switch_probability = 0.05
            s.commit()

            emit_switching_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "cannibalisation_risk").status == "resolved"
        finally:
            s.query(models.InternalCompetitionScore).filter_by(sku_id=sku_id).delete()
            s.commit()
            s.close()
            _cleanup_signals([sku_id])


class TestCostAutoResolve:
    def test_resolves_when_margin_recovers(self):
        from engine.signal_emitters import emit_cost_signals
        uid = _unique()
        sku_id = f"SKU-ARCO-{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.FactCostDaily(
                date=today, sku_id=sku_id, sku_name=f"Test {uid}",
                net_margin_pct=-3.0, selling_price=10.0, total_cost=10.3,
                total_direct_cost=8.0, total_indirect_cost=2.3,
                cost_signal="MARGIN_CRITICAL")
            s.add(row)
            s.commit()

            emit_cost_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "below_break_even").status == "active"

            # Verhelpen: marge hersteld boven de drempel
            row.net_margin_pct = 12.0
            s.commit()

            emit_cost_signals(s)
            s.commit()
            assert _signal_for(s, sku_id, "below_break_even").status == "resolved"
        finally:
            s.query(models.FactCostDaily).filter_by(sku_id=sku_id).delete()
            s.commit()
            s.close()
            _cleanup_signals([sku_id])


class TestEconomicAutoResolve:
    def test_resolves_when_source_expires(self):
        from engine.signal_emitters import emit_cost_signals
        uid = _unique()
        code = f"econ_test_{uid}"
        today = date_type.today()

        s = SessionLocal()
        try:
            row = models.FactEconomicSignalDaily(
                date=today, signal_type="RAW_MATERIAL",
                signal_name=f"Test economisch signaal {uid}",
                severity="HOOG", severity_score=0.7,
                current_value=120.0, baseline_value=100.0, change_pct=20.0,
                signal_code=code.upper(), description_nl="Grondstofprijs stijgt.",
                recommended_action_nl="Inkoop vervroegen",
                margin_impact_pct=-2.0,
                valid_until=today + timedelta(days=7))
            s.add(row)
            s.commit()

            emit_cost_signals(s)
            s.commit()
            sig = s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.signal_type == code,
                models.IntelligenceSignal.engine == "economic",
            ).order_by(models.IntelligenceSignal.id.desc()).first()
            assert sig is not None and sig.status == "active"

            # Verhelpen: bronrij niet meer geldig
            row.valid_until = today - timedelta(days=1)
            s.commit()

            emit_cost_signals(s)
            s.commit()
            s.refresh(sig)
            assert sig.status == "resolved"
        finally:
            s.query(models.FactEconomicSignalDaily).filter_by(
                signal_code=code.upper()).delete()
            s.query(models.IntelligenceSignal).filter_by(signal_type=code).delete()
            s.commit()
            s.close()

    def test_empty_source_does_not_resolve(self):
        """Lege/onbeschikbare economische bron (bijv. mislukte ingest) mag
        actieve economische signalen NIET resolven."""
        from engine.signal_emitters import emit_cost_signals
        uid = _unique()
        code = f"econ_empty_{uid}"

        s = SessionLocal()
        try:
            sig = publish_signal(
                s, engine="economic", signal_type=code,
                entity_type="shop", entity_id="1",
                explanation="Economisch signaal.", evidence={"v": 1},
                sources=["t"])
            s.commit()
            sig_id = sig.id

            # Simuleer een lege brontabel binnen een niet-gecommitte
            # transactie: de emitter ziet géén economische rijen.
            s.query(models.FactEconomicSignalDaily).delete()
            emit_cost_signals(s)
            status_in_txn = s.query(models.IntelligenceSignal).get(sig_id).status
            s.rollback()  # herstel de echte bronrijen

            assert status_in_txn == "active", (
                "Een lege economische bron is geen bewijs dat de conditie "
                "verholpen is; het signaal moet actief blijven")
        finally:
            s.rollback()
            s.query(models.IntelligenceSignal).filter_by(signal_type=code).delete()
            s.commit()
            s.close()


# ══════════════════════════════════════════════════════════════════════════════
# Engines die rechtstreeks publiceren: forecast, promotie, basket, loyaliteit
# ══════════════════════════════════════════════════════════════════════════════

def _make_shop(s, prefix):
    shop = models.DimShop(shop_code=f"{prefix}{_unique()[:6]}",
                          name=f"AR {prefix} shop", active=True)
    s.add(shop)
    s.flush()
    return shop.id


class TestForecastAutoResolve:
    def test_stock_risk_resolves_when_stock_replenished(self):
        from engine.forecast_engine import run_forecast_engine
        uid = _unique()
        sku_id = f"SKU-ARFC-{uid}"
        today = date_type.today()

        s = SessionLocal()
        shop_id_test = None
        try:
            shop_id_test = _make_shop(s, "ARFC")
            s.add(models.DimProduct(sku_id=sku_id, product_name=f"Forecast {uid}",
                                    shop_id=shop_id_test, stock_quantity=10,
                                    current_price=10.0, cost_price=5.0))
            for i in range(20):
                s.add(models.FactSalesDaily(
                    date=today - timedelta(days=i + 1), sku_id=sku_id,
                    shop_id=shop_id_test, units_sold=5,
                    revenue=50.0, cost=25.0, margin=25.0))
            s.commit()

            run_forecast_engine(s, shop_id=shop_id_test)
            sig = _signal_for(s, sku_id, "stock_risk")
            assert sig is not None and sig.status == "active"

            # Verhelpen: voorraad ruimschoots aangevuld
            s.query(models.DimProduct).filter_by(sku_id=sku_id).update(
                {"stock_quantity": 100000})
            s.commit()

            run_forecast_engine(s, shop_id=shop_id_test)
            assert _signal_for(s, sku_id, "stock_risk").status == "resolved"

            # Idempotent: nog een run publiceert niet opnieuw
            run_forecast_engine(s, shop_id=shop_id_test)
            cnt = s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == sku_id,
                models.IntelligenceSignal.signal_type == "stock_risk").count()
            assert cnt == 1
        finally:
            s.rollback()
            s.query(models.FactForecastDaily).filter_by(sku_id=sku_id).delete()
            s.query(models.FactSalesDaily).filter_by(sku_id=sku_id).delete()
            s.query(models.DimProduct).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_unevaluable_sku_not_resolved_in_mixed_run(self):
        """Regressie: een SKU met te weinig historie (conditie niet
        evalueerbaar) mag niet worden geresolved, ook al konden andere SKU's
        in dezelfde run wél worden geëvalueerd."""
        from engine.forecast_engine import run_forecast_engine
        uid = _unique()
        sku_ok = f"SKU-ARFCMX-{uid}"     # voldoende historie, geen risico
        sku_thin = f"SKU-ARFCTH-{uid}"   # te weinig historie
        today = date_type.today()

        s = SessionLocal()
        shop_id_test = None
        try:
            shop_id_test = _make_shop(s, "ARFM")
            s.add(models.DimProduct(sku_id=sku_ok, product_name=f"OK {uid}",
                                    shop_id=shop_id_test, stock_quantity=100000,
                                    current_price=10.0, cost_price=5.0))
            s.add(models.DimProduct(sku_id=sku_thin, product_name=f"Dun {uid}",
                                    shop_id=shop_id_test, stock_quantity=10,
                                    current_price=10.0, cost_price=5.0))
            for i in range(20):
                s.add(models.FactSalesDaily(
                    date=today - timedelta(days=i + 1), sku_id=sku_ok,
                    shop_id=shop_id_test, units_sold=5,
                    revenue=50.0, cost=25.0, margin=25.0))
            # Te weinig historie voor sku_thin (< min_history_days)
            for i in range(3):
                s.add(models.FactSalesDaily(
                    date=today - timedelta(days=i + 1), sku_id=sku_thin,
                    shop_id=shop_id_test, units_sold=5,
                    revenue=50.0, cost=25.0, margin=25.0))
            sig = publish_signal(
                s, engine="forecast_risk", signal_type="stock_risk",
                entity_type="sku", entity_id=sku_thin,
                explanation="Voorraadrisico.", evidence={"v": 1}, sources=["t"],
                shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            run_forecast_engine(s, shop_id=shop_id_test)
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Een niet-evalueerbare SKU mag in een gemengde run niet "
                "worden geresolved")
        finally:
            s.rollback()
            for sk in (sku_ok, sku_thin):
                s.query(models.FactForecastDaily).filter_by(sku_id=sk).delete()
                s.query(models.FactSalesDaily).filter_by(sku_id=sk).delete()
                s.query(models.DimProduct).filter_by(sku_id=sk).delete()
                s.query(models.IntelligenceSignal).filter_by(entity_id=sk).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_missing_source_data_keeps_competitor_and_supplier_signals(self):
        """Regressie: competitor_risk en supplier_risk mogen niet resolven
        wanneer de bijbehorende brondata (competitiescore resp.
        leveranciersrecord) ontbreekt — ook al is de verkoophistorie
        evalueerbaar. Een cross-shop competitiescore telt niet als eigen
        evaluatie."""
        from engine.forecast_engine import run_forecast_engine
        uid = _unique()
        sku = f"SKU-ARFSRC-{uid}"
        today = date_type.today()

        s = SessionLocal()
        shop_id_test = None
        other_shop_id = None
        try:
            shop_id_test = _make_shop(s, "ARFS")
            other_shop_id = _make_shop(s, "ARFO")
            s.add(models.DimProduct(sku_id=sku, product_name=f"Src {uid}",
                                    shop_id=shop_id_test, stock_quantity=100000,
                                    current_price=10.0, cost_price=5.0))
            for i in range(20):
                s.add(models.FactSalesDaily(
                    date=today - timedelta(days=i + 1), sku_id=sku,
                    shop_id=shop_id_test, units_sold=5,
                    revenue=50.0, cost=25.0, margin=25.0))
            # Alleen een ANDERE shop heeft een competitiescore voor deze SKU
            s.add(models.SkuCompetitionScore(
                shop_id=other_shop_id, sku_id=sku, run_date=today,
                price_index=0.9))
            sig_comp = publish_signal(
                s, engine="forecast_risk", signal_type="competitor_risk",
                entity_type="sku", entity_id=sku,
                explanation="Concurrentierisico.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            sig_sup = publish_signal(
                s, engine="forecast_risk", signal_type="supplier_risk",
                entity_type="sku", entity_id=sku,
                explanation="Leveranciersrisico.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            s.commit()
            comp_id, sup_id = sig_comp.id, sig_sup.id

            run_forecast_engine(s, shop_id=shop_id_test)
            assert s.query(models.IntelligenceSignal).get(comp_id).status == "active", (
                "competitor_risk mag niet resolven zonder eigen (shop-"
                "gescopeerde) competitiescore")
            assert s.query(models.IntelligenceSignal).get(sup_id).status == "active", (
                "supplier_risk mag niet resolven zonder leveranciersrecord")
        finally:
            s.rollback()
            s.query(models.FactForecastDaily).filter_by(sku_id=sku).delete()
            s.query(models.FactSalesDaily).filter_by(sku_id=sku).delete()
            s.query(models.SkuCompetitionScore).filter_by(sku_id=sku).delete()
            s.query(models.DimProduct).filter_by(sku_id=sku).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku).delete()
            for shp in (shop_id_test, other_shop_id):
                if shp:
                    s.query(models.IntelligenceSignal).filter_by(
                        shop_id=shp).delete()
                    s.query(models.DimShop).filter_by(id=shp).delete()
            s.commit()
            s.close()

    def test_no_sales_data_does_not_resolve(self):
        """Een run zonder enige verkoophistorie mag risicosignalen niet resolven."""
        from engine.forecast_engine import run_forecast_engine
        uid = _unique()
        sku_id = f"SKU-ARFCND-{uid}"

        s = SessionLocal()
        shop_id_test = None
        try:
            shop_id_test = _make_shop(s, "ARFN")
            sig = publish_signal(
                s, engine="forecast_risk", signal_type="stock_risk",
                entity_type="sku", entity_id=sku_id,
                explanation="Voorraadrisico.", evidence={"v": 1}, sources=["t"],
                shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            run_forecast_engine(s, shop_id=shop_id_test)  # geen sales in deze shop
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Geen verkoopdata is geen bewijs dat het risico verholpen is")
        finally:
            s.rollback()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()


class TestPromotionAutoResolve:
    def test_loss_making_resolves_when_verdict_improves(self):
        from engine.promotion_engine import run_promotion_engine
        uid = _unique()
        sku_id = f"SKU-ARPM-{uid}"
        today = date_type.today()
        p_start = today - timedelta(days=10)
        p_end = today - timedelta(days=4)

        s = SessionLocal()
        shop_id_test = None
        promo_id = None
        try:
            shop_id_test = _make_shop(s, "ARPM")
            s.add(models.DimProduct(sku_id=sku_id, product_name=f"Promo {uid}",
                                    shop_id=shop_id_test, category=f"cat-{uid}",
                                    current_price=10.0, cost_price=5.0,
                                    stock_quantity=1000))
            promo = models.Promotion(sku_id=sku_id, promotion_type="percentage_off",
                                     discount_value=50.0, start_date=p_start,
                                     end_date=p_end)
            s.add(promo)
            # Baseline: gezonde verkoop met marge
            b_end = p_start - timedelta(days=1)
            for i in range(7):
                s.add(models.FactSalesDaily(
                    date=b_end - timedelta(days=i), sku_id=sku_id,
                    shop_id=shop_id_test, units_sold=10,
                    revenue=100.0, cost=50.0, margin=50.0))
            # Tijdens promo: zelfde afzet, marge weggegeven → verliesgevend
            d = p_start
            while d <= p_end:
                s.add(models.FactSalesDaily(
                    date=d, sku_id=sku_id, shop_id=shop_id_test,
                    units_sold=10, revenue=50.0, cost=50.0, margin=0.0))
                d += timedelta(days=1)
            s.commit()
            promo_id = promo.id

            run_promotion_engine(s, shop_id=shop_id_test)
            sig = _signal_for(s, sku_id, "promotion_loss_making")
            assert sig is not None and sig.status == "active"

            # Verhelpen: promo-marge blijkt na datacorrectie toch positief
            s.query(models.FactSalesDaily).filter(
                models.FactSalesDaily.sku_id == sku_id,
                models.FactSalesDaily.date >= p_start,
            ).update({"margin": 60.0}, synchronize_session=False)
            s.commit()

            run_promotion_engine(s, shop_id=shop_id_test)
            assert _signal_for(s, sku_id, "promotion_loss_making").status == "resolved"
        finally:
            s.rollback()
            if promo_id:
                s.query(models.FactPromotionEffect).filter_by(
                    promotion_id=promo_id).delete()
                s.query(models.Promotion).filter_by(id=promo_id).delete()
            s.query(models.FactSalesDaily).filter_by(sku_id=sku_id).delete()
            s.query(models.DimProduct).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_unanalyzable_promo_sku_not_resolved_in_mixed_run(self):
        """Regressie: een SKU waarvan de promotie niet analyseerbaar is (geen
        verkoopdata) mag niet worden geresolved, ook al kon een andere
        promotie in dezelfde run wél worden geanalyseerd."""
        from engine.promotion_engine import run_promotion_engine
        uid = _unique()
        sku_ok = f"SKU-ARPMMX-{uid}"
        sku_nd = f"SKU-ARPMND2-{uid}"
        today = date_type.today()
        p_start = today - timedelta(days=10)
        p_end = today - timedelta(days=4)

        s = SessionLocal()
        shop_id_test = None
        promo_ids = []
        try:
            shop_id_test = _make_shop(s, "ARPX")
            for sk in (sku_ok, sku_nd):
                s.add(models.DimProduct(sku_id=sk, product_name=f"P {sk}",
                                        shop_id=shop_id_test,
                                        category=f"cat-{sk}",
                                        current_price=10.0, cost_price=5.0))
                promo = models.Promotion(sku_id=sk,
                                         promotion_type="percentage_off",
                                         discount_value=50.0,
                                         start_date=p_start, end_date=p_end)
                s.add(promo)
                s.flush()
                promo_ids.append(promo.id)
            # Alleen sku_ok krijgt analyseerbare verkoopdata
            b_end = p_start - timedelta(days=1)
            for i in range(7):
                s.add(models.FactSalesDaily(
                    date=b_end - timedelta(days=i), sku_id=sku_ok,
                    shop_id=shop_id_test, units_sold=10,
                    revenue=100.0, cost=50.0, margin=50.0))
            d = p_start
            while d <= p_end:
                s.add(models.FactSalesDaily(
                    date=d, sku_id=sku_ok, shop_id=shop_id_test,
                    units_sold=10, revenue=50.0, cost=50.0, margin=0.0))
                d += timedelta(days=1)
            sig = publish_signal(
                s, engine="promotion", signal_type="promotion_loss_making",
                entity_type="sku", entity_id=sku_nd,
                explanation="Verliesgevende promotie.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            run_promotion_engine(s, shop_id=shop_id_test)
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Een SKU met niet-analyseerbare promotie mag in een gemengde "
                "run niet worden geresolved")
            # De analyseerbare SKU levert wél een vers signaal op
            assert _signal_for(s, sku_ok, "promotion_loss_making").status == "active"
        finally:
            s.rollback()
            for pid in promo_ids:
                s.query(models.FactPromotionEffect).filter_by(
                    promotion_id=pid).delete()
                s.query(models.Promotion).filter_by(id=pid).delete()
            for sk in (sku_ok, sku_nd):
                s.query(models.FactSalesDaily).filter_by(sku_id=sk).delete()
                s.query(models.DimProduct).filter_by(sku_id=sk).delete()
                s.query(models.IntelligenceSignal).filter_by(entity_id=sk).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_no_analyzable_promotions_does_not_resolve(self):
        """Promoties zonder analyseerbare verkoopdata mogen niets resolven."""
        from engine.promotion_engine import run_promotion_engine
        uid = _unique()
        sku_id = f"SKU-ARPMND-{uid}"
        today = date_type.today()

        s = SessionLocal()
        shop_id_test = None
        promo_id = None
        try:
            shop_id_test = _make_shop(s, "ARPN")
            s.add(models.DimProduct(sku_id=sku_id, product_name=f"Promo {uid}",
                                    shop_id=shop_id_test, current_price=10.0,
                                    cost_price=5.0))
            promo = models.Promotion(sku_id=sku_id, promotion_type="percentage_off",
                                     discount_value=10.0,
                                     start_date=today - timedelta(days=10),
                                     end_date=today - timedelta(days=4))
            s.add(promo)
            sig = publish_signal(
                s, engine="promotion", signal_type="promotion_loss_making",
                entity_type="sku", entity_id=sku_id,
                explanation="Verliesgevende promotie.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            s.commit()
            promo_id = promo.id
            sig_id = sig.id

            # Geen verkoopdata → analyzed == 0 → geen resolve
            run_promotion_engine(s, shop_id=shop_id_test)
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Zonder analyseerbare data mag een promotiesignaal niet resolven")
        finally:
            s.rollback()
            if promo_id:
                s.query(models.FactPromotionEffect).filter_by(
                    promotion_id=promo_id).delete()
                s.query(models.Promotion).filter_by(id=promo_id).delete()
            s.query(models.DimProduct).filter_by(sku_id=sku_id).delete()
            s.query(models.IntelligenceSignal).filter_by(entity_id=sku_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()


class TestBasketAutoResolve:
    def test_resolves_when_association_drops_out(self):
        from engine.basket_engine import run_basket_engine
        uid = _unique()
        sku_a = f"SKU-ARBA-{uid}"
        sku_b = f"SKU-ARBB-{uid}"
        sku_c = f"SKU-ARBC-{uid}"

        s = SessionLocal()
        shop_id_test = None
        try:
            shop_id_test = _make_shop(s, "ARBK")
            for sk, nm in [(sku_a, "A"), (sku_b, "B"), (sku_c, "C")]:
                s.add(models.DimProduct(sku_id=sk, product_name=f"Basket {nm} {uid}",
                                        shop_id=shop_id_test, current_price=20.0,
                                        cost_price=10.0))
            s.add(models.FactBasketAffinity(
                shop_id=shop_id_test, sku_id_a=sku_a, sku_id_b=sku_b,
                affinity_score=0.95, co_purchase_count=40))
            s.commit()

            run_basket_engine(s, shop_id=shop_id_test)
            sig = _signal_for(s, sku_a, "strong_product_association")
            assert sig is not None and sig.status == "active"

            # Verhelpen: de associatie a→b verdwijnt; andere data blijft
            s.query(models.FactBasketAffinity).filter_by(
                sku_id_a=sku_a, shop_id=shop_id_test).delete()
            s.add(models.FactBasketAffinity(
                shop_id=shop_id_test, sku_id_a=sku_c, sku_id_b=sku_b,
                affinity_score=0.9, co_purchase_count=30))
            s.commit()

            run_basket_engine(s, shop_id=shop_id_test)
            assert _signal_for(s, sku_a, "strong_product_association").status == "resolved"

            # Geen data betekent geen resolve: bron leeg → c-signaal blijft actief
            sig_c = _signal_for(s, sku_c, "strong_product_association")
            assert sig_c is not None and sig_c.status == "active"
            s.query(models.FactBasketAffinity).filter_by(
                shop_id=shop_id_test).delete()
            s.commit()
            run_basket_engine(s, shop_id=shop_id_test)  # early return: no_data
            assert _signal_for(s, sku_c, "strong_product_association").status == "active", (
                "Een lege basket-bron mag associatiesignalen niet resolven")
        finally:
            s.rollback()
            for sk in (sku_a, sku_b, sku_c):
                s.query(models.FactBasketAffinity).filter_by(sku_id_a=sk).delete()
                s.query(models.BasketAssociation).filter_by(antecedent_sku=sk).delete()
                s.query(models.DimProduct).filter_by(sku_id=sk).delete()
                s.query(models.IntelligenceSignal).filter_by(entity_id=sk).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()


class TestLoyaltyAutoResolve:
    def _member(self, s, shop_id_test, uid):
        m = models.LoyaltyMember(
            shop_id=shop_id_test,
            pseudonymous_customer_id=f"CUST-ARLO-{uid}",
            joined_at=date_type.today() - timedelta(days=100),
            tier_code="bronze", status="active")
        s.add(m)
        s.flush()
        return m

    def test_nba_and_fraud_resolve_when_fixed(self):
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=500)  # geïsoleerde run

        s = SessionLocal()
        shop_id_test = None
        member_id = None
        try:
            shop_id_test = _make_shop(s, "ARLO")
            m = self._member(s, shop_id_test, uid)
            member_id = m.id
            cust = m.pseudonymous_customer_id
            score = models.CustomerValueScore(
                shop_id=shop_id_test, member_id=member_id, run_date=run_date,
                clv_estimate=999999.0, churn_risk=0.8, retention_probability=0.2,
                value_segment="at_risk", confidence=0.7,
                next_best_action="winback_voucher", nba_reason="Churnrisico hoog.",
                nba_expected_value=50.0, nba_alternative="prijsverlaging",
                nba_alternative_cost=80.0)
            s.add(score)
            fraud = models.LoyaltyFraudSignal(
                shop_id=shop_id_test, member_id=member_id, run_date=run_date,
                fraud_type="abnormal_earn_rate", severity="high", score=0.9,
                explanation="Abnormaal spaargedrag.", evidence={"v": 1},
                status="open")
            s.add(fraud)
            s.commit()

            publish_signals(s, run_date)
            s.commit()
            assert _signal_for(s, cust, f"nba_winback_voucher").status == "active"
            assert _signal_for(s, cust, "fraud_abnormal_earn_rate").status == "active"

            # Verhelpen: geen actie meer nodig, fraudemelding beoordeeld
            score.next_best_action = "no_action"
            fraud.status = "reviewed"
            s.commit()

            publish_signals(s, run_date)
            s.commit()
            assert _signal_for(s, cust, "nba_winback_voucher").status == "resolved"
            assert _signal_for(s, cust, "fraud_abnormal_earn_rate").status == "resolved"
        finally:
            s.rollback()
            if member_id:
                s.query(models.CustomerValueScore).filter_by(member_id=member_id).delete()
                s.query(models.LoyaltyFraudSignal).filter_by(member_id=member_id).delete()
                s.query(models.LoyaltyMember).filter_by(id=member_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_liability_signal_resolves_when_no_outstanding_points(self):
        """Regressie: een actief loyalty_liability_level-shopsignaal resolvet
        zodra de shop geen uitstaande punten meer heeft."""
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=505)

        s = SessionLocal()
        shop_id_test = None
        member_id = None
        try:
            shop_id_test = _make_shop(s, "ARLL")
            # Lid zonder punten: shop is loyalty-actief maar zonder liability
            m = self._member(s, shop_id_test, uid)
            member_id = m.id
            sig = publish_signal(
                s, engine="loyalty", signal_type="loyalty_liability_level",
                entity_type="shop", entity_id=str(shop_id_test),
                explanation="Openstaande verplichting.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            publish_signals(s, run_date)
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "resolved", (
                "Zonder uitstaande punten moet het liability-signaal "
                "auto-resolven")
        finally:
            s.rollback()
            s.query(models.LoyaltyWallet).filter_by(
                member_id=member_id).delete() if member_id else None
            if member_id:
                s.query(models.LoyaltyMember).filter_by(id=member_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_reviewed_fraud_on_unscored_member_resolves(self):
        """Regressie: een gereviewde fraudemelding van een lid zónder
        klantwaardescore moet tóch auto-resolven — de fraudeconditie is
        immers beoordeeld en verholpen, los van de scoring."""
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=504)

        s = SessionLocal()
        shop_id_test = None
        member_id = None
        fraud_id = None
        try:
            shop_id_test = _make_shop(s, "ARLF")
            m = self._member(s, shop_id_test, uid)
            member_id = m.id
            fraud = models.LoyaltyFraudSignal(
                shop_id=shop_id_test, member_id=m.id, run_date=run_date,
                fraud_type="velocity", severity="high", score=0.9,
                explanation="Verdacht inwisselpatroon.", status="open",
                evidence={"v": 1})
            s.add(fraud)
            s.flush()
            fraud_id = fraud.id
            sig = publish_signal(
                s, engine="loyalty", signal_type="fraud_velocity",
                entity_type="customer",
                entity_id=m.pseudonymous_customer_id,
                explanation="Fraudeverdenking.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            # Melding wordt gereviewd/gesloten — geen open fraude meer
            fraud.status = "reviewed"
            s.commit()

            publish_signals(s, run_date)
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "resolved", (
                "Een gereviewde fraudemelding moet ook zonder "
                "klantwaardescore auto-resolven")
        finally:
            s.rollback()
            if fraud_id:
                s.query(models.LoyaltyFraudSignal).filter_by(id=fraud_id).delete()
            if member_id:
                s.query(models.LoyaltyMember).filter_by(id=member_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_unscored_member_not_resolved_in_mixed_run(self):
        """Regressie: een lid zonder score in deze run (niet geëvalueerd) mag
        niet worden geresolved, ook al zijn andere leden in dezelfde shop
        wél gescoord."""
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=503)

        s = SessionLocal()
        shop_id_test = None
        member_ids = []
        try:
            shop_id_test = _make_shop(s, "ARLM")
            m_scored = self._member(s, shop_id_test, f"{uid}-a")
            member_ids.append(m_scored.id)
            s.add(models.CustomerValueScore(
                shop_id=shop_id_test, member_id=m_scored.id, run_date=run_date,
                clv_estimate=100.0, value_segment="mid_value", confidence=0.6,
                next_best_action="no_action"))
            m_unscored = models.LoyaltyMember(
                shop_id=shop_id_test,
                pseudonymous_customer_id=f"CUST-ARLM-{uid}-b",
                joined_at=date_type.today() - timedelta(days=100),
                tier_code="bronze", status="active")
            s.add(m_unscored)
            s.flush()
            member_ids.append(m_unscored.id)
            sig = publish_signal(
                s, engine="loyalty", signal_type="nba_winback_voucher",
                entity_type="customer",
                entity_id=m_unscored.pseudonymous_customer_id,
                explanation="NBA.", evidence={"v": 1}, sources=["t"],
                shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            publish_signals(s, run_date)
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Een niet-gescoord lid mag in een gemengde run niet worden "
                "geresolved")
        finally:
            s.rollback()
            if member_ids:
                s.query(models.CustomerValueScore).filter(
                    models.CustomerValueScore.member_id.in_(member_ids)).delete(
                    synchronize_session=False)
                s.query(models.LoyaltyMember).filter(
                    models.LoyaltyMember.id.in_(member_ids)).delete(
                    synchronize_session=False)
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_member_outside_publication_top_not_resolved(self):
        """Regressie: een lid met een bestaand NBA-signaal dat door ranking
        buiten de top-50-publicatielimiet valt maar nog steeds een geldige
        actie heeft (next_best_action != no_action) mag NIET worden
        geresolved."""
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=502)  # geïsoleerde run

        s = SessionLocal()
        shop_id_test = None
        member_ids = []
        cust_low = None
        try:
            shop_id_test = _make_shop(s, "ARLT")
            # Laag-CLV-lid met bestaand actief NBA-signaal en nog geldige actie
            m_low = self._member(s, shop_id_test, uid)
            member_ids.append(m_low.id)
            cust_low = m_low.pseudonymous_customer_id
            s.add(models.CustomerValueScore(
                shop_id=shop_id_test, member_id=m_low.id, run_date=run_date,
                clv_estimate=1.0, value_segment="low_value", confidence=0.6,
                next_best_action="winback_voucher", nba_reason="Actie geldig.",
                nba_expected_value=5.0, nba_alternative="prijsverlaging",
                nba_alternative_cost=8.0))
            sig = publish_signal(
                s, engine="loyalty", signal_type="nba_winback_voucher",
                entity_type="customer", entity_id=cust_low,
                explanation="Bestaand NBA-signaal.", evidence={"v": 1},
                sources=["t"], shop_id=shop_id_test)
            # 50 leden met hogere CLV duwen het lid uit de publicatie-top
            for i in range(50):
                m = models.LoyaltyMember(
                    shop_id=shop_id_test,
                    pseudonymous_customer_id=f"CUST-ARLT-{uid}-{i}",
                    joined_at=date_type.today() - timedelta(days=100),
                    tier_code="bronze", status="active")
                s.add(m)
                s.flush()
                member_ids.append(m.id)
                s.add(models.CustomerValueScore(
                    shop_id=shop_id_test, member_id=m.id, run_date=run_date,
                    clv_estimate=100000.0 + i, value_segment="high_value",
                    confidence=0.8, next_best_action="loyalty_bonus",
                    nba_reason="Hoog CLV.", nba_expected_value=50.0,
                    nba_alternative="prijsverlaging", nba_alternative_cost=80.0))
            s.commit()
            sig_id = sig.id

            publish_signals(s, run_date)
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Een lid dat buiten de top-50-publicatie valt maar nog een "
                "geldige NBA heeft mag niet worden geresolved")
        finally:
            s.rollback()
            if member_ids:
                s.query(models.CustomerValueScore).filter(
                    models.CustomerValueScore.member_id.in_(member_ids)).delete(
                    synchronize_session=False)
                s.query(models.LoyaltyMember).filter(
                    models.LoyaltyMember.id.in_(member_ids)).delete(
                    synchronize_session=False)
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()

    def test_no_scores_for_run_does_not_resolve(self):
        """Een run zonder klantwaardescores voor deze shop mag NBA/fraude-
        signalen niet resolven (scoring niet gedraaid ≠ conditie verholpen)."""
        from engine.loyalty_intelligence import publish_signals
        uid = _unique()
        run_date = date_type.today() - timedelta(days=501)

        s = SessionLocal()
        shop_id_test = None
        member_id = None
        try:
            shop_id_test = _make_shop(s, "ARLN")
            m = self._member(s, shop_id_test, uid)
            member_id = m.id
            cust = m.pseudonymous_customer_id
            sig = publish_signal(
                s, engine="loyalty", signal_type="nba_winback_voucher",
                entity_type="customer", entity_id=cust,
                explanation="NBA.", evidence={"v": 1}, sources=["t"],
                shop_id=shop_id_test)
            s.commit()
            sig_id = sig.id

            publish_signals(s, run_date)  # geen scores voor deze run_date/shop
            s.commit()
            refreshed = s.query(models.IntelligenceSignal).get(sig_id)
            assert refreshed.status == "active", (
                "Zonder scores voor deze shop mag niets worden geresolved")
        finally:
            s.rollback()
            if member_id:
                s.query(models.LoyaltyMember).filter_by(id=member_id).delete()
            if shop_id_test:
                s.query(models.IntelligenceSignal).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.LoyaltyExpiryPolicy).filter_by(
                    shop_id=shop_id_test).delete()
                s.query(models.DimShop).filter_by(id=shop_id_test).delete()
            s.commit()
            s.close()
