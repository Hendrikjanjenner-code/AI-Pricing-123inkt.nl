"""
Regressietests voor loyalty-intelligence (taak: stille regressies loyalty-ledger):
- verify_ledger_integrity: wallet != som(ledger) wordt gedetecteerd.
- compute_customer_value: segmentatie (high/mid/low/at_risk/lost), CLV-formule,
  churn-grenzen en confidence.
- Upload-processors (_process_loyalty_members / _process_loyalty_transactions):
  ongeldige rijen leveren warnings op zonder data-corruptie.

Aanvulling op tests/test_loyalty_ledger.py (dat apply_ledger_entry dekt).
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
from routes.uploads import _process_loyalty_members, _process_loyalty_transactions

# Vaste, historische run_date zodat compute_customer_value-tests geen
# dagelijkse productie-runs van vandaag wegvagen (delete op run_date).
CVS_RUN_DATE = date(2001, 1, 15)


def _cleanup_member_ids(mids):
    s = SessionLocal()
    try:
        s.query(models.CustomerValueScore).filter(
            models.CustomerValueScore.member_id.in_(mids)).delete(synchronize_session=False)
        s.query(models.LoyaltyTransaction).filter(
            models.LoyaltyTransaction.member_id.in_(mids)).delete(synchronize_session=False)
        s.query(models.LoyaltyWallet).filter(
            models.LoyaltyWallet.member_id.in_(mids)).delete(synchronize_session=False)
        s.query(models.LoyaltyMember).filter(
            models.LoyaltyMember.id.in_(mids)).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()


@pytest.fixture()
def db():
    s = SessionLocal()
    created_ids = []
    yield s, created_ids
    try:
        s.rollback()
        s.close()
    except Exception:
        pass
    if created_ids:
        _cleanup_member_ids(created_ids)


def _mk_member(s, created_ids, **kw):
    m = models.LoyaltyMember(
        shop_id=1,
        pseudonymous_customer_id=f"TEST-LI-{uuid.uuid4().hex[:10]}",
        tier_code="bronze", status="active", is_demo_data=False, **kw,
    )
    s.add(m)
    s.commit()
    created_ids.append(m.id)
    return m


# ─── verify_ledger_integrity ─────────────────────────────────────────────────

def test_integrity_detects_wallet_tampering(db):
    s, ids = db
    m = _mk_member(s, ids)
    li.apply_ledger_entry(s, m, date.today(), "earn", 300, commit=True)
    assert [x for x in li.verify_ledger_integrity(s) if x["member_id"] == m.id] == []

    # Sabotage: wallet buiten de ledger om muteren
    wallet = li.ensure_wallet(s, m.id)
    wallet.balance_points = 999
    s.commit()
    mismatch = [x for x in li.verify_ledger_integrity(s) if x["member_id"] == m.id]
    assert mismatch == [{"member_id": m.id, "wallet_balance": 999, "ledger_sum": 300}]


def test_integrity_wallet_without_ledger_rows(db):
    s, ids = db
    m = _mk_member(s, ids)
    wallet = li.ensure_wallet(s, m.id)
    wallet.balance_points = 50  # saldo zonder enige ledger-entry
    s.commit()
    mismatch = [x for x in li.verify_ledger_integrity(s) if x["member_id"] == m.id]
    assert mismatch and mismatch[0]["ledger_sum"] == 0


# ─── compute_customer_value ──────────────────────────────────────────────────

def _earn(s, m, days_ago, points, order_value):
    li.apply_ledger_entry(
        s, m, CVS_RUN_DATE - timedelta(days=days_ago), "earn", points,
        order_value=order_value, external_ref=f"CVS-{uuid.uuid4().hex[:10]}")


def _score(s, member_id):
    return s.query(models.CustomerValueScore).filter_by(
        member_id=member_id, run_date=CVS_RUN_DATE).first()


def test_customer_value_segments(db):
    s, ids = db
    # high_value: recent, frequent (>=6), besteding >= 500
    hi = _mk_member(s, ids)
    for d in (10, 30, 60, 90, 120, 150, 180, 200):
        _earn(s, hi, d, 100, 100.0)  # 8 aankopen, €800
    # mid_value: besteding >= 150, weinig frequentie, recent genoeg
    mid = _mk_member(s, ids)
    _earn(s, mid, 20, 100, 100.0)
    _earn(s, mid, 40, 100, 100.0)
    # low_value: kleine recente aankoop
    lo = _mk_member(s, ids)
    _earn(s, lo, 15, 10, 20.0)
    # at_risk: laatste aankoop lang geleden (recency hoog, < 540d)
    risk = _mk_member(s, ids)
    _earn(s, risk, 350, 50, 80.0)
    # lost: nooit een aankoop
    lost = _mk_member(s, ids)
    s.commit()

    n = li.compute_customer_value(s, run_date=CVS_RUN_DATE)
    s.commit()
    assert n >= 5

    sc = _score(s, hi.id)
    assert sc.value_segment == "high_value"
    assert sc.frequency_12m == 8
    assert float(sc.monetary_12m) == pytest.approx(800.0)
    # CLV-formule: 12m-besteding × 2 × retentiekans
    assert float(sc.clv_estimate) == pytest.approx(round(800.0 * 2 * float(sc.retention_probability), 2))
    assert 0 < float(sc.confidence) <= 0.9
    assert sc.explanation and sc.next_best_action == "tier_upgrade_nudge"

    assert _score(s, mid.id).value_segment == "mid_value"
    assert _score(s, lo.id).value_segment == "low_value"

    sc_risk = _score(s, risk.id)
    assert sc_risk.value_segment == "at_risk"
    assert float(sc_risk.churn_risk) >= 0.6
    assert sc_risk.next_best_action == "winback_voucher"

    sc_lost = _score(s, lost.id)
    # Geen aankopen ooit → churn 0.9, recency None → segment lost
    assert sc_lost.value_segment == "lost"
    assert float(sc_lost.churn_risk) == pytest.approx(0.9)
    assert float(sc_lost.clv_estimate) == pytest.approx(0.0)
    assert sc_lost.next_best_action == "no_action"

    # Idempotent: tweede run voor dezelfde datum verdubbelt geen rijen.
    li.compute_customer_value(s, run_date=CVS_RUN_DATE)
    s.commit()
    cnt = s.query(models.CustomerValueScore).filter_by(
        member_id=hi.id, run_date=CVS_RUN_DATE).count()
    assert cnt == 1


# ─── Upload-processors ───────────────────────────────────────────────────────

def test_process_members_valid_and_invalid_rows(db):
    s, ids = db
    pid = f"TEST-LI-UP-{uuid.uuid4().hex[:10]}"
    rows = [
        {"pseudonymous_customer_id": pid, "joined_at": "2024-01-15",
         "tier_code": "SILVER", "status": "Active"},
        {"pseudonymous_customer_id": ""},          # ontbrekende id → failed
        {"pseudonymous_customer_id": f"TEST-LI-UP-{uuid.uuid4().hex[:10]}",
         "joined_at": "15-01-2024"},               # ongeldig datumformaat → warning
    ]
    processed, failed, warnings = _process_loyalty_members(rows, s)
    m = s.query(models.LoyaltyMember).filter_by(pseudonymous_customer_id=pid).first()
    assert m is not None
    ids.append(m.id)
    m2 = s.query(models.LoyaltyMember).filter(
        models.LoyaltyMember.pseudonymous_customer_id.like("TEST-LI-UP-%"),
        models.LoyaltyMember.id != m.id).first()
    if m2:
        ids.append(m2.id)

    assert failed == 1  # alleen de rij zonder id (datumfout in _enforce_row_validation slaat rij over)
    assert any("ontbreekt" in w for w in warnings)
    assert any("datumformaat" in w or "ongeldig" in w.lower() for w in warnings)
    assert m.tier_code == "silver" and m.status == "active"
    assert m.joined_at == date(2024, 1, 15)
    # Wallet is aangemaakt met saldo 0
    wallet = li.ensure_wallet(s, m.id)
    assert (wallet.balance_points or 0) == 0


def test_process_transactions_invalid_rows_no_corruption(db):
    s, ids = db
    m = _mk_member(s, ids)
    pid = m.pseudonymous_customer_id
    today = str(date.today())
    rows = [
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": today, "points_delta": "100"},
        {"pseudonymous_customer_id": pid, "txn_type": "teleport", "date": today, "points_delta": "10"},   # onbekend type
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": "01/02/2025", "points_delta": "10"},  # ongeldige datum
        {"pseudonymous_customer_id": "TEST-LI-GHOST", "txn_type": "earn", "date": today, "points_delta": "10"},  # onbekend lid
        {"pseudonymous_customer_id": pid, "txn_type": "redeem", "date": today, "points_delta": "-500"},   # saldo zou negatief worden
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": today, "points_delta": ""},          # punten ontbreken
        {"pseudonymous_customer_id": pid, "txn_type": "redeem", "date": today, "points_delta": "-40"},    # geldig
    ]
    processed, failed, warnings = _process_loyalty_transactions(rows, s)
    assert processed == 2
    assert failed == 5
    assert any("onbekend txn_type" in w for w in warnings)
    assert any("ongeldig" in w.lower() for w in warnings)  # datum
    assert any("onbekend — importeer eerst" in w for w in warnings)
    assert any("negatief" in w for w in warnings)

    # Geen corruptie: wallet == som(ledger), saldo klopt, precies 2 ledger-rijen
    wallet = li.ensure_wallet(s, m.id)
    assert wallet.balance_points == 60
    assert s.query(models.LoyaltyTransaction).filter_by(member_id=m.id).count() == 2
    assert [x for x in li.verify_ledger_integrity(s) if x["member_id"] == m.id] == []


# ─── CampaignUpliftSnapshot: trend over meerdere runs ────────────────────────

def _mk_campaign_with_groups(s, ids, shop_id=1):
    """Campagne met 2 treatment- en 2 control-leden + earn-transacties."""
    c = models.LoyaltyCampaign(
        shop_id=shop_id, name=f"TEST-UPLIFT-{uuid.uuid4().hex[:8]}",
        campaign_type="bonus_points",
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(), status="completed",
        is_demo_data=False,
    )
    s.add(c)
    s.commit()
    for i in range(4):
        m = _mk_member(s, ids)
        group = "treatment" if i < 2 else "control"
        s.add(models.LoyaltyCampaignMembership(
            campaign_id=c.id, member_id=m.id, group_type=group))
        # treatment besteedt meer dan control
        li.apply_ledger_entry(
            s, m, date.today() - timedelta(days=10), "earn",
            200 if group == "treatment" else 100,
            order_value=(200 if group == "treatment" else 100),
            order_reference=f"TEST-UPL-{c.id}-{i}",
        )
    s.commit()
    return c


def _cleanup_campaign(cid):
    s = SessionLocal()
    try:
        s.query(models.CampaignUpliftSnapshot).filter_by(campaign_id=cid).delete()
        s.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_type == "campaign",
            models.IntelligenceSignal.entity_id == str(cid),
        ).delete()
        s.query(models.LoyaltyCampaignMembership).filter_by(campaign_id=cid).delete()
        s.query(models.LoyaltyCampaign).filter_by(id=cid).delete()
        s.commit()
    finally:
        s.close()


def test_uplift_snapshot_persisted_per_run_including_same_day(db):
    s, ids = db
    # Niet-default winkel: snapshots moeten de winkel van de campagne dragen
    shop = models.DimShop(shop_code=f"UPL{uuid.uuid4().hex[:6]}",
                          name="Uplift-testshop", active=True)
    s.add(shop)
    s.commit()
    c = _mk_campaign_with_groups(s, ids, shop_id=shop.id)
    try:
        li.publish_campaign_uplift_signals(s)
        s.commit()
        li.publish_campaign_uplift_signals(s)  # tweede run op dezelfde dag
        s.commit()
        snaps = s.query(models.CampaignUpliftSnapshot).filter_by(
            campaign_id=c.id).order_by(models.CampaignUpliftSnapshot.id).all()
        # Elke run bewaart een eigen snapshot — ook op dezelfde dag
        assert len(snaps) == 2
        for snap in snaps:
            assert snap.run_date == date.today()
            assert snap.run_at is not None
            assert snap.shop_id == shop.id, (
                "snapshot moet de winkel van de campagne dragen, niet shop 1")
            assert snap.direction == "positive"       # treatment besteedt 2x zoveel
            assert snap.spend_uplift_pct == 100.0
            assert snap.treatment_n == 2 and snap.control_n == 2
            assert 0 <= (snap.combined_confidence or 0) <= 1
    finally:
        _cleanup_campaign(c.id)


def test_uplift_endpoint_history_returns_recent_runs_chronologically(db):
    from datetime import datetime as _dt
    from routes.loyalty import campaign_uplift
    s, ids = db
    c = _mk_campaign_with_groups(s, ids)
    try:
        # 95 kunstmatige historische snapshots + 1 echte run van vandaag
        base = _dt(2020, 1, 1, 3, 0, 0)
        for i in range(95):
            s.add(models.CampaignUpliftSnapshot(
                shop_id=1, campaign_id=c.id,
                run_date=date(2020, 1, 1) + timedelta(days=i),
                run_at=base + timedelta(days=i),
                spend_uplift_pct=float(i), combined_confidence=0.5,
                retention_confidence=0.5, direction="neutral",
                treatment_n=2, control_n=2,
            ))
        s.commit()
        li.publish_campaign_uplift_signals(s)
        s.commit()

        resp = campaign_uplift(c.id, db=s, current_user=None)
        hist = resp["history"]
        # Cap op 90 en de MEEST RECENTE runs, oudste→nieuwste voor de sparkline
        assert len(hist) == 90
        run_ats = [h["run_at"] for h in hist]
        assert run_ats == sorted(run_ats)
        # De nieuwste snapshot (van de echte run zojuist) zit erin ...
        assert hist[-1]["run_date"] == date.today().isoformat()
        # ... en de oudste kunstmatige rijen zijn eruit gevallen (geen stale window)
        assert hist[0]["run_at"] > "2020-01-01T03:00:00"
    finally:
        _cleanup_campaign(c.id)


def test_migration_drops_legacy_uplift_constraint_and_backfills_run_at(db):
    """
    Regressietest voor de rollout vanaf het oude schema: legacy unieke
    constraint (campaign_id, run_date) moet worden gedropt en bestaande rijen
    zonder run_at moeten worden gebackfilld, zodat meerdere runs per dag
    bewaard kunnen worden en de historie-volgorde klopt.
    """
    from sqlalchemy import text as sa_sql
    from database import engine
    import migrate

    s, ids = db
    c = _mk_campaign_with_groups(s, ids)
    try:
        with engine.connect() as conn:
            # Simuleer het oude schema. Onder dat schema konden duplicaten per
            # (campaign_id, run_date) niet bestaan — dedupliceer eerst zodat
            # de legacy constraint kan worden aangelegd op de dev-database.
            conn.execute(sa_sql(
                "DELETE FROM campaign_uplift_snapshots a USING campaign_uplift_snapshots b "
                "WHERE a.id < b.id AND a.campaign_id = b.campaign_id "
                "AND a.run_date = b.run_date"))
            # Legacy constraint + rij zonder run_at
            conn.execute(sa_sql(
                "ALTER TABLE campaign_uplift_snapshots "
                "ADD CONSTRAINT uq_campaign_uplift_run UNIQUE (campaign_id, run_date)"))
            conn.execute(sa_sql(
                "ALTER TABLE campaign_uplift_snapshots ALTER COLUMN run_at DROP NOT NULL"))
            conn.execute(sa_sql(
                "INSERT INTO campaign_uplift_snapshots "
                "(shop_id, campaign_id, run_date, run_at, spend_uplift_pct, direction, "
                " treatment_n, control_n, created_at) "
                "VALUES (1, :cid, '2024-05-01', NULL, 1.0, 'neutral', 2, 2, "
                "        '2024-05-01T04:00:00')"), {"cid": c.id})
            conn.commit()

        migrate.run_migrations(engine, models.Base.metadata)

        with engine.connect() as conn:
            # Constraint is weg …
            n = conn.execute(sa_sql(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_campaign_uplift_run'"
            )).scalar()
            assert n == 0
            # … en run_at is deterministisch gebackfilld vanaf created_at
            run_at = conn.execute(sa_sql(
                "SELECT run_at FROM campaign_uplift_snapshots "
                "WHERE campaign_id = :cid AND run_date = '2024-05-01'"), {"cid": c.id}
            ).scalar()
            assert run_at is not None and str(run_at).startswith("2024-05-01 04:00:00")

        # Meerdere runs op dezelfde dag zijn nu toegestaan
        li.publish_campaign_uplift_signals(s)
        s.commit()
        li.publish_campaign_uplift_signals(s)
        s.commit()
        today_count = s.query(models.CampaignUpliftSnapshot).filter_by(
            campaign_id=c.id, run_date=date.today()).count()
        assert today_count == 2
    finally:
        _cleanup_campaign(c.id)
