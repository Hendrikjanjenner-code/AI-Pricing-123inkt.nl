"""
Regressietests voor de campagne-upliftberekening (compute_campaign_uplift)
en de signaalpublicatie (publish_campaign_uplift_signals).

Beschermt tegen stille regressies in:
- groepfiltering (alleen-treatment / alleen-control / lege campagnes overslaan)
- de richting (direction) van de uplift
- z-score / confidence-berekening (basiseigenschappen)
- signal_type en deduplicatie (supersede) bij herpublicatie.

Draait tegen de dev-database; alle testdata wordt na afloop opgeruimd.
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine import loyalty_intelligence as li


@pytest.fixture(scope="module", autouse=True)
def ensure_shop():
    """Zorg dat dim_shop id=1 en id=2 bestaan (lege dev-DB na alleen users-seed)."""
    from sqlalchemy import text as sa_text
    s = SessionLocal()
    try:
        cols = [r[0] for r in s.execute(sa_text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='dim_shop' AND is_nullable='NO' "
            "AND column_default IS NULL AND column_name NOT IN ('id')"
        )).fetchall()]
        extra_cols = "".join(f", {c}" for c in cols)
        for sid in (1, 2):
            extra_vals = "".join(f", 'test-{c}-{sid}'" for c in cols)
            s.execute(sa_text(
                f"INSERT INTO dim_shop (id{extra_cols}) VALUES ({sid}{extra_vals}) "
                "ON CONFLICT (id) DO NOTHING"
            ))
        s.commit()
    finally:
        s.close()
    yield


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    try:
        s.rollback()
        s.close()
    except Exception:
        pass


class CampaignFactory:
    """Maakt campagnes/leden/transacties aan en ruimt alles op na de test."""

    def __init__(self, db):
        self.db = db
        self.member_ids: list[int] = []
        self.campaign_ids: list[int] = []

    def member(self, *, shop_id=1) -> models.LoyaltyMember:
        m = models.LoyaltyMember(
            shop_id=shop_id,
            pseudonymous_customer_id=f"TEST-UPLIFT-{uuid.uuid4().hex[:10]}",
            tier_code="bronze", status="active", is_demo_data=False,
        )
        self.db.add(m)
        self.db.flush()
        self.member_ids.append(m.id)
        return m

    def campaign(self, *, start=None, end=None, name=None, shop_id=1) -> models.LoyaltyCampaign:
        c = models.LoyaltyCampaign(
            shop_id=shop_id,
            name=name or f"TEST-UPLIFT-CAMPAGNE-{uuid.uuid4().hex[:8]}",
            campaign_type="bonus_points",
            start_date=start, end_date=end, status="active",
        )
        self.db.add(c)
        self.db.flush()
        self.campaign_ids.append(c.id)
        return c

    def assign(self, campaign, member, group_type):
        self.db.add(models.LoyaltyCampaignMembership(
            campaign_id=campaign.id, member_id=member.id, group_type=group_type,
        ))
        self.db.flush()

    def earn(self, member, txn_date, order_value, points=10):
        li.apply_ledger_entry(
            self.db, member, txn_date, "earn", points,
            order_value=order_value,
            external_ref=f"TEST-UPLIFT-{uuid.uuid4().hex[:12]}",
        )

    def cleanup(self):
        try:
            self.db.rollback()
            self.db.close()
        except Exception:
            pass
        s = SessionLocal()
        try:
            if self.campaign_ids:
                s.query(models.IntelligenceSignal).filter(
                    models.IntelligenceSignal.engine == "loyalty",
                    models.IntelligenceSignal.entity_type == "campaign",
                    models.IntelligenceSignal.entity_id.in_(
                        [str(cid) for cid in self.campaign_ids]
                    ),
                ).delete(synchronize_session=False)
                s.query(models.LoyaltyCampaignMembership).filter(
                    models.LoyaltyCampaignMembership.campaign_id.in_(self.campaign_ids)
                ).delete(synchronize_session=False)
                s.query(models.LoyaltyCampaign).filter(
                    models.LoyaltyCampaign.id.in_(self.campaign_ids)
                ).delete(synchronize_session=False)
            if self.member_ids:
                s.query(models.LoyaltyTransaction).filter(
                    models.LoyaltyTransaction.member_id.in_(self.member_ids)
                ).delete(synchronize_session=False)
                s.query(models.LoyaltyWallet).filter(
                    models.LoyaltyWallet.member_id.in_(self.member_ids)
                ).delete(synchronize_session=False)
                s.query(models.LoyaltyMember).filter(
                    models.LoyaltyMember.id.in_(self.member_ids)
                ).delete(synchronize_session=False)
            s.commit()
        finally:
            s.close()


@pytest.fixture()
def factory(db):
    f = CampaignFactory(db)
    yield f
    f.cleanup()


PERIOD_START = date.today() - timedelta(days=60)
PERIOD_END = date.today() - timedelta(days=1)
IN_PERIOD = date.today() - timedelta(days=30)


def _build_two_group_campaign(factory, *, treatment_spend, control_spend,
                              start=PERIOD_START, end=PERIOD_END):
    """Campagne met 3 treatment- en 3 control-leden; besteding per lid opgegeven."""
    c = factory.campaign(start=start, end=end)
    for spend in treatment_spend:
        m = factory.member()
        factory.assign(c, m, "treatment")
        if spend:
            factory.earn(m, IN_PERIOD, spend)
    for spend in control_spend:
        m = factory.member()
        factory.assign(c, m, "control")
        if spend:
            factory.earn(m, IN_PERIOD, spend)
    return c


# ---------------------------------------------------------------------------
# compute_campaign_uplift — groepfiltering
# ---------------------------------------------------------------------------

def test_empty_campaign_skipped(db, factory):
    c = factory.campaign(start=PERIOD_START, end=PERIOD_END)
    assert li.compute_campaign_uplift(db, campaign_id=c.id) == []


def test_treatment_only_campaign_skipped(db, factory):
    c = factory.campaign(start=PERIOD_START, end=PERIOD_END)
    m = factory.member()
    factory.assign(c, m, "treatment")
    factory.earn(m, IN_PERIOD, 100)
    assert li.compute_campaign_uplift(db, campaign_id=c.id) == []


def test_control_only_campaign_skipped(db, factory):
    c = factory.campaign(start=PERIOD_START, end=PERIOD_END)
    m = factory.member()
    factory.assign(c, m, "control")
    factory.earn(m, IN_PERIOD, 100)
    assert li.compute_campaign_uplift(db, campaign_id=c.id) == []


def test_both_groups_analyzed_with_correct_stats(db, factory):
    c = _build_two_group_campaign(
        factory, treatment_spend=[100, 200, 300], control_spend=[100, 100, 100]
    )
    results = li.compute_campaign_uplift(db, campaign_id=c.id)
    assert len(results) == 1
    r = results[0]
    assert r["campaign_id"] == c.id
    assert r["treatment"]["n"] == 3
    assert r["control"]["n"] == 3
    assert r["treatment"]["spend_per_member"] == pytest.approx(200.0)
    assert r["control"]["spend_per_member"] == pytest.approx(100.0)
    assert r["uplift"]["spend_per_member_pct"] == pytest.approx(100.0)
    # Beide groepen volledige retentie → geen retentie-uplift, z = 0
    assert r["treatment"]["retention_rate"] == pytest.approx(1.0)
    assert r["z_retention"] == pytest.approx(0.0)
    assert 0.0 <= r["combined_confidence"] <= 1.0


def test_campaign_without_dates_uses_fallback_period(db, factory):
    """Zonder start/einddatum valt de meetperiode terug op 365d t/m vandaag."""
    c = _build_two_group_campaign(
        factory, treatment_spend=[150, 150], control_spend=[100, 100],
        start=None, end=None,
    )
    results = li.compute_campaign_uplift(db, campaign_id=c.id)
    assert len(results) == 1
    r = results[0]
    assert r["start_date"] == (date.today() - timedelta(days=365)).isoformat()
    assert r["end_date"] == date.today().isoformat()
    assert r["uplift"]["spend_per_member_pct"] == pytest.approx(50.0)


def test_transactions_outside_period_excluded(db, factory):
    c = factory.campaign(start=PERIOD_START, end=PERIOD_END)
    mt = factory.member()
    mc = factory.member()
    factory.assign(c, mt, "treatment")
    factory.assign(c, mc, "control")
    factory.earn(mt, IN_PERIOD, 100)
    factory.earn(mc, IN_PERIOD, 100)
    # Buiten de periode: mag de stats niet beïnvloeden
    factory.earn(mt, PERIOD_START - timedelta(days=10), 9999)
    factory.earn(mt, PERIOD_END + timedelta(days=1), 9999)
    r = li.compute_campaign_uplift(db, campaign_id=c.id)[0]
    assert r["treatment"]["spend_total"] == pytest.approx(100.0)
    assert r["treatment"]["orders_total"] == 1


# ---------------------------------------------------------------------------
# direction
# ---------------------------------------------------------------------------

def test_direction_positive_when_treatment_spends_more(db, factory):
    c = _build_two_group_campaign(
        factory, treatment_spend=[200, 200], control_spend=[100, 100]
    )
    r = li.compute_campaign_uplift(db, campaign_id=c.id)[0]
    assert r["direction"] == "positive"
    assert r["uplift"]["spend_per_member_pct"] > 5


def test_direction_negative_when_treatment_spends_less(db, factory):
    c = _build_two_group_campaign(
        factory, treatment_spend=[50, 50], control_spend=[100, 100]
    )
    r = li.compute_campaign_uplift(db, campaign_id=c.id)[0]
    assert r["direction"] == "negative"
    assert r["uplift"]["spend_per_member_pct"] < -5


def test_direction_neutral_when_within_threshold(db, factory):
    c = _build_two_group_campaign(
        factory, treatment_spend=[102, 102], control_spend=[100, 100]
    )
    r = li.compute_campaign_uplift(db, campaign_id=c.id)[0]
    assert r["direction"] == "neutral"


def test_direction_neutral_when_control_spend_zero(db, factory):
    """Control zonder besteding → uplift% onbepaald (None) → neutraal."""
    c = _build_two_group_campaign(
        factory, treatment_spend=[100, 100], control_spend=[None, None]
    )
    r = li.compute_campaign_uplift(db, campaign_id=c.id)[0]
    assert r["uplift"]["spend_per_member_pct"] is None
    assert r["direction"] == "neutral"


# ---------------------------------------------------------------------------
# publish_campaign_uplift_signals
# ---------------------------------------------------------------------------

def _active_signals(db, campaign_id):
    return db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.engine == "loyalty",
        models.IntelligenceSignal.entity_type == "campaign",
        models.IntelligenceSignal.entity_id == str(campaign_id),
        models.IntelligenceSignal.status == "active",
    ).all()


def test_publish_creates_correct_signal_type(db, factory):
    c = _build_two_group_campaign(
        factory, treatment_spend=[200, 200], control_spend=[100, 100]
    )
    published = li.publish_campaign_uplift_signals(db)
    db.flush()
    assert published >= 1
    signals = _active_signals(db, c.id)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_type == "campaign_uplift_positive"
    assert sig.direction == "positive"
    assert sig.severity == "medium"
    assert sig.suggested_action == "scale_campaign"
    assert sig.dedupe_key == f"loyalty:campaign_uplift_positive:campaign:{c.id}"
    assert sig.evidence["uplift"]["spend_per_member_pct"] == pytest.approx(100.0)


def test_republish_supersedes_previous_signal(db, factory):
    """Herpublicatie mag nooit twee actieve uplift-signalen per campagne laten staan."""
    c = _build_two_group_campaign(
        factory, treatment_spend=[200, 200], control_spend=[100, 100]
    )
    li.publish_campaign_uplift_signals(db)
    db.flush()
    li.publish_campaign_uplift_signals(db)
    db.flush()
    signals = _active_signals(db, c.id)
    assert len(signals) == 1
    superseded = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.entity_type == "campaign",
        models.IntelligenceSignal.entity_id == str(c.id),
        models.IntelligenceSignal.status == "superseded",
    ).count()
    assert superseded >= 1


def test_signal_inherits_campaign_shop_id(db, factory):
    """Signalen erven shop_id van de campagne i.p.v. hardcoded shop 1."""
    c = factory.campaign(start=PERIOD_START, end=PERIOD_END, shop_id=2)
    for spend, group in ((200, "treatment"), (200, "treatment"),
                         (100, "control"), (100, "control")):
        m = factory.member(shop_id=2)
        factory.assign(c, m, group)
        factory.earn(m, IN_PERIOD, spend)
    li.publish_campaign_uplift_signals(db)
    db.flush()
    signals = _active_signals(db, c.id)
    assert len(signals) == 1
    assert signals[0].shop_id == 2


def test_compute_uplift_scoped_to_shop(db, factory):
    """compute_campaign_uplift(shop_id=...) beperkt zich tot campagnes van die shop."""
    c1 = _build_two_group_campaign(
        factory, treatment_spend=[200, 200], control_spend=[100, 100]
    )
    c2 = factory.campaign(start=PERIOD_START, end=PERIOD_END, shop_id=2)
    for spend, group in ((150, "treatment"), (100, "control")):
        m = factory.member(shop_id=2)
        factory.assign(c2, m, group)
        factory.earn(m, IN_PERIOD, spend)

    results = li.compute_campaign_uplift(db, shop_id=2)
    ids = {r["campaign_id"] for r in results}
    assert c2.id in ids
    assert c1.id not in ids
    assert all(r["shop_id"] == 2 for r in results if r["campaign_id"] == c2.id)


def test_direction_change_supersedes_old_direction(db, factory):
    """Als de richting omslaat, wordt het oude signaal (ander type) superseded."""
    c = _build_two_group_campaign(
        factory, treatment_spend=[200, 200], control_spend=[100, 100]
    )
    li.publish_campaign_uplift_signals(db)
    db.flush()
    # Extra control-besteding zodat treatment nu lager uitkomt → negative
    extra = factory.member()
    factory.assign(c, extra, "control")
    factory.earn(extra, IN_PERIOD, 1000)
    li.publish_campaign_uplift_signals(db)
    db.flush()
    signals = _active_signals(db, c.id)
    assert len(signals) == 1
    assert signals[0].signal_type == "campaign_uplift_negative"
