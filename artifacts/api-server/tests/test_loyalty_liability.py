"""
Regressietests voor de financiële liability-cijfers en het FIFO-puntenverloop
(taak: bevestig dat liability- en puntenverloopcijfers correct blijven na
modelwijzigingen):

- liability_summary: punten-liability (outstanding × POINT_VALUE_EUR),
  voucher-liability (alleen status 'issued'), vouchers_expiring_30d,
  points_expiring_30d/90d en de expiry_policy-velden.
- _fifo_expirable_points: inwisselingen consumeren de oudste punten eerst;
  al-verlopen punten tellen niet dubbel; saldo is de bovengrens.

Aanvulling op tests/test_loyalty_ledger.py en tests/test_loyalty_intelligence.py.
Draait tegen de dev-database; liability_summary is globaal, dus die tests
werken met vóór/na-delta's. Alle testdata wordt na afloop opgeruimd.
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal, engine, Base
import models
from engine import loyalty_intelligence as li


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_schema():
    """Zorg dat tabellen en de default shop (id=1) bestaan in een verse DB."""
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        if not s.query(models.DimShop).filter(models.DimShop.id == 1).first():
            s.add(models.DimShop(id=1, shop_code="default", name="Default Shop"))
            s.commit()
    finally:
        s.close()


def _cleanup_member_ids(mids):
    s = SessionLocal()
    try:
        s.query(models.LoyaltyVoucher).filter(
            models.LoyaltyVoucher.member_id.in_(mids)).delete(synchronize_session=False)
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


def _mk_member(s, created_ids):
    m = models.LoyaltyMember(
        shop_id=1,
        pseudonymous_customer_id=f"TEST-LIAB-{uuid.uuid4().hex[:10]}",
        tier_code="bronze", status="active", is_demo_data=False,
    )
    s.add(m)
    s.commit()
    created_ids.append(m.id)
    return m


def _earn(s, m, txn_date, points):
    li.apply_ledger_entry(
        s, m, txn_date, "earn", points,
        external_ref=f"LIAB-{uuid.uuid4().hex[:10]}", commit=True)


# ─── liability_summary ───────────────────────────────────────────────────────

def test_liability_summary_points_and_vouchers(db):
    s, ids = db
    before = li.liability_summary(s)

    m = _mk_member(s, ids)
    _earn(s, m, date.today(), 500)

    # Vouchers: issued (telt), issued & bijna verlopen (telt + expiring),
    # used (telt niet).
    today = date.today()
    vouchers = [
        models.LoyaltyVoucher(
            shop_id=1, member_id=m.id, code=f"TV-{uuid.uuid4().hex[:10]}",
            monetary_value=10.0, status="issued", issued_at=today,
            expires_at=today + timedelta(days=365)),
        models.LoyaltyVoucher(
            shop_id=1, member_id=m.id, code=f"TV-{uuid.uuid4().hex[:10]}",
            monetary_value=7.5, status="issued", issued_at=today,
            expires_at=today + timedelta(days=10)),
        models.LoyaltyVoucher(
            shop_id=1, member_id=m.id, code=f"TV-{uuid.uuid4().hex[:10]}",
            monetary_value=99.0, status="used", issued_at=today,
            used_at=today, expires_at=today + timedelta(days=5)),
    ]
    s.add_all(vouchers)
    s.commit()

    after = li.liability_summary(s)

    assert after["outstanding_points"] - before["outstanding_points"] == 500
    assert after["point_value_eur"] == li.POINT_VALUE_EUR
    assert after["points_liability_eur"] - before["points_liability_eur"] == pytest.approx(
        500 * li.POINT_VALUE_EUR, abs=0.01)
    assert after["open_vouchers"] - before["open_vouchers"] == 2  # used telt niet
    assert after["voucher_liability_eur"] - before["voucher_liability_eur"] == pytest.approx(17.5, abs=0.01)
    assert after["vouchers_expiring_30d"] - before["vouchers_expiring_30d"] == 1
    # total = punten + vouchers, consistent binnen dezelfde snapshot
    assert after["total_liability_eur"] == pytest.approx(
        after["points_liability_eur"] + after["voucher_liability_eur"], abs=0.01)
    # Beleidsvelden aanwezig
    assert set(after["expiry_policy"]) == {"enabled", "expiry_months", "warn_days_before"}


def test_liability_summary_points_expiring_windows(db):
    s, ids = db
    policy = li._get_expiry_policy(s)
    if not policy.enabled:
        pytest.skip("verloopbeleid staat uit in deze database")

    before = li.liability_summary(s)

    m = _mk_member(s, ids)
    # Punten die over ±10 dagen verlopen: vallen zowel in het 30d- als het
    # 90d-venster.
    almost_expired = date.today() - timedelta(days=policy.expiry_months * 30 - 10)
    _earn(s, m, almost_expired, 120)
    # Verse punten: verlopen in geen van beide vensters.
    _earn(s, m, date.today(), 80)

    after = li.liability_summary(s)
    assert after["points_expiring_30d"] - before["points_expiring_30d"] == 120
    assert after["points_expiring_90d"] - before["points_expiring_90d"] == 120


# ─── _fifo_expirable_points ──────────────────────────────────────────────────

def _wallet(s, member_id):
    return li.ensure_wallet(s, member_id)


def test_fifo_redemptions_consume_oldest_first(db):
    s, ids = db
    m = _mk_member(s, ids)
    old = date.today() - timedelta(days=400)
    _earn(s, m, old, 100)
    _earn(s, m, date.today(), 50)
    li.apply_ledger_entry(s, m, date.today(), "redeem", -30, commit=True)

    # FIFO: de 30 ingewisselde punten komen van de oudste 100 → 70 verloopt.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 70


def test_fifo_redemptions_exceeding_old_points(db):
    s, ids = db
    m = _mk_member(s, ids)
    _earn(s, m, date.today() - timedelta(days=400), 100)
    _earn(s, m, date.today(), 50)
    li.apply_ledger_entry(s, m, date.today(), "redeem", -120, commit=True)

    # 120 ingewisseld > 100 oude punten → alle oude punten al geconsumeerd.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 0


def test_fifo_already_expired_points_not_double_counted(db):
    s, ids = db
    m = _mk_member(s, ids)
    _earn(s, m, date.today() - timedelta(days=400), 100)
    li.apply_ledger_entry(s, m, date.today(), "expire", -40, commit=True)

    # 40 punten zijn al verlopen; alleen de resterende 60 mogen nog verlopen.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 60

    # Alles verlopen → niets meer te verlopen (geen dubbeltelling).
    li.apply_ledger_entry(s, m, date.today(), "expire", -60, commit=True)
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 0


def test_fifo_capped_by_balance(db):
    s, ids = db
    m = _mk_member(s, ids)
    _earn(s, m, date.today() - timedelta(days=400), 100)
    li.apply_ledger_entry(s, m, date.today(), "redeem", -90, commit=True)

    # Saldo (10) is de harde bovengrens, ook al zou de FIFO-som hoger uitkomen.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 10
    assert pts <= _wallet(s, m.id).balance_points


def test_fifo_no_old_points(db):
    s, ids = db
    m = _mk_member(s, ids)
    _earn(s, m, date.today(), 200)  # alleen verse punten

    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id), expiry_cutoff=date.today() - timedelta(days=360))
    assert pts == 0


def test_fifo_warn_window_mode(db):
    s, ids = db
    m = _mk_member(s, ids)
    today = date.today()
    cutoff_full = today - timedelta(days=360)
    cutoff_soon = today - timedelta(days=330)  # 30d-waarschuwingsvenster

    _earn(s, m, cutoff_full - timedelta(days=40), 100)  # al over de vervalgrens
    _earn(s, m, cutoff_full + timedelta(days=10), 50)   # verloopt binnenkort
    li.apply_ledger_entry(s, m, today, "redeem", -100, commit=True)

    # FIFO: de redeem consumeert eerst de 100 pre-window-punten;
    # de 50 venster-punten staan dus nog volledig op verlopen.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id),
        expiry_cutoff=cutoff_soon, warn_window_end=cutoff_full)
    assert pts == 50

    # Consumeert de redeem óók een deel van de venster-punten, dan telt
    # alleen de rest.
    li.apply_ledger_entry(s, m, today, "redeem", -20, commit=True)
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id),
        expiry_cutoff=cutoff_soon, warn_window_end=cutoff_full)
    assert pts == 30


def test_fifo_warn_window_counts_overdue_points(db):
    """
    Regressie (taak 160): punten die de vervalgrens al gepasseerd zijn maar
    nog niet formeel verlopen (expiry-run nog niet gedraaid) tellen mee als
    'binnenkort verlopend' in de warn-window-modus.
    """
    s, ids = db
    m = _mk_member(s, ids)
    today = date.today()
    cutoff_full = today - timedelta(days=360)
    cutoff_soon = today - timedelta(days=330)

    _earn(s, m, cutoff_full - timedelta(days=40), 100)  # al over de vervalgrens
    _earn(s, m, cutoff_full + timedelta(days=10), 50)   # verloopt binnenkort
    _earn(s, m, today, 25)                              # vers, telt niet mee

    # Geen redeems: zowel de 100 overdue- als de 50 venster-punten tellen mee.
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id),
        expiry_cutoff=cutoff_soon, warn_window_end=cutoff_full)
    assert pts == 150

    # Een deel van de overdue-punten is al geconsumeerd: de rest telt nog mee.
    li.apply_ledger_entry(s, m, today, "redeem", -60, commit=True)
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id),
        expiry_cutoff=cutoff_soon, warn_window_end=cutoff_full)
    assert pts == 90  # 40 overdue + 50 venster

    # Na een expiry-run zijn de overdue-punten formeel verlopen en tellen
    # alleen de venster-punten nog mee (geen dubbeltelling).
    li.apply_ledger_entry(s, m, today, "expire", -40, commit=True)
    pts = li._fifo_expirable_points(
        s, m.id, _wallet(s, m.id),
        expiry_cutoff=cutoff_soon, warn_window_end=cutoff_full)
    assert pts == 50


def test_liability_summary_includes_overdue_points(db):
    """points_expiring_30d/90d bevatten ook al-overdue-maar-niet-verlopen punten."""
    s, ids = db
    policy = li._get_expiry_policy(s)
    if not policy.enabled:
        pytest.skip("verloopbeleid staat uit in deze database")

    before = li.liability_summary(s)

    m = _mk_member(s, ids)
    # Punten die de vervalgrens al 20 dagen gepasseerd zijn (expiry-run nog niet gedraaid).
    overdue = date.today() - timedelta(days=policy.expiry_months * 30 + 20)
    _earn(s, m, overdue, 200)

    after = li.liability_summary(s)
    assert after["points_expiring_30d"] - before["points_expiring_30d"] == 200
    assert after["points_expiring_90d"] - before["points_expiring_90d"] == 200
