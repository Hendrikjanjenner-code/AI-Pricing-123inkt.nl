"""
Loyalty & Customer Value Intelligence Engine (masterprompt §22, §31, §64.5).

Onderdelen:
- Ledger-integriteit: wallet-saldi muteren uitsluitend via ledger-entries;
  `apply_ledger_entry` is de enige toegestane mutatieroute en blokkeert
  negatieve saldi. `verify_ledger_integrity` controleert saldo == som(ledger).
- Customer Intelligence: RFM, CLV (24m-schatting), churn-risico en retentie
  met confidence en uitleg — op pseudonymous_customer_id, geen PII (§31).
- Next Best Action: per lid een aanbeveling incl. vergelijking met een
  generieke prijsverlaging (§22), gepubliceerd als IntelligenceSignals.
- Financial liability: openstaande punten + uitgegeven vouchers.
- Fraudesignalen: abnormale earn-rates, snelle redemptions, referral-ringen
  en saldo-mismatches.

Er is nog geen live loyalty-databron; de module werkt met CSV/XLSX-import en
expliciet gemarkeerde demodata (is_demo_data=True, §64.5).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)

MODEL_VERSION = "loyalty-v1.0"
# Boekhoudkundige puntwaarde voor liability (EUR per punt).
POINT_VALUE_EUR = 0.01

DEFAULT_TIERS = [
    {"code": "bronze", "name": "Brons", "min_points_12m": 0, "earn_multiplier": 1.0, "rank": 1},
    {"code": "silver", "name": "Zilver", "min_points_12m": 1500, "earn_multiplier": 1.25, "rank": 2},
    {"code": "gold", "name": "Goud", "min_points_12m": 5000, "earn_multiplier": 1.5, "rank": 3},
]


class LedgerError(Exception):
    """Ledger-mutatie geweigerd (bv. negatief saldo of dubbele external_ref)."""


# Tekenregels per transactietype: credits moeten positief zijn, debits
# negatief. 'adjust' mag beide kanten op (handmatige correctie), maar nooit 0.
_CREDIT_TYPES = {"earn", "referral_bonus", "campaign_bonus"}
_DEBIT_TYPES = {"redeem", "expire"}


# ---------------------------------------------------------------------------
# Ledger / wallet
# ---------------------------------------------------------------------------

def ensure_wallet(db: Session, member_id: int, *, for_update: bool = False) -> models.LoyaltyWallet:
    def _query():
        q = db.query(models.LoyaltyWallet).filter(
            models.LoyaltyWallet.member_id == member_id
        )
        if for_update:
            # Row-lock zodat gelijktijdige mutaties elkaar niet kunnen inhalen
            # (twee redemptions die allebei de saldocheck halen).
            q = q.with_for_update()
        return q.first()

    wallet = _query()
    if not wallet:
        # Atomair aanmaken via ON CONFLICT DO NOTHING: bij een race maakt
        # precies één sessie de rij aan en pakt de ander die daarna (gelockt)
        # op — zonder IntegrityError die de sessie zou invalideren.
        db.execute(
            sa_text(
                "INSERT INTO loyalty_wallets (member_id, balance_points, "
                "lifetime_earned, lifetime_redeemed, lifetime_expired) "
                "VALUES (:mid, 0, 0, 0, 0) ON CONFLICT (member_id) DO NOTHING"
            ),
            {"mid": member_id},
        )
        wallet = _query()
        if wallet is None:  # pragma: no cover — zou niet mogen gebeuren
            raise LedgerError(f"Wallet voor lid {member_id} kon niet worden aangemaakt")
    return wallet


def apply_ledger_entry(
    db: Session,
    member: models.LoyaltyMember,
    txn_date: date,
    txn_type: str,
    points_delta: int,
    *,
    order_reference: str | None = None,
    order_value=None,
    description: str | None = None,
    external_ref: str | None = None,
    campaign_id: int | None = None,
    voucher_id: int | None = None,
    is_demo_data: bool = False,
    commit: bool = False,
) -> models.LoyaltyTransaction:
    """
    Enige toegestane route om puntensaldi te muteren: schrijft een
    append-only ledger-entry en werkt het wallet-saldo transactioneel bij.
    Weigert mutaties die het saldo negatief zouden maken en dubbele
    external_refs (idempotente import).
    """
    if points_delta == 0:
        raise LedgerError("points_delta mag niet 0 zijn")
    if txn_type in _CREDIT_TYPES and points_delta < 0:
        raise LedgerError(
            f"txn_type '{txn_type}' vereist positieve punten (kreeg {points_delta})"
        )
    if txn_type in _DEBIT_TYPES and points_delta > 0:
        raise LedgerError(
            f"txn_type '{txn_type}' vereist negatieve punten (kreeg {points_delta})"
        )
    if txn_type not in _CREDIT_TYPES | _DEBIT_TYPES | {"adjust"}:
        raise LedgerError(f"onbekend txn_type '{txn_type}'")

    # Lock de wallet-rij: saldocheck + update gebeuren atomair binnen de
    # transactie, zodat gelijktijdige redemptions niet allebei kunnen slagen.
    wallet = ensure_wallet(db, member.id, for_update=True)

    # Duplicate-check NA het wallet-lock (gelijktijdige leveringen van dezelfde
    # external_ref serialiseren eerst op het lock en zien elkaars rij daarna).
    # De unieke partiële index uq_loyalty_txn_member_external_ref vormt het
    # sluitstuk op databaseniveau; een IntegrityError daarop wordt hieronder
    # als idempotente LedgerError afgehandeld.
    if external_ref:
        dup = db.query(models.LoyaltyTransaction).filter(
            models.LoyaltyTransaction.external_ref == external_ref,
            models.LoyaltyTransaction.member_id == member.id,
        ).first()
        if dup:
            raise LedgerError(f"Dubbele transactie (external_ref={external_ref}) — overgeslagen")
    new_balance = (wallet.balance_points or 0) + points_delta
    if new_balance < 0:
        raise LedgerError(
            f"Saldo zou negatief worden ({wallet.balance_points} {points_delta:+d}) — geweigerd"
        )

    txn = models.LoyaltyTransaction(
        shop_id=member.shop_id or 1,
        member_id=member.id,
        txn_date=txn_date,
        txn_type=txn_type,
        points_delta=points_delta,
        order_reference=order_reference,
        order_value=order_value,
        description=description,
        external_ref=external_ref,
        campaign_id=campaign_id,
        voucher_id=voucher_id,
        is_demo_data=is_demo_data,
    )
    # Voeg de ledger-rij toe en flush die volledig BINNEN een savepoint: de
    # add moet ná begin_nested() gebeuren, anders kan de flush die het
    # savepoint opzet de pending rij al buiten het savepoint wegschrijven en
    # markeert een IntegrityError op de unieke partiële index
    # (member_id, external_ref) de héle omliggende (batch)transactie als
    # mislukt. Binnen het savepoint komt diezelfde IntegrityError als
    # idempotente LedgerError terug zonder de batch of de wallet-tellers te
    # corrumperen. Sessie draait met autoflush=False, dus deze flush maakt de
    # duplicate-check ook binnen één import-batch sluitend.
    try:
        with db.begin_nested():
            db.add(txn)
            db.flush()
    except IntegrityError as ie:
        raise LedgerError(
            f"Dubbele transactie (external_ref={external_ref}) — overgeslagen"
        ) from ie

    # Pas daarna de wallet muteren — nooit bereikt bij een duplicate.
    wallet.balance_points = new_balance
    if points_delta > 0:
        wallet.lifetime_earned = (wallet.lifetime_earned or 0) + points_delta
    elif txn_type == "expire":
        wallet.lifetime_expired = (wallet.lifetime_expired or 0) + (-points_delta)
    else:
        wallet.lifetime_redeemed = (wallet.lifetime_redeemed or 0) + (-points_delta)
    db.flush()
    if commit:
        db.commit()
    return txn


def verify_ledger_integrity(db: Session) -> list[dict]:
    """Controleer saldo == som(ledger) per wallet. Retourneert mismatches."""
    sums = dict(
        db.query(
            models.LoyaltyTransaction.member_id,
            func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0),
        ).group_by(models.LoyaltyTransaction.member_id).all()
    )
    mismatches = []
    for wallet in db.query(models.LoyaltyWallet).all():
        expected = int(sums.get(wallet.member_id, 0))
        if int(wallet.balance_points or 0) != expected:
            mismatches.append({
                "member_id": wallet.member_id,
                "wallet_balance": int(wallet.balance_points or 0),
                "ledger_sum": expected,
            })
    return mismatches


def recompute_tiers(db: Session) -> int:
    """Herbereken tier per lid op basis van 12m verdiende punten."""
    tiers = db.query(models.LoyaltyTier).order_by(models.LoyaltyTier.rank.desc()).all()
    if not tiers:
        return 0
    cutoff = date.today() - timedelta(days=365)
    earned = dict(
        db.query(
            models.LoyaltyTransaction.member_id,
            func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0),
        ).filter(
            models.LoyaltyTransaction.points_delta > 0,
            models.LoyaltyTransaction.txn_date >= cutoff,
        ).group_by(models.LoyaltyTransaction.member_id).all()
    )
    updated = 0
    for member in db.query(models.LoyaltyMember).all():
        pts = int(earned.get(member.id, 0))
        new_tier = tiers[-1].code  # laagste als fallback
        for t in tiers:  # aflopend op rank
            if pts >= (t.min_points_12m or 0):
                new_tier = t.code
                break
        if member.tier_code != new_tier:
            member.tier_code = new_tier
            updated += 1
    return updated


# ---------------------------------------------------------------------------
# Customer Intelligence: RFM / CLV / churn / retentie / NBA
# ---------------------------------------------------------------------------

def _f(x) -> float:
    return float(x) if x is not None else 0.0


def compute_customer_value(db: Session, run_date: date | None = None) -> int:
    """
    Berekent per lid RFM, CLV (24m), churn-risico, retentiekans, segment en
    Next Best Action. Heuristisch model met expliciete confidence en uitleg
    (§64.9-10) — confidence schaalt met de hoeveelheid historie.
    """
    run_date = run_date or date.today()
    cutoff_12m = run_date - timedelta(days=365)

    members = db.query(models.LoyaltyMember).all()
    if not members:
        return 0

    # Purchase-achtige events: earn-transacties met order_value
    rows = db.query(
        models.LoyaltyTransaction.member_id,
        func.count(models.LoyaltyTransaction.id),
        func.coalesce(func.sum(models.LoyaltyTransaction.order_value), 0),
        func.max(models.LoyaltyTransaction.txn_date),
    ).filter(
        models.LoyaltyTransaction.txn_type == "earn",
        models.LoyaltyTransaction.txn_date >= cutoff_12m,
    ).group_by(models.LoyaltyTransaction.member_id).all()
    stats_12m = {r[0]: r for r in rows}

    last_any = dict(
        db.query(
            models.LoyaltyTransaction.member_id,
            func.max(models.LoyaltyTransaction.txn_date),
        ).filter(models.LoyaltyTransaction.txn_type == "earn")
        .group_by(models.LoyaltyTransaction.member_id).all()
    )

    # Verwijder eerdere run van vandaag (idempotent)
    db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.run_date == run_date
    ).delete()

    n = 0
    for m in members:
        _, freq, monetary, _ = stats_12m.get(m.id, (m.id, 0, 0, None))
        last_purchase = last_any.get(m.id)
        recency = (run_date - last_purchase).days if last_purchase else None
        monetary = _f(monetary)
        aov = monetary / freq if freq else 0.0

        # Churn-risico: logistisch oplopend met recency, gedempt door frequentie
        if recency is None:
            churn = 0.9
        else:
            base = min(1.0, recency / 365.0)          # 0..1 na een jaar stilte
            damp = min(0.4, freq * 0.05)              # frequente kopers churnen minder snel
            churn = round(max(0.02, min(0.98, base * (1.0 - damp) + 0.05)), 3)
        retention = round(1.0 - churn, 3)

        # CLV: verwachte 24m-waarde = 12m-besteding * 2 * retentiekans
        clv = round(monetary * 2.0 * retention, 2)

        # Segment
        if recency is None or churn >= 0.85:
            segment = "lost" if (recency or 9999) > 540 else "at_risk"
        elif churn >= 0.6:
            segment = "at_risk"
        elif monetary >= 500 and freq >= 6:
            segment = "high_value"
        elif monetary >= 150:
            segment = "mid_value"
        else:
            segment = "low_value"

        # Confidence: schaalt met datapunten (frequentie) en aanwezige historie
        confidence = round(min(0.9, 0.2 + 0.08 * min(freq, 8) + (0.1 if last_purchase else 0.0)), 2)

        explanation = (
            f"RFM 12m: recency={recency if recency is not None else 'geen aankopen'}d, "
            f"frequentie={freq}, besteding=€{monetary:.2f} (AOV €{aov:.2f}). "
            f"Churn-risico {churn:.0%} → retentiekans {retention:.0%}. "
            f"CLV-schatting (24m) = 12m-besteding × 2 × retentiekans = €{clv:.2f}. "
            f"Heuristisch model {MODEL_VERSION}; confidence {confidence:.0%} op basis van "
            f"{freq} datapunten."
        )

        # Next Best Action + vergelijking met generieke prijsverlaging (§22)
        nba, nba_reason, nba_ev, alt_cost = _next_best_action(segment, churn, monetary, aov, retention)

        db.add(models.CustomerValueScore(
            shop_id=m.shop_id or 1,
            member_id=m.id,
            run_date=run_date,
            recency_days=recency,
            frequency_12m=int(freq or 0),
            monetary_12m=monetary,
            avg_order_value=aov,
            clv_estimate=clv,
            churn_risk=churn,
            retention_probability=retention,
            value_segment=segment,
            confidence=confidence,
            explanation=explanation,
            next_best_action=nba,
            nba_reason=nba_reason,
            nba_expected_value=nba_ev,
            nba_alternative="generieke_prijsverlaging_2pct",
            nba_alternative_cost=alt_cost,
        ))
        n += 1
    return n


def _next_best_action(segment: str, churn: float, monetary: float, aov: float, retention: float):
    """
    Kies NBA en kwantificeer t.o.v. het alternatief: een generieke
    prijsverlaging van 2% over de 12m-besteding van dit lid (marge-offer
    zonder targeting). Gericht loyalty-instrument is doorgaans goedkoper.
    """
    alt_cost = round(monetary * 0.02, 2)  # kost van 2% generieke prijsverlaging
    if segment == "lost":
        return ("no_action", "Lid is >18 maanden inactief; winback-kosten wegen "
                "niet op tegen verwachte waarde.", 0.0, alt_cost)
    if segment == "at_risk":
        ev = round(monetary * 0.25 * (1 - churn + 0.3), 2)
        return ("winback_voucher",
                f"Hoog churn-risico ({churn:.0%}): gerichte winback-voucher (±€{max(aov*0.1, 5):.0f}) "
                f"is goedkoper dan generieke prijsverlaging (€{alt_cost:.2f}) en behoudt marge "
                "op niet-risico-klanten.", ev, alt_cost)
    if segment == "high_value":
        ev = round(monetary * 0.10, 2)
        return ("tier_upgrade_nudge",
                "Hoogwaardig lid: tier-voordeel benadrukken verhoogt retentie zonder "
                f"prijsinvestering; generiek alternatief zou €{alt_cost:.2f} marge kosten.", ev, alt_cost)
    if segment == "mid_value":
        ev = round(monetary * 0.08, 2)
        return ("loyalty_bonus",
                "Gerichte bonuspunten-actie stimuleert herhaalaankoop tegen puntkosten "
                f"(±€{monetary * 0.01:.2f}) i.p.v. generieke prijsverlaging (€{alt_cost:.2f}).",
                ev, alt_cost)
    return ("no_action", "Lage waarde en geen verhoogd churn-risico; geen actie is "
            "rendabeler dan investeren.", 0.0, alt_cost)


# ---------------------------------------------------------------------------
# Financial liability
# ---------------------------------------------------------------------------

def liability_summary(db: Session, shop_id: int | None = None) -> dict:
    """Liability-samenvatting; met shop_id beperkt tot leden/vouchers van die shop."""
    outstanding_q = db.query(
        func.coalesce(func.sum(models.LoyaltyWallet.balance_points), 0)
    )
    voucher_value_q = db.query(
        func.coalesce(func.sum(models.LoyaltyVoucher.monetary_value), 0)
    ).filter(models.LoyaltyVoucher.status == "issued")
    voucher_count_q = db.query(func.count(models.LoyaltyVoucher.id)).filter(
        models.LoyaltyVoucher.status == "issued"
    )
    # 30d expiry: vouchers die binnen 30 dagen vervallen
    soon = date.today() + timedelta(days=30)
    expiring_vouchers_q = db.query(func.count(models.LoyaltyVoucher.id)).filter(
        models.LoyaltyVoucher.status == "issued",
        models.LoyaltyVoucher.expires_at != None,  # noqa: E711
        models.LoyaltyVoucher.expires_at <= soon,
    )
    if shop_id is not None:
        outstanding_q = outstanding_q.join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyWallet.member_id
        ).filter(models.LoyaltyMember.shop_id == shop_id)
        voucher_value_q = voucher_value_q.join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyVoucher.member_id
        ).filter(models.LoyaltyMember.shop_id == shop_id)
        voucher_count_q = voucher_count_q.join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyVoucher.member_id
        ).filter(models.LoyaltyMember.shop_id == shop_id)
        expiring_vouchers_q = expiring_vouchers_q.join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyVoucher.member_id
        ).filter(models.LoyaltyMember.shop_id == shop_id)

    outstanding = int(outstanding_q.scalar() or 0)
    voucher_value = voucher_value_q.scalar() or 0
    voucher_count = voucher_count_q.scalar() or 0
    expiring_vouchers = expiring_vouchers_q.scalar() or 0
    points_liability = round(outstanding * POINT_VALUE_EUR, 2)

    # Punten die binnenkort verlopen op basis van het verloopbeleid van de shop.
    # Ongescoped (dashboard zonder shop_id): aggregeer per shop volgens het
    # eigen (enabled) beleid van die shop — nooit shop 1-beleid op andere shops.
    policy = _get_expiry_policy(db, shop_id if shop_id is not None else 1)
    points_expiring_30d = 0
    points_expiring_90d = 0
    expiry_forecast: list[dict] = []
    scope_ids = [shop_id] if shop_id is not None else _loyalty_shop_ids(db)
    for sid in scope_ids:
        shop_policy = policy if sid == (shop_id if shop_id is not None else 1) \
            else _get_expiry_policy(db, sid)
        if not shop_policy.enabled:
            continue
        points_expiring_30d += _compute_expiring_points(db, shop_policy, warn_days=30, shop_id=sid)
        points_expiring_90d += _compute_expiring_points(db, shop_policy, warn_days=90, shop_id=sid)
        shop_forecast = _expiry_forecast_monthly(db, shop_policy, months=6, shop_id=sid)
        if not expiry_forecast:
            expiry_forecast = shop_forecast
        else:
            for agg, extra in zip(expiry_forecast, shop_forecast):
                agg["points"] += extra["points"]
                agg["eur"] = round(agg["eur"] + extra["eur"], 2)

    return {
        "shop_id": shop_id,
        "outstanding_points": outstanding,
        "point_value_eur": POINT_VALUE_EUR,
        "points_liability_eur": points_liability,
        "open_vouchers": int(voucher_count),
        "voucher_liability_eur": round(float(voucher_value), 2),
        "total_liability_eur": round(points_liability + float(voucher_value), 2),
        "vouchers_expiring_30d": int(expiring_vouchers),
        "points_expiring_30d": int(points_expiring_30d),
        "points_expiring_90d": int(points_expiring_90d),
        "expiry_forecast": expiry_forecast,
        "expiry_policy": {
            "enabled": policy.enabled,
            "expiry_months": policy.expiry_months,
            "warn_days_before": policy.warn_days_before,
        },
    }


# ---------------------------------------------------------------------------
# Puntenverloop (expiry)
# ---------------------------------------------------------------------------

DEFAULT_EXPIRY_MONTHS = 12
DEFAULT_WARN_DAYS = 30


def _get_expiry_policy(db: Session, shop_id: int = 1) -> models.LoyaltyExpiryPolicy:
    """Haal het verloopbeleid van een shop op; maak het aan met standaardwaarden als het ontbreekt."""
    policy = db.query(models.LoyaltyExpiryPolicy).filter(
        models.LoyaltyExpiryPolicy.shop_id == shop_id
    ).first()
    if not policy:
        policy = models.LoyaltyExpiryPolicy(
            shop_id=shop_id,
            enabled=True,
            expiry_months=DEFAULT_EXPIRY_MONTHS,
            warn_days_before=DEFAULT_WARN_DAYS,
        )
        db.add(policy)
        db.flush()
    return policy

def _wallet_query(db: Session, shop_id: int | None = None):
    """Wallets, optioneel beperkt tot leden van één shop (wallets zelf hebben geen shop_id)."""
    q = db.query(models.LoyaltyWallet)
    if shop_id is not None:
        q = q.join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyWallet.member_id
        ).filter(models.LoyaltyMember.shop_id == shop_id)
    return q
def _fifo_expirable_points(
    db: Session,
    member_id: int,
    wallet: models.LoyaltyWallet,
    expiry_cutoff: date,
    *,
    warn_window_end: date | None = None,
) -> int:
    """
    FIFO-berekening: hoeveel punten, verdiend vóór `expiry_cutoff`
    (en optioneel na `warn_window_end`), zijn nog niet geconsumeerd
    door inwisselingen of eerder verloop.

    FIFO-regel: inwisselingen consumeren altijd de oudste punten eerst.
    Verdiend vóór cutoff − min(totaal-ingewisseld, verdiend-vóór-cutoff) − al-verlopen
    = resterende oude punten die nu moeten verlopen.
    """
    # Verdiend vóór de vervalgrens (earn + bonus-typen)
    credit_types = list(_CREDIT_TYPES)
    earned_old: int = int(db.query(
        func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0)
    ).filter(
        models.LoyaltyTransaction.member_id == member_id,
        models.LoyaltyTransaction.txn_type.in_(credit_types),
        models.LoyaltyTransaction.txn_date < expiry_cutoff,
    ).scalar() or 0)

    if earned_old <= 0:
        return 0

    if warn_window_end is not None:
        # "Expiring soon"-modus: alleen punten verdiend tussen warn_window_end en cutoff
        earned_in_window: int = int(db.query(
            func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0)
        ).filter(
            models.LoyaltyTransaction.member_id == member_id,
            models.LoyaltyTransaction.txn_type.in_(credit_types),
            models.LoyaltyTransaction.txn_date >= warn_window_end,
            models.LoyaltyTransaction.txn_date < expiry_cutoff,
        ).scalar() or 0)
        # Hoeveel van de nog-oudere punten zijn al geconsumeerd door inwisselingen?
        total_redeemed = int(wallet.lifetime_redeemed or 0)
        total_expired = int(wallet.lifetime_expired or 0)
        earned_before_window = earned_old - earned_in_window
        # FIFO: redeems raken eerst de punten vóór het waarschuwingsvenster
        redeems_on_pre_window = min(total_redeemed + total_expired, earned_before_window)
        remaining_pre_window = max(0, earned_before_window - redeems_on_pre_window)
        # Van de window-punten: wat is al geconsumeerd na pre-window?
        redeems_on_window = max(0, (total_redeemed + total_expired) - redeems_on_pre_window)
        still_live_window = max(0, earned_in_window - redeems_on_window)
        # Punten die de vervalgrens al gepasseerd zijn maar nog niet formeel
        # verlopen (bijv. omdat de expiry-run nog niet gedraaid heeft) tellen
        # mee als "binnenkort verlopend": ze vervallen bij de eerstvolgende run.
        return min(int(wallet.balance_points or 0), still_live_window + remaining_pre_window)

    # Normaal verlooppad: alle punten vóór cutoff
    total_redeemed = int(wallet.lifetime_redeemed or 0)
    total_expired = int(wallet.lifetime_expired or 0)
    # FIFO: inwisselingen slaan neer op de oudste punten
    redeems_hitting_old = min(total_redeemed, earned_old)
    still_live_old = max(0, earned_old - redeems_hitting_old - total_expired)
    return min(int(wallet.balance_points or 0), still_live_old)


def _compute_expiring_points(
    db: Session,
    policy: models.LoyaltyExpiryPolicy,
    warn_days: int,
    shop_id: int | None = None,
) -> int:
    """
    Totaal aantal punten dat binnen `warn_days` dagen vervalt op basis van het
    verloopbeleid; met shop_id beperkt tot leden van die shop.
    """
    today = date.today()
    # Punten verdiend vóór deze datum vervallen binnen warn_days
    cutoff_soon = today - timedelta(days=policy.expiry_months * 30 - warn_days)
    # De eigenlijke vervalgrens
    cutoff_full = today - timedelta(days=policy.expiry_months * 30)

    total = 0
    for wallet in _wallet_query(db, shop_id).all():
        if not wallet.balance_points:
            continue
        pts = _fifo_expirable_points(
            db, wallet.member_id, wallet,
            expiry_cutoff=cutoff_soon,
            warn_window_end=cutoff_full,
        )
        total += pts
    return total

_NL_MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]


def _month_end(d: date) -> date:
    """Laatste dag van de maand waarin `d` valt."""
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)
def apply_expiry_run(
    db: Session,
    run_date: date | None = None,
    *,
    dry_run: bool = False,
    shop_id: int | None = None,
) -> dict:
    """
    Genereer expire-ledger-entries (FIFO) voor alle leden waarvan punten
    de vervalgrens hebben overschreden, volgens het verloopbeleid van de
    shop van elk lid (niet één globaal beleid).

    - Gebruikt uitsluitend `apply_ledger_entry` zodat de ledger-integriteit
      gewaarborgd blijft (saldo nooit negatief, geen dubbele entries via
      external_ref-idempotentie).
    - Bij `dry_run=True` worden geen mutaties geschreven.
    - Met `shop_id` beperkt tot leden van die shop.
    - Retourneert een samenvatting.
    """
    run_date = run_date or date.today()

    members_expired = 0
    points_expired_total = 0
    skipped_duplicates = 0
    errors = 0

    wallets = _wallet_query(db, shop_id).filter(
        models.LoyaltyWallet.balance_points > 0
    ).all()
    members_map = {
        m.id: m for m in db.query(models.LoyaltyMember).filter(
            models.LoyaltyMember.id.in_([w.member_id for w in wallets])
        ).all()
    }
    # Verloopbeleid per shop (lazy opgehaald per aangetroffen shop)
    policies: dict[int, models.LoyaltyExpiryPolicy] = {}

    def _policy_for(sid: int) -> models.LoyaltyExpiryPolicy:
        if sid not in policies:
            policies[sid] = _get_expiry_policy(db, sid)
        return policies[sid]

    if shop_id is not None and not _policy_for(shop_id).enabled:
        return {
            "run_date": run_date.isoformat(),
            "policy_enabled": False,
            "shop_id": shop_id,
            "members_processed": 0,
            "members_expired": 0,
            "points_expired": 0,
            "dry_run": dry_run,
        }

    members_processed = 0
    for wallet in wallets:
        member = members_map.get(wallet.member_id)
        if not member:
            continue
        policy = _policy_for(int(member.shop_id or 1))
        if not policy.enabled:
            continue
        members_processed += 1
        expiry_cutoff = run_date - timedelta(days=policy.expiry_months * 30)

        pts_to_expire = _fifo_expirable_points(
            db, member.id, wallet, expiry_cutoff
        )
        if pts_to_expire <= 0:
            continue

        if dry_run:
            members_expired += 1
            points_expired_total += pts_to_expire
            continue

        # external_ref voor idempotentie: één expiry-entry per lid per maand
        period = run_date.strftime("%Y-%m")
        ext_ref = f"expiry-{member.id}-{period}"

        try:
            apply_ledger_entry(
                db, member, run_date,
                "expire", -pts_to_expire,
                description=(
                    f"Automatisch verloop: {pts_to_expire} punten ouder dan "
                    f"{policy.expiry_months} maanden (FIFO, vervalgrens {expiry_cutoff})"
                ),
                external_ref=ext_ref,
            )
            members_expired += 1
            points_expired_total += pts_to_expire
        except LedgerError as e:
            msg = str(e)
            if "Dubbele transactie" in msg:
                skipped_duplicates += 1
            else:
                logger.warning("Expiry-fout lid %s: %s", member.id, e)
                errors += 1

    logger.info(
        "Expiry-run %s: %d leden, %d punten verlopen, %d duplicaten overgeslagen, %d fouten",
        run_date, members_expired, points_expired_total, skipped_duplicates, errors,
    )
    # Contractvelden expiry_cutoff/expiry_months: gebaseerd op het beleid van
    # de gescopede shop, of de default shop (1) bij een ongescopede run.
    primary_policy = _policy_for(int(shop_id) if shop_id is not None else 1)
    return {
        "run_date": run_date.isoformat(),
        "policy_enabled": any(p.enabled for p in policies.values()) if policies else True,
        "shop_id": shop_id,
        "expiry_cutoff": (
            run_date - timedelta(days=primary_policy.expiry_months * 30)
        ).isoformat(),
        "expiry_months": primary_policy.expiry_months,
        "policies": {
            sid: {"enabled": p.enabled, "expiry_months": p.expiry_months}
            for sid, p in policies.items()
        },
        "members_processed": members_processed,
        "members_expired": members_expired,
        "points_expired": points_expired_total,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
        "dry_run": dry_run,
    }


def expiring_soon_members(db: Session, shop_id: int | None = None) -> list[dict]:
    """
    Geef een lijst van leden met punten die binnenkort verlopen, volgens het
    verloopbeleid van de shop van elk lid. Met `shop_id` beperkt tot die shop.
    """
    today = date.today()
    wallets = _wallet_query(db, shop_id).filter(
        models.LoyaltyWallet.balance_points > 0
    ).all()
    members_map = {
        m.id: m for m in db.query(models.LoyaltyMember).filter(
            models.LoyaltyMember.id.in_([w.member_id for w in wallets])
        ).all()
    }
    policies: dict[int, models.LoyaltyExpiryPolicy] = {}

    result = []
    for wallet in wallets:
        member = members_map.get(wallet.member_id)
        if not member:
            continue
        sid = int(member.shop_id or 1)
        if sid not in policies:
            policies[sid] = _get_expiry_policy(db, sid)
        policy = policies[sid]
        if not policy.enabled:
            continue
        # Punten verdiend vóór deze datum verlopen binnen warn_days_before dagen
        cutoff_soon = today - timedelta(days=policy.expiry_months * 30 - policy.warn_days_before)
        # De eigenlijke vervalgrens
        cutoff_full = today - timedelta(days=policy.expiry_months * 30)
        pts = _fifo_expirable_points(
            db, wallet.member_id, wallet,
            expiry_cutoff=cutoff_soon,
            warn_window_end=cutoff_full,
        )
        if pts > 0:
            # Schat de vervaldatum FIFO-consistent: zolang er nog levende
            # punten van vóór de vervalgrens zijn (overdue), is de vroegste
            # earn-datum überhaupt bepalend → geschatte vervaldatum in het
            # verleden en days_until_expiry <= 0, zodat overdue leden bovenaan
            # sorteren — consistent met de liability-cijfers. Pas als de
            # overdue punten volledig geconsumeerd zijn telt de vroegste earn
            # binnen het waarschuwingsvenster.
            overdue_live = _fifo_expirable_points(
                db, wallet.member_id, wallet, expiry_cutoff=cutoff_full,
            )
            date_filters = [
                models.LoyaltyTransaction.member_id == member.id,
                models.LoyaltyTransaction.txn_type.in_(list(_CREDIT_TYPES)),
                models.LoyaltyTransaction.txn_date < cutoff_soon,
            ]
            if overdue_live <= 0:
                date_filters.append(models.LoyaltyTransaction.txn_date >= cutoff_full)
            earliest = db.query(func.min(models.LoyaltyTransaction.txn_date)).filter(
                *date_filters
            ).scalar()
            if earliest is None:
                # Alleen al-overdue punten: schat de (verstreken) vervaldatum
                # op basis van de vroegste credit vóór de vervalgrens.
                earliest = db.query(func.min(models.LoyaltyTransaction.txn_date)).filter(
                    models.LoyaltyTransaction.member_id == member.id,
                    models.LoyaltyTransaction.txn_type.in_(list(_CREDIT_TYPES)),
                    models.LoyaltyTransaction.txn_date < cutoff_full,
                ).scalar()
            expires_on = (
                earliest + timedelta(days=policy.expiry_months * 30)
            ) if earliest else None
            result.append({
                "member_id": member.id,
                "shop_id": sid,
                "pseudonymous_customer_id": member.pseudonymous_customer_id,
                "tier_code": member.tier_code,
                "balance_points": int(wallet.balance_points or 0),
                "points_expiring": pts,
                "points_expiring_eur": round(pts * POINT_VALUE_EUR, 2),
                "expires_on": expires_on.isoformat() if expires_on else None,
                "days_until_expiry": (expires_on - today).days if expires_on else None,
                "is_demo_data": bool(member.is_demo_data),
            })
    result.sort(key=lambda r: r["days_until_expiry"] if r["days_until_expiry"] is not None else 9999)
    return result


# ---------------------------------------------------------------------------
# Fraude
# ---------------------------------------------------------------------------

def detect_fraud(db: Session, run_date: date | None = None) -> int:
    """
    Detecteert: abnormale earn-rate (punten >> verwacht t.o.v. order_value),
    snelle redemption na earn (<48u patroon), referral-ringen (één werver met
    veel inactieve referrals) en wallet/ledger-mismatches.
    """
    run_date = run_date or date.today()
    db.query(models.LoyaltyFraudSignal).filter(
        models.LoyaltyFraudSignal.run_date == run_date
    ).delete()
    n = 0

    # Shop van elk lid: fraudesignalen krijgen de shop_id van het lid,
    # niet de kolom-default (shop 1).
    member_shop = {
        mid: int(sid or 1)
        for mid, sid in db.query(models.LoyaltyMember.id, models.LoyaltyMember.shop_id).all()
    }

    def _add(member_id: int, fraud_type: str, severity: str, score: float,
             explanation: str, evidence: dict):
        nonlocal n
        db.add(models.LoyaltyFraudSignal(
            shop_id=member_shop.get(member_id, 1),
            member_id=member_id, run_date=run_date, fraud_type=fraud_type,
            severity=severity, score=score, explanation=explanation, evidence=evidence,
        ))
        n += 1

    # 1. Abnormale earn-rate: punten per euro >> tier-multiplier (verwacht ~1-1.5 pt/€)
    cutoff = run_date - timedelta(days=90)
    rows = db.query(
        models.LoyaltyTransaction.member_id,
        func.sum(models.LoyaltyTransaction.points_delta),
        func.coalesce(func.sum(models.LoyaltyTransaction.order_value), 0),
        func.count(models.LoyaltyTransaction.id),
    ).filter(
        models.LoyaltyTransaction.txn_type == "earn",
        models.LoyaltyTransaction.txn_date >= cutoff,
    ).group_by(models.LoyaltyTransaction.member_id).all()
    for member_id, pts, val, cnt in rows:
        val = _f(val)
        if val > 0 and pts and (pts / val) > 3.0:
            _add(member_id, "abnormal_earn_rate", "high", min(1.0, (pts / val) / 10.0),
                 f"Earn-rate {pts / val:.1f} punten/€ over 90 dagen — verwacht ≤1.5 "
                 f"(hoogste tier-multiplier). {int(pts)} punten op €{val:.2f} besteding.",
                 {"points_90d": int(pts), "order_value_90d": val, "txn_count": int(cnt)})

    # 2. Snelle redemption: ≥3 redemptions binnen 2 dagen na earns in 30 dagen
    cutoff30 = run_date - timedelta(days=30)
    redeem_counts = db.query(
        models.LoyaltyTransaction.member_id,
        func.count(models.LoyaltyTransaction.id),
        func.sum(models.LoyaltyTransaction.points_delta),
    ).filter(
        models.LoyaltyTransaction.txn_type == "redeem",
        models.LoyaltyTransaction.txn_date >= cutoff30,
    ).group_by(models.LoyaltyTransaction.member_id).all()
    for member_id, cnt, pts in redeem_counts:
        if cnt >= 3:
            _add(member_id, "rapid_redemption", "medium", min(1.0, cnt / 10.0),
                 f"{cnt} redemptions binnen 30 dagen ({abs(int(pts or 0))} punten) — "
                 "ongebruikelijk hoog inwisseltempo.",
                 {"redemptions_30d": int(cnt), "points_redeemed": abs(int(pts or 0))})

    # 3. Referral-ring: werver met ≥5 referrals waarvan >80% zonder enige earn
    ref_rows = db.query(
        models.LoyaltyMember.referred_by,
        func.count(models.LoyaltyMember.id),
    ).filter(models.LoyaltyMember.referred_by != None)  # noqa: E711
    ref_rows = ref_rows.group_by(models.LoyaltyMember.referred_by).having(
        func.count(models.LoyaltyMember.id) >= 5
    ).all()
    for referrer_pid, cnt in ref_rows:
        referrer = db.query(models.LoyaltyMember).filter(
            models.LoyaltyMember.pseudonymous_customer_id == referrer_pid
        ).first()
        if not referrer:
            continue
        referred_ids = [r[0] for r in db.query(models.LoyaltyMember.id).filter(
            models.LoyaltyMember.referred_by == referrer_pid).all()]
        active = db.query(func.count(func.distinct(models.LoyaltyTransaction.member_id))).filter(
            models.LoyaltyTransaction.member_id.in_(referred_ids),
            models.LoyaltyTransaction.txn_type == "earn",
        ).scalar() or 0
        inactive_pct = 1.0 - (active / cnt)
        if inactive_pct > 0.8:
            _add(referrer.id, "referral_ring", "high", round(inactive_pct, 2),
                 f"{cnt} referrals waarvan {inactive_pct:.0%} nooit een aankoop deed — "
                 "patroon past bij referral-bonus-misbruik.",
                 {"referrals": int(cnt), "inactive_pct": round(inactive_pct, 2)})

    # 4. Wallet/ledger-mismatch
    for mm in verify_ledger_integrity(db):
        _add(mm["member_id"], "balance_mismatch", "critical", 1.0,
             f"Wallet-saldo ({mm['wallet_balance']}) wijkt af van ledger-som "
             f"({mm['ledger_sum']}) — ledger-integriteit geschonden.",
             mm)
    return n


# ---------------------------------------------------------------------------
# Intelligence Signals (§7): publiceren richting Decision Engine
# ---------------------------------------------------------------------------

def _publish_signal(db: Session, **kw) -> None:
    dedupe_key = f"{kw['engine']}:{kw['signal_type']}:{kw['entity_type']}:{kw['entity_id']}"
    shop_id = kw.pop("shop_id", 1)
    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.dedupe_key == dedupe_key,
        models.IntelligenceSignal.shop_id == shop_id,
        models.IntelligenceSignal.status == "active",
    ).update({"status": "superseded"})
    db.add(models.IntelligenceSignal(
        shop_id=shop_id, dedupe_key=dedupe_key, model_version=MODEL_VERSION, **kw
    ))


def publish_signals(db: Session, run_date: date | None = None) -> int:
    """
    Publiceert loyalty-signalen: NBA per lid (top-churn/high-value), fraude,
    liability-niveau. Elk signaal heeft explanation + evidence (§64.9-10).
    """
    run_date = run_date or date.today()
    published = 0

    scores = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.run_date == run_date,
        models.CustomerValueScore.next_best_action != "no_action",
    ).order_by(models.CustomerValueScore.clv_estimate.desc()).limit(50).all()
    members = {m.id: m for m in db.query(models.LoyaltyMember).all()}

    for s in scores:
        m = members.get(s.member_id)
        if not m:
            continue
        _publish_signal(
            db,
            shop_id=int(m.shop_id or 1),
            engine="loyalty",
            signal_type=f"nba_{s.next_best_action}",
            severity="medium" if s.value_segment == "at_risk" else "info",
            direction="positive",
            entity_type="customer",
            entity_id=m.pseudonymous_customer_id,
            entity_name=f"Lid {m.pseudonymous_customer_id} ({s.value_segment})",
            current_value=float(s.clv_estimate or 0),
            confidence=float(s.confidence or 0),
            explanation=(
                f"Next Best Action '{s.next_best_action}': {s.nba_reason} "
                f"Verwachte incrementele waarde €{float(s.nba_expected_value or 0):.2f} "
                f"vs. generieke prijsverlaging (kost €{float(s.nba_alternative_cost or 0):.2f})."
            ),
            evidence={
                "clv_estimate": float(s.clv_estimate or 0),
                "churn_risk": s.churn_risk,
                "retention_probability": s.retention_probability,
                "value_segment": s.value_segment,
                "nba_expected_value": float(s.nba_expected_value or 0),
                "alternative": s.nba_alternative,
                "alternative_cost": float(s.nba_alternative_cost or 0),
            },
            sources=["customer_value_scores", "loyalty_transactions", "loyalty_wallets"],
            suggested_action=s.next_best_action,
        )
        published += 1

    # Fraude: één signaal per open fraudemelding van vandaag
    frauds = db.query(models.LoyaltyFraudSignal).filter(
        models.LoyaltyFraudSignal.run_date == run_date,
        models.LoyaltyFraudSignal.status == "open",
    ).all()
    for f in frauds:
        m = members.get(f.member_id)
        if not m:
            continue
        _publish_signal(
            db,
            shop_id=int(m.shop_id or 1),
            engine="loyalty",
            signal_type=f"fraud_{f.fraud_type}",
            severity=f.severity or "medium",
            direction="negative",
            entity_type="customer",
            entity_id=m.pseudonymous_customer_id,
            entity_name=f"Lid {m.pseudonymous_customer_id}",
            current_value=f.score,
            confidence=min(0.95, 0.5 + (f.score or 0) / 2),
            explanation=f.explanation,
            evidence=f.evidence or {"fraud_type": f.fraud_type},
            sources=["loyalty_fraud_signals", "loyalty_transactions"],
            suggested_action="review_member",
        )
        published += 1

    # Liability op shop-niveau: één signaal per shop met loyalty-leden
    for sid in _loyalty_shop_ids(db):
        liab = liability_summary(db, shop_id=sid)
        if liab["outstanding_points"] > 0:
            _publish_signal(
                db,
                shop_id=sid,
                engine="loyalty",
                signal_type="loyalty_liability_level",
                severity="info",
                direction="neutral",
                entity_type="shop",
                entity_id=str(sid),
                entity_name="Loyalty financial liability",
                current_value=liab["total_liability_eur"],
                confidence=0.95,
                explanation=(
                    f"Openstaande loyaliteitsverplichting shop {sid}: {liab['outstanding_points']} punten "
                    f"(€{liab['points_liability_eur']:.2f}) + {liab['open_vouchers']} open vouchers "
                    f"(€{liab['voucher_liability_eur']:.2f}) = €{liab['total_liability_eur']:.2f}."
                ),
                evidence=liab,
                sources=["loyalty_wallets", "loyalty_vouchers"],
                suggested_action="monitor_liability",
            )
            published += 1

    return published

def _z_to_confidence(z: float) -> float:
    """
    Benadering van 1 - p_waarde (tweezijdig) via de normale verdeling.
    Geen scipy-afhankelijkheid: nauwkeurig genoeg voor heuristische confidence.
    """
    import math
    # Abramowitz & Stegun benadering van de complementaire fout-functie
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    p_one_tail = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z) * poly
    p_two_tail = 2 * p_one_tail
    return round(max(0.0, min(1.0, 1.0 - p_two_tail)), 3)
def run_loyalty_engine(db: Session) -> dict:
    """Volledige run: verloop → tiers → customer value → fraude → campaign uplift → signalen."""
    run_date = date.today()
    # Verloop als eerste stap: expired punten zijn dan niet meer in het saldo
    # voor de tier-herberekening en klantwaardescores.
    expiry = apply_expiry_run(db, run_date)
    db.flush()
    tiers_updated = recompute_tiers(db)
    db.flush()
    scored = compute_customer_value(db, run_date)
    # SessionLocal draait met autoflush=False: expliciet flushen zodat de
    # queries in detect_fraud/publish_signals de zojuist berekende rijen zien.
    db.flush()
    fraud = detect_fraud(db, run_date)
    db.flush()
    signals = publish_signals(db, run_date)
    db.flush()
    uplift_signals = publish_campaign_uplift_signals(db, run_date)
    db.commit()
    return {
        "run_date": run_date.isoformat(),
        "tiers_updated": tiers_updated,
        "members_scored": scored,
        "fraud_signals": fraud,
        "intelligence_signals_published": signals + uplift_signals,
        "campaign_uplift_signals": uplift_signals,
        "model_version": MODEL_VERSION,
        "expiry": expiry,
    }


def ensure_default_tiers(db: Session) -> None:
    if db.query(models.LoyaltyTier).count() == 0:
        for t in DEFAULT_TIERS:
            db.add(models.LoyaltyTier(**t))
        db.commit()

def compute_campaign_uplift(
    db: Session,
    campaign_id: int | None = None,
    shop_id: int | None = None,
) -> list[dict]:
    """
    Berekent uplift per campagne (treatment vs. control):
    - besteding per lid (spend/member)
    - aankoopfrequentie per lid (orders/member)
    - retentie: aandeel leden met ≥1 aankoop in de campagneperiode
    - uplift% + statistische confidence (z-score benadering, §22).

    Alleen campagnes met ≥1 treatment- EN ≥1 control-lid worden geanalyseerd.
    Geeft een lijst van uplift-dicts terug (één per campagne).
    """
    q = db.query(models.LoyaltyCampaign)
    if campaign_id is not None:
        q = q.filter(models.LoyaltyCampaign.id == campaign_id)
    if shop_id is not None:
        q = q.filter(models.LoyaltyCampaign.shop_id == shop_id)
    campaigns = q.all()

    results = []
    for c in campaigns:
        memberships = db.query(models.LoyaltyCampaignMembership).filter(
            models.LoyaltyCampaignMembership.campaign_id == c.id
        ).all()
        if not memberships:
            continue

        treatment_ids = [m.member_id for m in memberships if m.group_type == "treatment"]
        control_ids = [m.member_id for m in memberships if m.group_type == "control"]
        if not treatment_ids or not control_ids:
            continue

        # Bepaal meetperiode: campagneperiode, of 365 dagen als fallback.
        # Als datums ontbreken is de periode GESCHAT — markeer dat expliciet
        # zodat de gebruiker weet dat het resultaat vertekend kan zijn.
        period_estimated = c.start_date is None or c.end_date is None
        start = c.start_date or (date.today() - timedelta(days=365))
        end = c.end_date or date.today()

        def _group_stats(member_ids: list[int]) -> dict:
            """Besteding, frequentie en retentie voor een groep in de campagneperiode."""
            if not member_ids:
                return {"n": 0, "spend_total": 0.0, "orders_total": 0,
                        "members_with_purchase": 0, "spend_per_member": 0.0,
                        "orders_per_member": 0.0, "retention_rate": 0.0}

            # Earn-transacties in de meetperiode voor deze leden
            rows = db.query(
                models.LoyaltyTransaction.member_id,
                func.count(models.LoyaltyTransaction.id),
                func.coalesce(func.sum(models.LoyaltyTransaction.order_value), 0),
            ).filter(
                models.LoyaltyTransaction.member_id.in_(member_ids),
                models.LoyaltyTransaction.txn_type == "earn",
                models.LoyaltyTransaction.txn_date >= start,
                models.LoyaltyTransaction.txn_date <= end,
            ).group_by(models.LoyaltyTransaction.member_id).all()

            n = len(member_ids)
            members_with_purchase = len(rows)
            orders_total = sum(int(r[1]) for r in rows)
            spend_total = sum(float(r[2]) for r in rows)
            return {
                "n": n,
                "spend_total": round(spend_total, 2),
                "orders_total": orders_total,
                "members_with_purchase": members_with_purchase,
                "spend_per_member": round(spend_total / n, 2),
                "orders_per_member": round(orders_total / n, 3),
                "retention_rate": round(members_with_purchase / n, 3),
            }

        t = _group_stats(treatment_ids)
        ctrl = _group_stats(control_ids)

        # Uplift-berekeningen
        def _uplift_pct(treatment_val: float, control_val: float) -> float | None:
            if control_val == 0:
                return None
            return round((treatment_val - control_val) / control_val * 100, 1)

        spend_uplift = _uplift_pct(t["spend_per_member"], ctrl["spend_per_member"])
        freq_uplift = _uplift_pct(t["orders_per_member"], ctrl["orders_per_member"])
        retention_uplift = _uplift_pct(t["retention_rate"], ctrl["retention_rate"])

        # Statistische confidence via z-score voor retentie (proporties).
        # Voor spend/frequentie geven we een heuristische confidence op basis
        # van steekproefgroottes (geen SD beschikbaar zonder rij-level data).
        import math
        n_t, n_c = t["n"], ctrl["n"]
        p_t = t["retention_rate"]
        p_c = ctrl["retention_rate"]
        p_pool = (t["members_with_purchase"] + ctrl["members_with_purchase"]) / (n_t + n_c) if (n_t + n_c) > 0 else 0.5
        denom = math.sqrt(p_pool * (1 - p_pool) * (1 / max(n_t, 1) + 1 / max(n_c, 1)))
        z_retention = (p_t - p_c) / denom if denom > 0 else 0.0
        retention_confidence = _z_to_confidence(z_retention)

        # Spend confidence: heuristic — schaalt met min(n_t, n_c) tot ~0.90
        spend_confidence = round(min(0.90, 0.3 + 0.04 * min(n_t, n_c, 15)), 2)

        # Gecombineerde confidence: gemiddelde van beide
        combined_confidence = round((retention_confidence + spend_confidence) / 2, 3)

        # Kwalificatie: positief/negatief/neutraal
        direction: str
        if spend_uplift is not None and spend_uplift > 5:
            direction = "positive"
        elif spend_uplift is not None and spend_uplift < -5:
            direction = "negative"
        else:
            direction = "neutral"

        period_warning = None
        if period_estimated:
            period_warning = (
                "Meetperiode geschat; voeg campagnedatums toe voor nauwkeurige analyse"
            )

        explanation = (
            f"Campagne '{c.name}' ({start} – {end}"
            f"{', periode geschat' if period_estimated else ''}): "
            f"treatment (n={n_t}) vs. control (n={n_c}). "
            f"Besteding/lid: €{t['spend_per_member']:.2f} vs. €{ctrl['spend_per_member']:.2f} "
            f"({'+' if (spend_uplift or 0) >= 0 else ''}{spend_uplift if spend_uplift is not None else '—'}%). "
            f"Frequentie/lid: {t['orders_per_member']:.2f} vs. {ctrl['orders_per_member']:.2f} "
            f"({'+' if (freq_uplift or 0) >= 0 else ''}{freq_uplift if freq_uplift is not None else '—'}%). "
            f"Retentie: {t['retention_rate']:.0%} vs. {ctrl['retention_rate']:.0%} "
            f"(z={z_retention:.2f}, confidence {retention_confidence:.0%}). "
            f"Gecombineerde confidence: {combined_confidence:.0%}."
        )

        results.append({
            "campaign_id": c.id,
            "shop_id": c.shop_id or 1,
            "campaign_name": c.name,
            "campaign_type": c.campaign_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period_estimated": period_estimated,
            "period_warning": period_warning,
            "direction": direction,
            "treatment": t,
            "control": ctrl,
            "uplift": {
                "spend_per_member_pct": spend_uplift,
                "orders_per_member_pct": freq_uplift,
                "retention_rate_pct": retention_uplift,
            },
            "z_retention": round(z_retention, 3),
            "retention_confidence": retention_confidence,
            "spend_confidence": spend_confidence,
            "combined_confidence": combined_confidence,
            "direction": direction,
            "explanation": explanation,
        })

    return results


_UPLIFT_SIGNAL_TYPES = (
    "campaign_uplift_positive",
    "campaign_uplift_negative",
    "campaign_uplift_neutral",
)


def publish_campaign_uplift_signals(db: Session, run_date: date | None = None) -> int:
    """
    Publiceert IntelligenceSignals voor campagne-uplift.

    Vóór publicatie worden ALLE actieve campaign_uplift_* signalen voor
    dezelfde campagne superseded (ongeacht de richting), zodat nooit een
    positief en een negatief signaal tegelijk actief zijn voor dezelfde
    campagne (reviewer-feedback: direction-reconciliation).
    """
    run_date = run_date or date.today()
    uplift_list = compute_campaign_uplift(db)
    published = 0
    for u in uplift_list:
        campaign_entity_id = str(u["campaign_id"])

        # Bewaar een historische snapshot per run zodat de trend over
        # meerdere runs zichtbaar blijft. Elke run (run_at) krijgt een eigen
        # rij — ook herhaalde runs op dezelfde dag blijven vergelijkbaar.
        db.add(models.CampaignUpliftSnapshot(
            shop_id=u.get("shop_id") or 1,
            campaign_id=u["campaign_id"],
            run_date=run_date,
            spend_uplift_pct=u["uplift"]["spend_per_member_pct"],
            orders_uplift_pct=u["uplift"]["orders_per_member_pct"],
            retention_uplift_pct=u["uplift"]["retention_rate_pct"],
            retention_confidence=u["retention_confidence"],
            combined_confidence=u["combined_confidence"],
            direction=u["direction"],
            treatment_n=u["treatment"]["n"],
            control_n=u["control"]["n"],
        ))

        # Supersede alle actieve uplift-signalen voor deze campagne,
        # ongeacht de richting — zo blijft er altijd maar één actief.
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.engine == "loyalty",
            models.IntelligenceSignal.signal_type.in_(_UPLIFT_SIGNAL_TYPES),
            models.IntelligenceSignal.entity_type == "campaign",
            models.IntelligenceSignal.entity_id == campaign_entity_id,
            models.IntelligenceSignal.status == "active",
        ).update({"status": "superseded"})

        signal_type = f"campaign_uplift_{u['direction']}"
        spend_uplift = u["uplift"]["spend_per_member_pct"]
        dedupe_key = f"loyalty:{signal_type}:campaign:{campaign_entity_id}"
        db.add(models.IntelligenceSignal(
            shop_id=u.get("shop_id") or 1,
            engine="loyalty",
            signal_type=signal_type,
            severity="medium" if u["direction"] in ("positive", "negative") else "info",
            direction=u["direction"],
            entity_type="campaign",
            entity_id=campaign_entity_id,
            entity_name=u["campaign_name"],
            current_value=spend_uplift if spend_uplift is not None else 0.0,
            confidence=u["combined_confidence"],
            explanation=u["explanation"],
            evidence={
                "treatment": u["treatment"],
                "control": u["control"],
                "uplift": u["uplift"],
                "z_retention": u["z_retention"],
                "retention_confidence": u["retention_confidence"],
            },
            sources=["loyalty_campaign_memberships", "loyalty_transactions"],
            suggested_action=(
                "scale_campaign" if u["direction"] == "positive"
                else ("review_campaign" if u["direction"] == "negative" else "monitor_campaign")
            ),
            dedupe_key=dedupe_key,
            model_version=MODEL_VERSION,
        ))
        # Expliciete flush (sessie draait met autoflush=False): een volgende
        # run binnen dezelfde sessie moet dit signaal kunnen superseden,
        # anders klapt de partiële unieke index op actieve dedupe_keys.
        db.flush()
        published += 1
    return published

def _expiry_forecast_monthly(
    db: Session, policy: models.LoyaltyExpiryPolicy, months: int = 6,
    shop_id: int | None = None,
) -> list[dict]:
    """
    Maand-voor-maand verloopcurve voor de komende `months` kalendermaanden.

    Voor elke maandgrens berekenen we cumulatief hoeveel punten (FIFO) tegen
    het einde van die maand de vervalgrens zijn gepasseerd; het verschil
    tussen opeenvolgende grenzen is het verloop in die maand. Al verlopen
    (overdue) punten vallen in de eerste maand — die vervallen bij de
    eerstvolgende expiry-run.

    Set-based: één wallet-query + één gegroepeerde credit-query met
    conditionele sommen per maandgrens, daarna de FIFO-formule in geheugen
    per lid (identiek aan het normale pad van _fifo_expirable_points).
    """
    from sqlalchemy import case

    today = date.today()
    horizon = timedelta(days=policy.expiry_months * 30)

    # Maandgrenzen: einde van deze maand + de volgende (months-1) maanden
    boundaries: list[date] = []
    cursor = today
    for _ in range(months):
        end = _month_end(cursor)
        boundaries.append(end)
        cursor = end + timedelta(days=1)
    # Zelfde grenssemantiek als apply_expiry_run: txn_date < run_date - horizon
    cutoffs = [b - horizon for b in boundaries]

    def _bucket(boundary: date, pts: int) -> dict:
        return {
            "month": boundary.strftime("%Y-%m"),
            "label": f"{_NL_MONTHS[boundary.month - 1]} {boundary.year}",
            "points": int(pts),
            "eur": round(pts * POINT_VALUE_EUR, 2),
        }

    wallet_q = db.query(models.LoyaltyWallet).filter(
        models.LoyaltyWallet.balance_points > 0
    )
    if shop_id is not None:
        wallet_q = wallet_q.join(
            models.LoyaltyMember,
            models.LoyaltyMember.id == models.LoyaltyWallet.member_id,
        ).filter(models.LoyaltyMember.shop_id == shop_id)
    wallets = wallet_q.all()
    if not wallets:
        return [_bucket(b, 0) for b in boundaries]

    member_ids = [w.member_id for w in wallets]
    sums = [
        func.coalesce(func.sum(case(
            (models.LoyaltyTransaction.txn_date < c,
             models.LoyaltyTransaction.points_delta),
            else_=0,
        )), 0).label(f"c{i}")
        for i, c in enumerate(cutoffs)
    ]
    rows = (db.query(models.LoyaltyTransaction.member_id, *sums)
            .filter(models.LoyaltyTransaction.member_id.in_(member_ids),
                    models.LoyaltyTransaction.txn_type.in_(list(_CREDIT_TYPES)))
            .group_by(models.LoyaltyTransaction.member_id)
            .all())
    earned_by_member = {r[0]: [int(r[i + 1] or 0) for i in range(months)]
                        for r in rows}

    cumulative = [0] * months
    for w in wallets:
        earned = earned_by_member.get(w.member_id)
        if not earned:
            continue
        balance = int(w.balance_points or 0)
        redeemed = int(w.lifetime_redeemed or 0)
        expired = int(w.lifetime_expired or 0)
        for i in range(months):
            earned_old = earned[i]
            if earned_old <= 0:
                continue
            # FIFO (zelfde formule als _fifo_expirable_points, normaal pad)
            redeems_hitting_old = min(redeemed, earned_old)
            still_live_old = max(0, earned_old - redeems_hitting_old - expired)
            cumulative[i] += min(balance, still_live_old)

    forecast = []
    prev = 0
    for boundary, cum in zip(boundaries, cumulative):
        pts = max(0, cum - prev)
        prev = max(prev, cum)
        forecast.append(_bucket(boundary, pts))
    return forecast


def _loyalty_shop_ids(db: Session) -> list[int]:
    """Alle shop_ids waarvoor loyalty-leden bestaan."""
    rows = db.query(func.distinct(models.LoyaltyMember.shop_id)).all()
    return sorted(int(r[0] or 1) for r in rows)
