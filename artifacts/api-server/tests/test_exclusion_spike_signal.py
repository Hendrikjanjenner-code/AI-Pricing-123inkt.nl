"""
Tests voor taak #213: waarschuw automatisch bij een plotselinge stijging van
uitgesloten concurrentprijzen.

Patroon: seed twee scoring-runs (vorige + laatste) met excluded_reasons,
draai emit_competition_signals en assert dat een shop-gescoped
'exclusion_spike'-signaal per reden verschijnt bij een significante stijging
(>50% én absoluut relevant), en automatisch oplost zodra de aantallen
normaliseren.

Zelfde conventies als test_signal_auto_resolve.py: dev-database, toekomstige
run_dates zodat residu van echte syncs de 'laatste run'-selectie niet stoort,
en volledige opruiming na afloop.
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
from engine.signal_emitters import (
    emit_competition_signals,
    EXCLUSION_SPIKE_MIN_INCREASE,
)
from engine.signal_publisher import _default_shop_id

OOS = "COMPETITOR_IGNORED_OUT_OF_STOCK"
DELIVERY = "COMPETITOR_IGNORED_BAD_DELIVERY"
OUTLIER = "COMPETITOR_IGNORED_OUTLIER"

PREV_RUN = date_type.today() + timedelta(days=30)
LAST_RUN = date_type.today() + timedelta(days=31)
NEXT_RUN = date_type.today() + timedelta(days=32)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _score_row(sku_id, run_date, reasons, shop_id):
    total = sum(reasons.values()) if reasons else 0
    return models.SkuCompetitionScore(
        sku_id=sku_id, run_date=run_date, shop_id=shop_id,
        price_index=1.0, competition_class="Monitor", pcis_score=0.3,
        reference_price=10.0, competitors_used=3,
        competitors_excluded=total, excluded_reasons=reasons or None)


@pytest.fixture()
def db():
    s = SessionLocal()
    sid = _default_shop_id(s)
    # Schone lei: geen actieve exclusion_spike-signalen uit eerdere runs.
    s.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.signal_type == "exclusion_spike",
    ).delete(synchronize_session=False)
    s.commit()
    yield s
    try:
        s.rollback()
        s.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.run_date >= PREV_RUN,
        ).delete(synchronize_session=False)
        s.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "exclusion_spike",
        ).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()


def _spike_signal(db, reason, status=None):
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.signal_type == "exclusion_spike",
        models.IntelligenceSignal.entity_id == reason)
    if status:
        q = q.filter(models.IntelligenceSignal.status == status)
    return q.order_by(models.IntelligenceSignal.id.desc()).first()


class TestExclusionSpikeSignal:
    def test_spike_publishes_shop_scoped_signal_per_reason(self, db):
        sid = _default_shop_id(db)
        uid = _unique()
        # Vorige run: 10 levertijd-uitsluitingen; laatste run: 40 (=+300%).
        db.add(_score_row(f"SKU-XSP-{uid}-a", PREV_RUN, {DELIVERY: 10}, sid))
        db.add(_score_row(f"SKU-XSP-{uid}-a", LAST_RUN, {DELIVERY: 25}, sid))
        db.add(_score_row(f"SKU-XSP-{uid}-b", LAST_RUN, {DELIVERY: 15, OOS: 3}, sid))
        db.commit()

        emit_competition_signals(db)
        db.commit()

        sig = _spike_signal(db, DELIVERY)
        assert sig is not None and sig.status == "active"
        assert sig.shop_id == sid
        assert sig.engine == "competition"
        assert sig.dedupe_key == f"competition:exclusion_spike:exclusion_reason:{DELIVERY}"
        assert sig.current_value == 40.0 and sig.previous_value == 10.0
        assert sig.change_pct == 300.0
        assert sig.explanation and sig.evidence and sig.sources
        # OOS steeg maar met 3 (< absolute drempel): geen signaal.
        assert _spike_signal(db, OOS) is None

    def test_small_or_relative_only_increase_is_ignored(self, db):
        sid = _default_shop_id(db)
        uid = _unique()
        # +40% (onder 50%-drempel) en +5 outliers (onder absolute drempel).
        db.add(_score_row(f"SKU-XSM-{uid}-p", PREV_RUN,
                          {DELIVERY: 50, OUTLIER: 2}, sid))
        db.add(_score_row(f"SKU-XSM-{uid}-l", LAST_RUN,
                          {DELIVERY: 70, OUTLIER: 7}, sid))
        db.commit()

        emit_competition_signals(db)
        db.commit()

        assert _spike_signal(db, DELIVERY) is None
        assert _spike_signal(db, OUTLIER) is None

    def test_new_reason_from_zero_counts_as_spike(self, db):
        sid = _default_shop_id(db)
        uid = _unique()
        db.add(_score_row(f"SKU-XSZ-{uid}-p", PREV_RUN, {}, sid))
        db.add(_score_row(f"SKU-XSZ-{uid}-l", LAST_RUN,
                          {OOS: EXCLUSION_SPIKE_MIN_INCREASE}, sid))
        db.commit()

        emit_competition_signals(db)
        db.commit()

        sig = _spike_signal(db, OOS)
        assert sig is not None and sig.status == "active"
        assert sig.previous_value == 0.0

    def test_signal_resolves_when_counts_normalize(self, db):
        sid = _default_shop_id(db)
        uid = _unique()
        db.add(_score_row(f"SKU-XRN-{uid}-p", PREV_RUN, {DELIVERY: 10}, sid))
        db.add(_score_row(f"SKU-XRN-{uid}-l", LAST_RUN, {DELIVERY: 40}, sid))
        db.commit()
        emit_competition_signals(db)
        db.commit()
        assert _spike_signal(db, DELIVERY).status == "active"

        # Nieuwe run: aantallen genormaliseerd t.o.v. de vorige run.
        db.add(_score_row(f"SKU-XRN-{uid}-n", NEXT_RUN, {DELIVERY: 12}, sid))
        db.commit()
        emit_competition_signals(db)
        db.commit()

        assert _spike_signal(db, DELIVERY).status == "resolved"

        # Idempotent: nóg een run publiceert niet opnieuw.
        emit_competition_signals(db)
        db.commit()
        rows = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "exclusion_spike",
            models.IntelligenceSignal.entity_id == DELIVERY).all()
        assert len(rows) == 1 and rows[0].status == "resolved"

    def test_foreign_shop_run_does_not_publish_or_resolve(self, db):
        sid = _default_shop_id(db)
        uid = _unique()
        other = models.DimShop(shop_code=f"XSPK-{uid}", name=f"Spike {uid}")
        db.add(other)
        db.flush()
        # Eigen winkel: actieve spike.
        db.add(_score_row(f"SKU-XFS-{uid}-p", PREV_RUN, {DELIVERY: 10}, sid))
        db.add(_score_row(f"SKU-XFS-{uid}-l", LAST_RUN, {DELIVERY: 40}, sid))
        db.commit()
        emit_competition_signals(db)
        db.commit()
        assert _spike_signal(db, DELIVERY).status == "active"

        # Nieuwere run van een ándere winkel met normale aantallen mag het
        # eigen signaal niet oplossen.
        db.add(_score_row(f"SKU-XFS-{uid}-o", NEXT_RUN, {DELIVERY: 1}, other.id))
        db.commit()
        emit_competition_signals(db)
        db.commit()
        assert _spike_signal(db, DELIVERY).status == "active"

        # Opruimen extra winkel.
        db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.shop_id == other.id).delete(
            synchronize_session=False)
        db.query(models.DimShop).filter(
            models.DimShop.id == other.id).delete(
            synchronize_session=False)
        db.commit()
