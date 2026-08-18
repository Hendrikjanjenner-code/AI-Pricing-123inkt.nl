"""
Unit- en integratietests voor signal_publisher.py en signal_emitters.py.

Doelstellingen (taak #24):
- publish_signal: dedupe/supersede, validatiefouten, valid_until
- expire_stale_signals: markeer verlopen signalen
- Per emitter: kleine gefixte datasets → signals bevatten explanation,
  evidence, confidence, model_version
- emit_all_signals: een emitter-fout crasht de engine-run NIET

Alle testdata wordt na afloop opgeruimd (rollback-fixtures of expliciete
delete). De tests draaien tegen de dev-database (SessionLocal).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from datetime import date as date_type
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine.signal_publisher import publish_signal, expire_stale_signals


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique() -> str:
    return uuid.uuid4().hex[:12]


MINIMAL_KWARGS = dict(
    engine="test_engine",
    signal_type="test_signal",
    entity_type="sku",
    entity_id="SKU-TEST-001",
    explanation="Dit is een testverklaring.",
    evidence={"score": 0.9},
    sources=["test_table"],
    confidence=0.75,
    model_version="test-v1",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """Een verse DB-sessie; rollback na elke test zodat geen data achterblijft."""
    s = SessionLocal()
    yield s
    try:
        s.rollback()
        s.close()
    except Exception:
        pass


@pytest.fixture()
def clean_db():
    """Sessie die na de test via expliciete delete opruimt.
    Gebruik dit als de test commit() aanroept (rollback-only werkt dan niet)."""
    s = SessionLocal()
    created_ids: list[int] = []
    yield s, created_ids
    s.close()
    cleanup = SessionLocal()
    try:
        if created_ids:
            cleanup.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.id.in_(created_ids)
            ).delete(synchronize_session=False)
            cleanup.commit()
    finally:
        cleanup.close()


# ══════════════════════════════════════════════════════════════════════════════
# publish_signal — validatiefouten
# ══════════════════════════════════════════════════════════════════════════════

class TestPublishSignalValidation:
    def test_requires_explanation(self, db):
        with pytest.raises(ValueError, match="explanation"):
            publish_signal(db, **{**MINIMAL_KWARGS, "explanation": ""})

    def test_requires_explanation_not_whitespace(self, db):
        with pytest.raises(ValueError, match="explanation"):
            publish_signal(db, **{**MINIMAL_KWARGS, "explanation": "   "})

    def test_requires_evidence(self, db):
        with pytest.raises(ValueError, match="evidence"):
            publish_signal(db, **{**MINIMAL_KWARGS, "evidence": {}})

    def test_requires_sources(self, db):
        with pytest.raises(ValueError, match="sources"):
            publish_signal(db, **{**MINIMAL_KWARGS, "sources": []})

    def test_invalid_severity_falls_back_to_info(self, db):
        sig = publish_signal(db, **{**MINIMAL_KWARGS, "severity": "extreme"})
        assert sig.severity == "info"

    def test_valid_severities_accepted(self, db):
        for sev in ("info", "low", "medium", "high", "critical"):
            sig = publish_signal(
                db, **{**MINIMAL_KWARGS,
                       "entity_id": f"SKU-SEV-{sev}-{_unique()}",
                       "severity": sev}
            )
            assert sig.severity == sev


# ══════════════════════════════════════════════════════════════════════════════
# publish_signal — correcte velden
# ══════════════════════════════════════════════════════════════════════════════

class TestPublishSignalFields:
    def test_signal_has_required_fields(self, db):
        sig = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}"})
        db.flush()  # autoflush=False — flush om het object persistent te maken
        db.refresh(sig)
        assert sig.explanation == MINIMAL_KWARGS["explanation"]
        assert sig.evidence == MINIMAL_KWARGS["evidence"]
        assert sig.sources == MINIMAL_KWARGS["sources"]
        assert sig.confidence == MINIMAL_KWARGS["confidence"]
        assert sig.model_version == MINIMAL_KWARGS["model_version"]
        assert sig.status == "active"

    def test_valid_until_defaults_to_7_days(self, db):
        before = datetime.utcnow()
        sig = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}"})
        after = datetime.utcnow()
        assert sig.valid_until is not None
        expected_min = before + timedelta(days=7)
        expected_max = after + timedelta(days=7)
        assert expected_min <= sig.valid_until <= expected_max

    def test_valid_until_explicit_is_respected(self, db):
        explicit = datetime(2099, 1, 1)
        sig = publish_signal(
            db, **{**MINIMAL_KWARGS,
                   "entity_id": f"SKU-{_unique()}",
                   "valid_until": explicit}
        )
        assert sig.valid_until == explicit

    def test_valid_days_custom(self, db):
        before = datetime.utcnow()
        sig = publish_signal(
            db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}", "valid_days": 30}
        )
        after = datetime.utcnow()
        assert before + timedelta(days=30) <= sig.valid_until <= after + timedelta(days=30)

    def test_confidence_clamped_above_1(self, db):
        sig = publish_signal(
            db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}", "confidence": 5.0}
        )
        assert sig.confidence == 1.0

    def test_confidence_clamped_below_0(self, db):
        sig = publish_signal(
            db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}", "confidence": -0.5}
        )
        assert sig.confidence == 0.0

    def test_dedupe_key_format(self, db):
        eid = f"SKU-{_unique()}"
        sig = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": eid})
        expected_key = f"{MINIMAL_KWARGS['engine']}:{MINIMAL_KWARGS['signal_type']}:{MINIMAL_KWARGS['entity_type']}:{eid}"
        assert sig.dedupe_key == expected_key

    def test_explanation_is_stripped(self, db):
        sig = publish_signal(
            db, **{**MINIMAL_KWARGS,
                   "entity_id": f"SKU-{_unique()}",
                   "explanation": "  Ruimte vooraan en achteraan.  "}
        )
        assert sig.explanation == "Ruimte vooraan en achteraan."


# ══════════════════════════════════════════════════════════════════════════════
# publish_signal — dedupe / supersede
# ══════════════════════════════════════════════════════════════════════════════

class TestPublishSignalDedupe:
    def test_supersedes_existing_active_signal(self, clean_db):
        db, ids = clean_db
        eid = f"SKU-DEDUP-{_unique()}"
        kwargs = {**MINIMAL_KWARGS, "entity_id": eid}

        first = publish_signal(db, **kwargs)
        db.flush()
        ids.append(first.id)

        second = publish_signal(db, **kwargs)
        db.flush()
        ids.append(second.id)

        # Na de flush moet het eerste signaal superseded zijn
        db.refresh(first)
        assert first.status == "superseded", "Eerste signaal moet superseded zijn"
        assert second.status == "active"

    def test_different_entity_id_no_supersede(self, clean_db):
        db, ids = clean_db
        eid_a = f"SKU-A-{_unique()}"
        eid_b = f"SKU-B-{_unique()}"
        sig_a = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": eid_a})
        db.flush()
        ids.append(sig_a.id)
        sig_b = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": eid_b})
        db.flush()
        ids.append(sig_b.id)
        db.refresh(sig_a)
        assert sig_a.status == "active", "Signaal met ander entity_id mag NIET worden superseded"

    def test_different_signal_type_no_supersede(self, clean_db):
        db, ids = clean_db
        eid = f"SKU-TYPE-{_unique()}"
        sig_a = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": eid, "signal_type": "type_alpha"})
        db.flush()
        ids.append(sig_a.id)
        sig_b = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": eid, "signal_type": "type_beta"})
        db.flush()
        ids.append(sig_b.id)
        db.refresh(sig_a)
        assert sig_a.status == "active"

    def test_uses_default_shop_id(self, db):
        sig = publish_signal(db, **{**MINIMAL_KWARGS, "entity_id": f"SKU-{_unique()}"})
        assert sig.shop_id is not None
        assert sig.shop_id >= 1


# ══════════════════════════════════════════════════════════════════════════════
# expire_stale_signals
# ══════════════════════════════════════════════════════════════════════════════

class TestExpireStaleSignals:
    def _make_signal(self, db, valid_until, status="active") -> models.IntelligenceSignal:
        uid = _unique()
        sig = models.IntelligenceSignal(
            shop_id=1,
            engine="expire_test",
            signal_type="stale_check",
            entity_type="sku",
            entity_id=f"SKU-EXP-{uid}",
            explanation="Test signaal voor vervaldatum-tests.",
            evidence={"v": 1},
            sources=["test"],
            confidence=0.5,
            status=status,
            valid_until=valid_until,
            dedupe_key=f"expire_test:stale_check:sku:SKU-EXP-{uid}",
        )
        db.add(sig)
        db.flush()
        return sig

    def test_marks_expired_signals(self, clean_db):
        db, ids = clean_db
        past = datetime.utcnow() - timedelta(hours=1)
        sig = self._make_signal(db, valid_until=past)
        sig_id = sig.id
        ids.append(sig_id)
        db.commit()

        db2 = SessionLocal()
        try:
            n = expire_stale_signals(db2)
            db2.commit()
            assert n >= 1
            # Query via db2 — sig behoort tot db, niet db2
            refreshed = db2.query(models.IntelligenceSignal).filter_by(id=sig_id).first()
            assert refreshed is not None
            assert refreshed.status == "expired"
        finally:
            db2.close()

    def test_ignores_future_valid_until(self, clean_db):
        db, ids = clean_db
        future = datetime.utcnow() + timedelta(days=10)
        sig = self._make_signal(db, valid_until=future)
        sig_id = sig.id
        ids.append(sig_id)
        db.commit()

        db2 = SessionLocal()
        try:
            expire_stale_signals(db2)
            db2.commit()
            refreshed = db2.query(models.IntelligenceSignal).filter_by(id=sig_id).first()
            assert refreshed.status == "active"
        finally:
            db2.close()

    def test_ignores_already_superseded(self, clean_db):
        db, ids = clean_db
        past = datetime.utcnow() - timedelta(hours=1)
        sig = self._make_signal(db, valid_until=past, status="superseded")
        sig_id = sig.id
        ids.append(sig_id)
        db.commit()

        db2 = SessionLocal()
        try:
            expire_stale_signals(db2)
            db2.commit()
            refreshed = db2.query(models.IntelligenceSignal).filter_by(id=sig_id).first()
            # Moet superseded blijven, niet expired worden
            assert refreshed.status == "superseded"
        finally:
            db2.close()

    def test_ignores_signal_without_valid_until(self, clean_db):
        db, ids = clean_db
        sig = self._make_signal(db, valid_until=None)
        sig_id = sig.id
        ids.append(sig_id)
        db.commit()

        db2 = SessionLocal()
        try:
            expire_stale_signals(db2)
            db2.commit()
            refreshed = db2.query(models.IntelligenceSignal).filter_by(id=sig_id).first()
            assert refreshed.status == "active"
        finally:
            db2.close()

    def test_returns_count_of_expired(self, clean_db):
        db, ids = clean_db
        past = datetime.utcnow() - timedelta(hours=2)
        for _ in range(3):
            sig = self._make_signal(db, valid_until=past)
            ids.append(sig.id)
        db.commit()

        db2 = SessionLocal()
        try:
            n = expire_stale_signals(db2)
            db2.commit()
            assert n >= 3
        finally:
            db2.close()


# ══════════════════════════════════════════════════════════════════════════════
# Emitter-contracttests: signals bevatten required fields
# ══════════════════════════════════════════════════════════════════════════════

def _assert_signal_contract(sig: models.IntelligenceSignal):
    """Verifieer dat een IntelligenceSignal de §64.9-10-velden bevat."""
    assert sig.explanation and sig.explanation.strip(), \
        f"Signal {sig.engine}:{sig.signal_type} mist explanation"
    assert sig.evidence, \
        f"Signal {sig.engine}:{sig.signal_type} mist evidence"
    assert sig.sources, \
        f"Signal {sig.engine}:{sig.signal_type} mist sources"
    assert sig.confidence is not None and 0.0 <= sig.confidence <= 1.0, \
        f"Signal {sig.engine}:{sig.signal_type} heeft ongeldige confidence"
    assert sig.model_version, \
        f"Signal {sig.engine}:{sig.signal_type} mist model_version"


class TestCompetitionEmitter:
    def test_competitive_pressure_signal_contract(self, clean_db):
        """Een SKU die duurder is dan de markt krijgt een signaal met alle vereiste velden."""
        from engine.signal_emitters import emit_competition_signals

        db, ids = clean_db
        uid = _unique()
        sku_id = f"SKU-COMP-{uid}"

        # Minimale SkuCompetitionScore-rij: duurder dan de markt, sterke klasse
        score = models.SkuCompetitionScore(
            sku_id=sku_id,
            run_date=date_type.today(),
            price_index=9.99,          # extreem duurder → altijd in top-MAX_PER_TYPE, ook met echte feed-data in de DB
            competition_class="Critical",
            pcis_score=0.8,
            reference_price=10.00,
            competitors_used=5,
            competitors_excluded=0,
        )
        db.add(score)
        db.commit()

        try:
            db2 = SessionLocal()
            try:
                n = emit_competition_signals(db2)
                assert n >= 1
                db2.flush()  # autoflush=False — flush zodat de query de nieuwe rijen ziet
                sigs = db2.query(models.IntelligenceSignal).filter(
                    models.IntelligenceSignal.entity_id == sku_id,
                    models.IntelligenceSignal.engine == "competition",
                ).all()
                assert sigs, "Geen signaal aangemaakt voor dure SKU"
                for sig in sigs:
                    _assert_signal_contract(sig)
                    ids.append(sig.id)
            finally:
                db2.close()
        finally:
            db.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).delete()
            db.commit()

    def test_price_opportunity_signal_contract(self, clean_db):
        """Een SKU die goedkoper is dan de markt krijgt een opportunity-signaal."""
        from engine.signal_emitters import emit_competition_signals

        db, ids = clean_db
        uid = _unique()
        sku_id = f"SKU-OPP-{uid}"

        score = models.SkuCompetitionScore(
            sku_id=sku_id,
            run_date=date_type.today(),
            price_index=0.01,          # extreem goedkoper → altijd in top-MAX_PER_TYPE, ook met echte feed-data in de DB
            competition_class="Monitor",
            pcis_score=0.3,
            reference_price=10.00,
            competitors_used=3,
            competitors_excluded=0,
        )
        db.add(score)
        db.commit()

        try:
            db2 = SessionLocal()
            try:
                emit_competition_signals(db2)
                db2.flush()  # autoflush=False
                sigs = db2.query(models.IntelligenceSignal).filter(
                    models.IntelligenceSignal.entity_id == sku_id,
                    models.IntelligenceSignal.signal_type == "price_increase_opportunity",
                ).all()
                assert sigs, "Geen opportunity-signaal voor goedkope SKU"
                for sig in sigs:
                    _assert_signal_contract(sig)
                    ids.append(sig.id)
            finally:
                db2.close()
        finally:
            db.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).delete()
            db.commit()


class TestPricingEmitter:
    def test_price_increase_signal_contract(self, clean_db):
        """Pending prijsverhoging ≥ 2% → signal met alle vereiste velden."""
        from engine.signal_emitters import emit_pricing_signals

        db, ids = clean_db
        uid = _unique()
        sku_id = f"SKU-PRIC-{uid}"
        today = date_type.today()

        rec = models.FactPricingRecommendationDaily(
            date=today,
            sku_id=sku_id,
            shop_id=1,
            current_price=10.00,
            recommended_price=10.50,
            recommended_change_pct=5.0,     # +5% → price_increase_recommended
            expected_margin_uplift=0.40,
            expected_revenue=105.00,
            confidence_score=0.80,
            reason_code="margin_improvement",
            strategy_type="MARGIN_DEFENSE",
            safety_status="ok",
            approval_status="pending",
            model_version="pricing-v2",
        )
        db.add(rec)
        db.commit()

        try:
            db2 = SessionLocal()
            try:
                n = emit_pricing_signals(db2)
                assert n >= 1
                db2.flush()  # autoflush=False
                sigs = db2.query(models.IntelligenceSignal).filter(
                    models.IntelligenceSignal.entity_id == sku_id,
                    models.IntelligenceSignal.engine == "pricing",
                ).all()
                assert sigs, "Geen pricing-signaal aangemaakt"
                for sig in sigs:
                    _assert_signal_contract(sig)
                    ids.append(sig.id)
            finally:
                db2.close()
        finally:
            db.query(models.FactPricingRecommendationDaily).filter_by(sku_id=sku_id).delete()
            db.commit()


class TestBcgEmitter:
    def test_pricing_power_star_signal_contract(self, clean_db):
        """PRICING_POWER_STAR-SKU → signal met alle vereiste velden."""
        from engine.signal_emitters import emit_bcg_signals

        db, ids = clean_db
        uid = _unique()
        eid = f"SKU-BCG-{uid}"
        today = date_type.today()

        row = models.FactBcgClassificationDaily(
            date=today,
            entity_type="SKU",
            entity_id=eid,
            entity_name=f"Testproduct {uid}",
            hybrid_bcg_class="PRICING_POWER_STAR",
            pricing_power_score=0.82,
            css_external_score=0.25,
            ibss_score=0.70,
            gps_score=0.65,
            pricing_strategy="PROTECT_MARGIN",
            confidence_score=0.78,
        )
        db.add(row)
        db.commit()

        try:
            db2 = SessionLocal()
            try:
                n = emit_bcg_signals(db2)
                assert n >= 1
                db2.flush()  # autoflush=False
                sigs = db2.query(models.IntelligenceSignal).filter(
                    models.IntelligenceSignal.entity_id == eid,
                    models.IntelligenceSignal.engine == "bcg",
                ).all()
                assert sigs, "Geen BCG-signaal aangemaakt"
                for sig in sigs:
                    _assert_signal_contract(sig)
                    ids.append(sig.id)
            finally:
                db2.close()
        finally:
            db.query(models.FactBcgClassificationDaily).filter_by(entity_id=eid).delete()
            db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# emit_all_signals — emitter-fout crasht de run NIET
# ══════════════════════════════════════════════════════════════════════════════

class TestEmitAllSignalsRollback:
    # run_competitor_rankings is een lazy import BINNEN emit_all_signals:
    #   from engine.competition_rankings import run_competitor_rankings
    # Patch het daarom op de bronmodule, niet op signal_emitters.
    _RCR_TARGET = "engine.competition_rankings.run_competitor_rankings"
    _EXPIRE_TARGET = "engine.signal_emitters.expire_stale_signals"

    def test_failing_emitter_does_not_crash_run(self, db):
        """Als één emitter een exception gooit, worden de overige nog steeds gedraaid
        en retourneert emit_all_signals een resultatendict met -1 voor de gefaalde."""
        from engine.signal_emitters import emit_all_signals

        def boom(_db):
            raise RuntimeError("Gesimuleerde emitter-crash")

        patched_emitters = {"broken": boom}

        with patch("engine.signal_emitters.EMITTERS", patched_emitters), \
             patch(self._RCR_TARGET, return_value=0), \
             patch(self._EXPIRE_TARGET, return_value=0):
            results = emit_all_signals(db)

        assert "broken" in results, "Gefaalde emitter moet in resultaten staan"
        assert results["broken"] == -1, "Gefaalde emitter moet -1 teruggeven"
        # Geen onverwachte exceptions: de run is niet gecrasht

    def test_one_failing_emitter_does_not_block_others(self, db):
        """Tweede emitter draait nog steeds als de eerste crasht."""
        from engine.signal_emitters import emit_all_signals

        call_log = []

        def boom(_db):
            call_log.append("boom")
            raise RuntimeError("eerste crasht")

        def fine(_db):
            call_log.append("fine")
            return 0

        patched_emitters = {"engine_a": boom, "engine_b": fine}

        with patch("engine.signal_emitters.EMITTERS", patched_emitters), \
             patch(self._RCR_TARGET, return_value=0), \
             patch(self._EXPIRE_TARGET, return_value=0):
            results = emit_all_signals(db)

        assert "boom" in call_log, "Eerste emitter moet aangeroepen zijn"
        assert "fine" in call_log, "Tweede emitter moet ook aangeroepen zijn ondanks crash in eerste"
        assert results["engine_a"] == -1
        assert results["engine_b"] == 0

    def test_all_engines_succeed_returns_counts(self, db):
        """Als alle emitters slagen, retourneert emit_all_signals positieve tellingen."""
        from engine.signal_emitters import emit_all_signals

        patched_emitters = {"eng1": lambda _db: 3, "eng2": lambda _db: 7}

        with patch("engine.signal_emitters.EMITTERS", patched_emitters), \
             patch(self._RCR_TARGET, return_value=0), \
             patch(self._EXPIRE_TARGET, return_value=2):
            results = emit_all_signals(db)

        assert results["eng1"] == 3
        assert results["eng2"] == 7
        assert results.get("expired") == 2

    def test_rankings_failure_does_not_abort_emitters(self, db):
        """Als run_competitor_rankings crasht, draaien de emitters nog steeds."""
        from engine.signal_emitters import emit_all_signals

        call_log = []

        def fine(_db):
            call_log.append("fine")
            return 1

        patched_emitters = {"pricing": fine}

        with patch("engine.signal_emitters.EMITTERS", patched_emitters), \
             patch(self._RCR_TARGET, side_effect=RuntimeError("rankings down")), \
             patch(self._EXPIRE_TARGET, return_value=0):
            results = emit_all_signals(db)

        assert "fine" in call_log, "Emitters moeten draaien ook al crashte rankings"
        assert results.get("rankings") == -1
        assert results.get("pricing") == 1
