"""
Integratietests voor de loyalty-ledger (taak: Loyalty & Customer Value):
tekenregels per txn_type, negatieve-saldobescherming, idempotente
external_refs (ook binnen één batch) en gelijktijdige redemptions.
Draait tegen de dev-database; alle testdata wordt na afloop opgeruimd.
"""
import os
import sys
import threading
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
from engine import loyalty_intelligence as li


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    try:
        s.rollback()
        s.close()
    except Exception:
        pass


@pytest.fixture()
def member(db):
    pid = f"TEST-LEDGER-{uuid.uuid4().hex[:8]}"
    m = models.LoyaltyMember(
        shop_id=1, pseudonymous_customer_id=pid, tier_code="bronze",
        status="active", is_demo_data=False,
    )
    db.add(m)
    db.commit()
    mid = m.id
    yield m
    db.rollback()
    db.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(models.LoyaltyTransaction).filter_by(member_id=mid).delete()
        cleanup.query(models.LoyaltyWallet).filter_by(member_id=mid).delete()
        cleanup.query(models.LoyaltyMember).filter_by(id=mid).delete()
        cleanup.commit()
    finally:
        cleanup.close()


def test_sign_rules_enforced(db, member):
    # Positieve redeem is boekhoudkundig fout en moet geweigerd worden.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "redeem", 100)
    # Negatieve earn eveneens.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "earn", -100)
    # Positieve expire eveneens.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "expire", 50)
    # Onbekend type geweigerd.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "bogus", 10)
    # Nul geweigerd.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "adjust", 0)
    db.rollback()
    # Geldige mutaties slagen; adjust mag beide kanten op.
    li.apply_ledger_entry(db, member, date.today(), "earn", 200)
    li.apply_ledger_entry(db, member, date.today(), "adjust", -50)
    li.apply_ledger_entry(db, member, date.today(), "redeem", -100)
    db.commit()
    wallet = li.ensure_wallet(db, member.id)
    assert wallet.balance_points == 50
    assert wallet.lifetime_earned == 200
    assert wallet.lifetime_redeemed == 150  # adjust(-50) + redeem(-100)
    mismatches = [x for x in li.verify_ledger_integrity(db) if x["member_id"] == member.id]
    assert mismatches == []


def test_negative_balance_blocked(db, member):
    li.apply_ledger_entry(db, member, date.today(), "earn", 100)
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "redeem", -101)
    db.rollback()
    wallet = li.ensure_wallet(db, member.id)
    assert (wallet.balance_points or 0) >= 0


def test_duplicate_external_ref_same_batch(db, member):
    ref = f"REF-{uuid.uuid4().hex[:8]}"
    li.apply_ledger_entry(db, member, date.today(), "earn", 100, external_ref=ref)
    # Zelfde batch (zelfde sessie, nog niet gecommit) — moet al geweigerd worden.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "earn", 100, external_ref=ref)
    db.commit()
    # En ook na commit.
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "earn", 100, external_ref=ref)
    db.rollback()
    wallet = li.ensure_wallet(db, member.id)
    assert wallet.balance_points == 100


def test_concurrent_duplicate_external_ref(member):
    """Twee gelijktijdige leveringen met dezelfde external_ref: precies één
    ledger-rij mag ontstaan (unieke index + duplicate-check na wallet-lock)."""
    ref = f"CONC-DUP-{uuid.uuid4().hex[:8]}"
    barrier = threading.Barrier(2)
    results = []

    def deliver(tag):
        s = SessionLocal()
        try:
            m = s.get(models.LoyaltyMember, member.id)
            barrier.wait(timeout=10)
            li.apply_ledger_entry(
                s, m, date.today(), "earn", 250, external_ref=ref, commit=True)
            results.append(("ok", tag))
        except li.LedgerError:
            s.rollback()
            results.append(("refused", tag))
        except Exception as e:
            s.rollback()
            results.append((f"unexpected:{type(e).__name__}", tag))
        finally:
            s.close()

    threads = [threading.Thread(target=deliver, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"threads niet afgerond: {results}"
    assert all(r in ("ok", "refused") for r, _ in results), f"onverwachte fout: {results}"
    ok_count = sum(1 for r, _ in results if r == "ok")
    assert ok_count == 1, f"verwacht precies 1 geslaagde levering, kreeg {results}"

    check = SessionLocal()
    try:
        rows = check.query(models.LoyaltyTransaction).filter_by(
            member_id=member.id, external_ref=ref).count()
        assert rows == 1
        wallet = li.ensure_wallet(check, member.id)
        assert wallet.balance_points == 250
        assert wallet.lifetime_earned == 250
        mismatches = [x for x in li.verify_ledger_integrity(check) if x["member_id"] == member.id]
        assert mismatches == []
    finally:
        check.close()


def test_concurrent_redemptions_cannot_overspend(member):
    """Twee gelijktijdige redemptions van elk 400 op een saldo van 500:
    precies één mag slagen (row-lock op de wallet)."""
    setup = SessionLocal()
    try:
        m = setup.get(models.LoyaltyMember, member.id)
        li.apply_ledger_entry(setup, m, date.today(), "earn", 500, commit=True)
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results = []

    def redeem(tag):
        s = SessionLocal()
        try:
            m = s.get(models.LoyaltyMember, member.id)
            barrier.wait(timeout=10)
            li.apply_ledger_entry(
                s, m, date.today(), "redeem", -400,
                external_ref=f"CONC-{tag}-{uuid.uuid4().hex[:6]}", commit=True)
            results.append(("ok", tag))
        except li.LedgerError:
            s.rollback()
            results.append(("refused", tag))
        except Exception as e:
            s.rollback()
            results.append((f"unexpected:{type(e).__name__}", tag))
        finally:
            s.close()

    threads = [threading.Thread(target=redeem, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"threads niet afgerond: {results}"
    assert all(r in ("ok", "refused") for r, _ in results), f"onverwachte fout: {results}"
    ok_count = sum(1 for r, _ in results if r == "ok")
    assert ok_count == 1, f"verwacht precies 1 geslaagde redemption, kreeg {results}"

    check = SessionLocal()
    try:
        wallet = li.ensure_wallet(check, member.id)
        assert wallet.balance_points == 100
        mismatches = [x for x in li.verify_ledger_integrity(check) if x["member_id"] == member.id]
        assert mismatches == []
    finally:
        check.close()


def test_duplicate_then_valid_row_in_same_batch(db, member):
    """
    Regressietest voor het savepoint-gedrag: een duplicate external_ref midden
    in een batch mag de omliggende transactie NIET als mislukt markeren.
    Een geldige rij ná de duplicate moet gewoon nog committen — precies het
    gedrag waarop de CSV-import (catch LedgerError → continue) leunt.
    """
    ref = f"BATCH-{uuid.uuid4().hex[:8]}"
    li.apply_ledger_entry(db, member, date.today(), "earn", 100, external_ref=ref)
    # Duplicate in dezelfde (batch)transactie → idempotente LedgerError
    with pytest.raises(li.LedgerError):
        li.apply_ledger_entry(db, member, date.today(), "earn", 100, external_ref=ref)
    # Sessie is nog gezond: geldige vervolgrij + commit slagen
    li.apply_ledger_entry(db, member, date.today(), "earn", 50,
                          external_ref=f"BATCH-{uuid.uuid4().hex[:8]}")
    db.commit()
    wallet = li.ensure_wallet(db, member.id)
    assert wallet.balance_points == 150
    assert db.query(models.LoyaltyTransaction).filter_by(member_id=member.id).count() == 2


def test_upload_batch_survives_duplicate_row():
    """End-to-end: CSV-upload met duplicate external_ref tussen geldige rijen —
    de upload slaagt, alleen de duplicate faalt."""
    from routes.uploads import _process_loyalty_transactions
    s = SessionLocal()
    pid = f"TEST-UPL-{uuid.uuid4().hex[:8]}"
    m = models.LoyaltyMember(shop_id=1, pseudonymous_customer_id=pid,
                             tier_code="bronze", status="active", is_demo_data=False)
    s.add(m)
    s.commit()
    ref = f"UPL-{uuid.uuid4().hex[:8]}"
    rows = [
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": str(date.today()), "points_delta": "100", "external_ref": ref},
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": str(date.today()), "points_delta": "100", "external_ref": ref},
        {"pseudonymous_customer_id": pid, "txn_type": "earn", "date": str(date.today()), "points_delta": "25", "external_ref": f"UPL-{uuid.uuid4().hex[:8]}"},
    ]
    try:
        processed, failed, warnings = _process_loyalty_transactions(rows, s)
        assert processed == 2 and failed == 1
        assert any("Dubbele transactie" in w for w in warnings)
        wallet = li.ensure_wallet(s, m.id)
        assert wallet.balance_points == 125
    finally:
        s.rollback()
        mid = m.id
        s.query(models.LoyaltyTransaction).filter_by(member_id=mid).delete()
        s.query(models.LoyaltyWallet).filter_by(member_id=mid).delete()
        s.query(models.LoyaltyMember).filter_by(id=mid).delete()
        s.commit()
        s.close()


def test_expiry_forecast_monthly_buckets(db, member):
    """Punten die over ~45 dagen de vervalgrens passeren, verschijnen in de
    juiste maand-bucket van de verloopcurve (delta t.o.v. baseline)."""
    from datetime import timedelta

    policy = li._get_expiry_policy(db)
    assert policy.enabled
    horizon = policy.expiry_months * 30

    before = li._expiry_forecast_monthly(db, policy, months=6)

    # Verdiend zó dat het verloop over ~45 dagen valt
    earn_date = date.today() - timedelta(days=horizon - 45)
    li.apply_ledger_entry(db, member, earn_date, "earn", 777,
                          external_ref=f"forecast-test-{member.id}")

    after = li._expiry_forecast_monthly(db, policy, months=6)

    assert len(after) == 6
    assert all(f["points"] >= 0 for f in after)
    deltas = [a["points"] - b["points"] for a, b in zip(after, before)]
    assert sum(deltas) == 777
    # De 777 punten vallen in één van de eerste drie maanden (rond dag 45)
    assert sum(deltas[:3]) == 777
    # EUR-waarde consistent met puntwaarde
    for f in after:
        assert f["eur"] == round(f["points"] * li.POINT_VALUE_EUR, 2)


def test_expiry_forecast_boundary_matches_expiry_run(db, member):
    """Een credit gedateerd exact month_end - horizon valt in de bucket van de
    VOLGENDE maand, consistent met apply_expiry_run (txn_date < run_date - horizon)."""
    from datetime import timedelta

    policy = li._get_expiry_policy(db)
    horizon = policy.expiry_months * 30
    today = date.today()
    month_end = li._month_end(today)

    before = li._expiry_forecast_monthly(db, policy, months=6)
    li.apply_ledger_entry(db, member, month_end - timedelta(days=horizon),
                          "earn", 555,
                          external_ref=f"forecast-boundary-{member.id}")
    after = li._expiry_forecast_monthly(db, policy, months=6)
    deltas = [a["points"] - b["points"] for a, b in zip(after, before)]

    # Niet in de huidige maand: een expiry-run op month_end laat deze punten staan
    assert deltas[0] == 0
    assert deltas[1] == 555

    # Consistentie met de echte expiry-run (dry_run): op month_end nog niets,
    # op de eerste dag van de volgende maand wél.
    wallet = li.ensure_wallet(db, member.id)
    assert li._fifo_expirable_points(db, member.id, wallet,
                                     month_end - timedelta(days=horizon)) == 0
    next_day = month_end + timedelta(days=1)
    assert li._fifo_expirable_points(db, member.id, wallet,
                                     next_day - timedelta(days=horizon)) == 555


def test_expiry_forecast_query_count_bounded(db, member):
    """De verloopcurve mag een vast, klein aantal queries gebruiken,
    onafhankelijk van het aantal wallets (set-based, geen per-wallet loop)."""
    from datetime import timedelta
    from sqlalchemy import event

    policy = li._get_expiry_policy(db)
    horizon = policy.expiry_months * 30
    li.apply_ledger_entry(db, member, date.today() - timedelta(days=horizon - 40),
                          "earn", 100, external_ref=f"forecast-qc-{member.id}")

    counter = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        li._expiry_forecast_monthly(db, policy, months=6)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # 1 wallet-query + 1 gegroepeerde credit-query (+ evt. beleidsquery-marge)
    assert counter["n"] <= 5, (
        f"Verloopcurve gebruikte {counter['n']} SELECT-queries; verwacht een "
        "vast klein aantal onafhankelijk van het aantal wallets"
    )


def test_expiry_forecast_six_ordered_buckets_and_overdue(db, member):
    """De curve heeft exact zes oplopende maand-buckets; punten die de
    vervalgrens al gepasseerd zijn (overdue) vallen in de eerste bucket."""
    from datetime import timedelta

    policy = li._get_expiry_policy(db)
    horizon = policy.expiry_months * 30

    before = li._expiry_forecast_monthly(db, policy, months=6)
    assert len(before) == 6
    months = [f["month"] for f in before]
    assert months == sorted(months) and len(set(months)) == 6
    for f in before:
        assert set(f) >= {"month", "label", "points", "eur"}

    # Overdue: al 10 dagen over de grens — vervalt bij de eerstvolgende run,
    # dus telt in de eerste maand-bucket.
    li.apply_ledger_entry(db, member, date.today() - timedelta(days=horizon + 10),
                          "earn", 321, external_ref=f"forecast-overdue-{member.id}")
    after = li._expiry_forecast_monthly(db, policy, months=6)
    deltas = [a["points"] - b["points"] for a, b in zip(after, before)]
    assert deltas[0] == 321 and sum(deltas[1:]) == 0


def test_expiry_forecast_fifo_redeems_reduce_buckets(db, member):
    """Redeems consumeren FIFO de oudste punten: een redeem verlaagt de
    verloopcurve, want de oudste (eerst vervallende) punten zijn al op."""
    from datetime import timedelta

    policy = li._get_expiry_policy(db)
    horizon = policy.expiry_months * 30

    before = li._expiry_forecast_monthly(db, policy, months=6)
    li.apply_ledger_entry(db, member, date.today() - timedelta(days=horizon - 40),
                          "earn", 500, external_ref=f"forecast-fifo-earn-{member.id}")
    li.apply_ledger_entry(db, member, date.today(), "redeem", -200,
                          external_ref=f"forecast-fifo-redeem-{member.id}")
    after = li._expiry_forecast_monthly(db, policy, months=6)
    deltas = [a["points"] - b["points"] for a, b in zip(after, before)]
    # Van de 500 blijft na de FIFO-redeem van 200 nog 300 te vervallen over.
    assert sum(deltas) == 300


def test_expiry_forecast_disabled_policy_empty(db):
    """Bij een uitgeschakeld verloopbeleid bevat liability_summary een lege
    verloopcurve (geen speculatieve buckets)."""
    # Residu-bestendig (shared test-DB): andere tests kunnen shops met een
    # eigen enabled verloopbeleid achterlaten; het ongescopete dashboard
    # aggregeert over álle loyalty-shops. Schakel daarom elk beleid uit.
    policies = [li._get_expiry_policy(db, sid) for sid in li._loyalty_shop_ids(db)]
    policies.append(li._get_expiry_policy(db))
    try:
        for p in policies:
            p.enabled = False
        db.flush()
        summary = li.liability_summary(db)
        assert summary["expiry_forecast"] == []
    finally:
        db.rollback()
