"""
Regressietests voor puntenverloop (taak: stille regressies in puntenverloop):
- apply_expiry_run: vervalcutoff klopt, FIFO-consumptie is correct, tweede run
  op dezelfde dag schrijft geen dubbele entries (idempotentie via external_ref),
  saldo daalt nooit onder nul, dry_run muteert niets, uitgeschakeld beleid is
  een no-op.
- expiring_soon_members: leden binnen het waarschuwingsvenster verschijnen,
  leden erbuiten (te nieuw of al verlopen) niet.

Aanvulling op tests/test_loyalty_ledger.py (apply_ledger_entry) en
tests/test_loyalty_intelligence.py (integriteit/CVS). Draait tegen de
dev-database; alle testdata wordt na afloop opgeruimd.
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
from sqlalchemy import text as sa_text

EXPIRY_MONTHS = 12
WARN_DAYS = 30
EXPIRY_DAYS = EXPIRY_MONTHS * 30  # engine rekent met maanden × 30 dagen


def _cleanup_member_ids(mids):
    s = SessionLocal()
    try:
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


@pytest.fixture()
def policy(db):
    """Zorg voor een bekend, ingeschakeld verloopbeleid; herstel na afloop."""
    s, _ = db
    if not s.query(models.DimShop).filter(models.DimShop.id == 1).first():
        s.execute(sa_text(
            "INSERT INTO dim_shop (id, shop_code, name) "
            "VALUES (1, 'default', 'Default Shop') "
            "ON CONFLICT (id) DO NOTHING"
        ))
        s.commit()
    p = s.query(models.LoyaltyExpiryPolicy).filter(
        models.LoyaltyExpiryPolicy.shop_id == 1).first()
    original = None
    if p:
        original = (p.enabled, p.expiry_months, p.warn_days_before)
        p.enabled = True
        p.expiry_months = EXPIRY_MONTHS
        p.warn_days_before = WARN_DAYS
    else:
        p = models.LoyaltyExpiryPolicy(
            shop_id=1, enabled=True,
            expiry_months=EXPIRY_MONTHS, warn_days_before=WARN_DAYS,
        )
        s.add(p)
    s.commit()
    yield p
    restore = SessionLocal()
    try:
        rp = restore.query(models.LoyaltyExpiryPolicy).filter(
            models.LoyaltyExpiryPolicy.shop_id == 1).first()
        if rp:
            if original:
                rp.enabled, rp.expiry_months, rp.warn_days_before = original
                restore.commit()
            else:
                restore.delete(rp)
                restore.commit()
    finally:
        restore.close()


def _make_member(s, created_ids):
    m = models.LoyaltyMember(
        shop_id=1,
        pseudonymous_customer_id=f"TEST-EXPIRY-{uuid.uuid4().hex[:8]}",
        tier_code="bronze", status="active", is_demo_data=False,
    )
    s.add(m)
    s.commit()
    created_ids.append(m.id)
    return m


def _expire_txns(s, member_id):
    return s.query(models.LoyaltyTransaction).filter(
        models.LoyaltyTransaction.member_id == member_id,
        models.LoyaltyTransaction.txn_type == "expire",
    ).all()


def _integrity_ok_for(s, mids):
    mismatches = li.verify_ledger_integrity(s)
    return [mm for mm in mismatches if mm["member_id"] in mids]


def test_expiry_cutoff_and_fifo_consumption(db, policy):
    """Alleen punten ouder dan de cutoff vervallen; redeems consumeren FIFO
    eerst de oudste punten, dus die tellen niet nogmaals mee in het verloop."""
    s, created = db
    m = _make_member(s, created)
    today = date.today()

    # 1000 punten ruim over de vervalgrens, 500 recente punten.
    li.apply_ledger_entry(s, m, today - timedelta(days=EXPIRY_DAYS + 40), "earn", 1000)
    li.apply_ledger_entry(s, m, today - timedelta(days=10), "earn", 500)
    # FIFO: deze redeem consumeert 300 van de óudste punten.
    li.apply_ledger_entry(s, m, today - timedelta(days=5), "redeem", -300)
    s.commit()

    summary = li.apply_expiry_run(s, run_date=today)
    s.commit()

    # Cutoff in de samenvatting klopt met het beleid.
    assert summary["policy_enabled"] is True
    assert summary["expiry_cutoff"] == (today - timedelta(days=EXPIRY_DAYS)).isoformat()

    # 1000 oud − 300 FIFO-geconsumeerd = 700 vervallen; recente 500 blijven staan.
    txns = _expire_txns(s, m.id)
    assert len(txns) == 1
    assert txns[0].points_delta == -700
    wallet = li.ensure_wallet(s, m.id)
    assert wallet.balance_points == 500
    assert wallet.lifetime_expired == 700
    assert _integrity_ok_for(s, {m.id}) == []


def test_second_run_same_day_is_idempotent(db, policy):
    """Een tweede run op dezelfde dag schrijft geen dubbele expire-entries
    (external_ref = expiry-<lid>-<maand>)."""
    s, created = db
    m = _make_member(s, created)
    today = date.today()
    li.apply_ledger_entry(s, m, today - timedelta(days=EXPIRY_DAYS + 20), "earn", 400)
    s.commit()

    first = li.apply_expiry_run(s, run_date=today)
    s.commit()
    assert len(_expire_txns(s, m.id)) == 1

    # Tweede run: _fifo_expirable_points ziet niets meer (al verlopen), en zelfs
    # als er iets over zou blijven, blokkeert de external_ref een dubbele entry.
    second = li.apply_expiry_run(s, run_date=today)
    s.commit()

    txns = _expire_txns(s, m.id)
    assert len(txns) == 1, "tweede run mag geen extra expire-entry schrijven"
    assert txns[0].points_delta == -400
    wallet = li.ensure_wallet(s, m.id)
    assert wallet.balance_points == 0
    assert wallet.lifetime_expired == 400
    assert first["points_expired"] >= 400
    # Geen dubbele boekingen in run 2 voor dit lid.
    assert _integrity_ok_for(s, {m.id}) == []
    assert second["errors"] == 0


def test_balance_never_goes_negative(db, policy):
    """Verloop is begrensd op het actuele saldo: ook na zware redemptions of
    correcties kan het saldo nooit onder nul komen."""
    s, created = db
    today = date.today()

    # Lid 1: bijna alles al ingewisseld.
    m1 = _make_member(s, created)
    li.apply_ledger_entry(s, m1, today - timedelta(days=EXPIRY_DAYS + 30), "earn", 1000)
    li.apply_ledger_entry(s, m1, today - timedelta(days=50), "redeem", -900)
    # Lid 2: negatieve handmatige correctie.
    m2 = _make_member(s, created)
    li.apply_ledger_entry(s, m2, today - timedelta(days=EXPIRY_DAYS + 30), "earn", 1000)
    li.apply_ledger_entry(s, m2, today - timedelta(days=40), "adjust", -950)
    s.commit()

    li.apply_expiry_run(s, run_date=today)
    s.commit()

    for m, expected_expire in ((m1, 100), (m2, 50)):
        wallet = li.ensure_wallet(s, m.id)
        assert wallet.balance_points >= 0
        assert wallet.balance_points == 0
        txns = _expire_txns(s, m.id)
        assert len(txns) == 1
        assert txns[0].points_delta == -expected_expire
    assert _integrity_ok_for(s, {m1.id, m2.id}) == []


def test_dry_run_writes_nothing(db, policy):
    s, created = db
    m = _make_member(s, created)
    today = date.today()
    li.apply_ledger_entry(s, m, today - timedelta(days=EXPIRY_DAYS + 15), "earn", 250)
    s.commit()

    summary = li.apply_expiry_run(s, run_date=today, dry_run=True)
    s.commit()

    assert summary["dry_run"] is True
    assert summary["points_expired"] >= 250  # gerapporteerd…
    assert _expire_txns(s, m.id) == []       # …maar niets geschreven
    wallet = li.ensure_wallet(s, m.id)
    assert wallet.balance_points == 250
    assert (wallet.lifetime_expired or 0) == 0


def test_disabled_policy_is_noop(db, policy):
    s, created = db
    m = _make_member(s, created)
    today = date.today()
    li.apply_ledger_entry(s, m, today - timedelta(days=EXPIRY_DAYS + 15), "earn", 300)
    policy.enabled = False
    s.commit()

    summary = li.apply_expiry_run(s, run_date=today)
    s.commit()

    assert summary["policy_enabled"] is False
    assert summary["points_expired"] == 0
    assert _expire_txns(s, m.id) == []
    assert li.ensure_wallet(s, m.id).balance_points == 300


def test_expiring_soon_members_window(db, policy):
    """Leden met punten binnen het waarschuwingsvenster verschijnen; te nieuwe
    punten vallen erbuiten. Punten die de vervalgrens al gepasseerd zijn maar
    nog niet formeel verlopen tellen óók mee (ze vervallen bij de
    eerstvolgende expiry-run) — consistent met de liability-cijfers."""
    s, created = db
    today = date.today()

    # Binnen het venster: verdiend tussen (360d, 330d) geleden.
    m_soon = _make_member(s, created)
    li.apply_ledger_entry(
        s, m_soon, today - timedelta(days=EXPIRY_DAYS - WARN_DAYS + 10), "earn", 600)
    # Te nieuw: pas over maanden aan de beurt.
    m_fresh = _make_member(s, created)
    li.apply_ledger_entry(s, m_fresh, today - timedelta(days=100), "earn", 600)
    # Al over de vervalgrens maar nog niet verlopen: telt mee als
    # 'binnenkort verlopend' totdat de expiry-run de punten formeel laat vervallen.
    m_late = _make_member(s, created)
    li.apply_ledger_entry(s, m_late, today - timedelta(days=EXPIRY_DAYS + 40), "earn", 600)
    s.commit()

    rows = {r["member_id"]: r for r in li.expiring_soon_members(s)}

    assert m_soon.id in rows
    row = rows[m_soon.id]
    assert row["points_expiring"] == 600
    assert row["expires_on"] is not None
    assert 0 <= row["days_until_expiry"] <= WARN_DAYS
    assert row["points_expiring_eur"] == round(600 * li.POINT_VALUE_EUR, 2)

    assert m_fresh.id not in rows, "te nieuwe punten horen niet in het waarschuwingsvenster"
    # Al-overdue punten blijven zichtbaar tot de expiry-run ze laat vervallen.
    assert m_late.id in rows
    assert rows[m_late.id]["points_expiring"] == 600
    # Overdue punten hebben geen zinvolle toekomstige vervaldatum meer:
    # de engine begrenst de schatting op het waarschuwingsvenster.
    assert rows[m_late.id]["expires_on"] is None

def test_expiring_soon_overdue_plus_window_gets_past_expiry(db, policy):
    """Een lid met zowel levende overdue-punten als punten binnen het
    waarschuwingsvenster krijgt een geschatte vervaldatum in het verleden:
    de overdue punten vervallen bij de eerstvolgende expiry-run en bepalen
    FIFO de prioritering (days_until_expiry <= 0)."""
    s, created = db
    today = date.today()

    m = _make_member(s, created)
    # Overdue: al over de vervalgrens, nog niet formeel verlopen.
    li.apply_ledger_entry(s, m, today - timedelta(days=EXPIRY_DAYS + 40), "earn", 400)
    # Binnen het waarschuwingsvenster.
    li.apply_ledger_entry(
        s, m, today - timedelta(days=EXPIRY_DAYS - WARN_DAYS + 10), "earn", 300)
    s.commit()

    rows = {r["member_id"]: r for r in li.expiring_soon_members(s)}
    assert m.id in rows
    row = rows[m.id]
    assert row["points_expiring"] == 700
    assert row["expires_on"] is not None
    assert row["days_until_expiry"] <= 0

    # FIFO: zodra de overdue punten volledig zijn ingewisseld, telt weer de
    # window-earn en ligt de geschatte vervaldatum in de toekomst.
    li.apply_ledger_entry(s, m, today - timedelta(days=5), "redeem", -400)
    s.commit()
    rows = {r["member_id"]: r for r in li.expiring_soon_members(s)}
    assert m.id in rows
    assert rows[m.id]["points_expiring"] == 300
    assert rows[m.id]["days_until_expiry"] is not None
    assert 0 <= rows[m.id]["days_until_expiry"] <= WARN_DAYS


def test_liability_summary_unscoped_uses_each_shops_policy(db, policy):
    """Ongescoped liability (dashboard zonder shop_id) moet per shop het eigen
    verloopbeleid toepassen: een shop met kortere looptijd telt volgens dat
    kortere beleid mee, een shop met uitgeschakeld beleid telt niet mee —
    nooit shop 1-beleid op andere shops."""
    s, created = db
    today = date.today()

    shop_b = models.DimShop(shop_code=f"lty-b-{uuid.uuid4().hex[:6]}", name="Loyalty B")
    shop_c = models.DimShop(shop_code=f"lty-c-{uuid.uuid4().hex[:6]}", name="Loyalty C")
    s.add_all([shop_b, shop_c])
    s.commit()
    pol_b = models.LoyaltyExpiryPolicy(
        shop_id=shop_b.id, enabled=True, expiry_months=6, warn_days_before=WARN_DAYS)
    pol_c = models.LoyaltyExpiryPolicy(
        shop_id=shop_c.id, enabled=False, expiry_months=EXPIRY_MONTHS,
        warn_days_before=WARN_DAYS)
    s.add_all([pol_b, pol_c])
    s.commit()
    try:
        before = li.liability_summary(s)

        def _member(shop):
            m = models.LoyaltyMember(
                shop_id=shop.id,
                pseudonymous_customer_id=f"TEST-EXPIRY-{uuid.uuid4().hex[:8]}",
                tier_code="bronze", status="active", is_demo_data=False,
            )
            s.add(m)
            s.commit()
            created.append(m.id)
            return m

        # Shop B (6 mnd): earn 200 dagen geleden → overdue onder B's beleid,
        # maar ruim binnen de 12 maanden van shop 1 — telt alleen mee als B's
        # eigen beleid wordt toegepast.
        m_b = _member(shop_b)
        li.apply_ledger_entry(s, m_b, today - timedelta(days=200), "earn", 500)
        # Shop C (uitgeschakeld): overdue punten mogen nergens meetellen.
        m_c = _member(shop_c)
        li.apply_ledger_entry(s, m_c, today - timedelta(days=400), "earn", 700)
        s.commit()

        after = li.liability_summary(s)
        assert after["points_expiring_90d"] - before["points_expiring_90d"] == 500
        assert after["points_expiring_30d"] - before["points_expiring_30d"] == 500
        delta = [a["points"] - b["points"]
                 for a, b in zip(after["expiry_forecast"], before["expiry_forecast"])]
        # Overdue punten van shop B vallen in de eerste maand; shop C telt niet mee.
        assert delta[0] == 500
        assert sum(delta) == 500
    finally:
        s.rollback()
        s.query(models.LoyaltyExpiryPolicy).filter(
            models.LoyaltyExpiryPolicy.shop_id.in_([shop_b.id, shop_c.id])
        ).delete(synchronize_session=False)
        _cleanup_member_ids(list(created))
        del created[:]
        s.query(models.DimShop).filter(
            models.DimShop.id.in_([shop_b.id, shop_c.id])
        ).delete(synchronize_session=False)
        s.commit()


def test_expiring_soon_respects_fifo_redeems(db, policy):
    """Redeems consumeren FIFO eerst de window-punten als er niets ouders is:
    het waarschuwingsbedrag daalt mee."""
    s, created = db
    today = date.today()
    m = _make_member(s, created)
    li.apply_ledger_entry(
        s, m, today - timedelta(days=EXPIRY_DAYS - WARN_DAYS + 5), "earn", 500)
    li.apply_ledger_entry(s, m, today - timedelta(days=20), "redeem", -200)
    s.commit()

    rows = {r["member_id"]: r for r in li.expiring_soon_members(s)}
    assert m.id in rows
    assert rows[m.id]["points_expiring"] == 300
