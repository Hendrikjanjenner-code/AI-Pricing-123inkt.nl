"""
Loyalty & Customer Value Intelligence API — /api/loyalty (masterprompt §22).

Er is nog geen live loyalty-databron aangesloten: data komt binnen via het
uploads-framework (routes/uploads.py: loyalty-members / loyalty-transactions)
of via de expliciet gemarkeerde demodata-seed (§64.5, is_demo_data=True).
"""
from datetime import date, datetime, timedelta
import random
import string

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from engine import loyalty_intelligence as li

router = APIRouter(prefix="/api/loyalty", tags=["loyalty"])


def _member_dict(m: models.LoyaltyMember, wallet: models.LoyaltyWallet | None = None) -> dict:
    return {
        "id": m.id,
        "pseudonymous_customer_id": m.pseudonymous_customer_id,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        "tier_code": m.tier_code,
        "status": m.status,
        "referral_code": m.referral_code,
        "referred_by": m.referred_by,
        "is_demo_data": bool(m.is_demo_data),
        "balance_points": int(wallet.balance_points) if wallet else 0,
        "lifetime_earned": int(wallet.lifetime_earned or 0) if wallet else 0,
        "lifetime_redeemed": int(wallet.lifetime_redeemed or 0) if wallet else 0,
    }


@router.get("/overview")
def loyalty_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Dashboard-samenvatting: leden, tiers, punten, liability, fraude, demoflag."""
    total = db.query(func.count(models.LoyaltyMember.id)).scalar() or 0
    demo = db.query(func.count(models.LoyaltyMember.id)).filter(
        models.LoyaltyMember.is_demo_data == True  # noqa: E712
    ).scalar() or 0
    by_tier = dict(db.query(
        models.LoyaltyMember.tier_code, func.count(models.LoyaltyMember.id)
    ).group_by(models.LoyaltyMember.tier_code).all())
    txns = db.query(func.count(models.LoyaltyTransaction.id)).scalar() or 0
    cutoff = date.today() - timedelta(days=30)
    earned_30d = db.query(func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0)).filter(
        models.LoyaltyTransaction.txn_type == "earn",
        models.LoyaltyTransaction.txn_date >= cutoff,
    ).scalar() or 0
    redeemed_30d = db.query(func.coalesce(func.sum(models.LoyaltyTransaction.points_delta), 0)).filter(
        models.LoyaltyTransaction.txn_type == "redeem",
        models.LoyaltyTransaction.txn_date >= cutoff,
    ).scalar() or 0
    open_fraud = db.query(func.count(models.LoyaltyFraudSignal.id)).filter(
        models.LoyaltyFraudSignal.status == "open"
    ).scalar() or 0
    latest_run = db.query(func.max(models.CustomerValueScore.run_date)).scalar()
    segs = {}
    if latest_run:
        segs = dict(db.query(
            models.CustomerValueScore.value_segment, func.count(models.CustomerValueScore.id)
        ).filter(models.CustomerValueScore.run_date == latest_run)
         .group_by(models.CustomerValueScore.value_segment).all())
    return {
        "members_total": int(total),
        "members_demo": int(demo),
        "contains_demo_data": demo > 0,
        "members_by_tier": {k or "onbekend": int(v) for k, v in by_tier.items()},
        "transactions_total": int(txns),
        "points_earned_30d": int(earned_30d),
        "points_redeemed_30d": abs(int(redeemed_30d)),
        "liability": li.liability_summary(db),
        "open_fraud_signals": int(open_fraud),
        "value_segments": {k or "onbekend": int(v) for k, v in segs.items()},
        "last_intelligence_run": latest_run.isoformat() if latest_run else None,
        "ledger_mismatches": len(li.verify_ledger_integrity(db)),
    }


@router.get("/tiers")
def list_tiers(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    li.ensure_default_tiers(db)
    return [
        {"code": t.code, "name": t.name, "min_points_12m": t.min_points_12m,
         "earn_multiplier": t.earn_multiplier, "rank": t.rank,
         "members": db.query(func.count(models.LoyaltyMember.id)).filter(
             models.LoyaltyMember.tier_code == t.code).scalar() or 0}
        for t in db.query(models.LoyaltyTier).order_by(models.LoyaltyTier.rank).all()
    ]


@router.get("/members")
def list_members(
    tier: str | None = Query(None),
    segment: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.LoyaltyMember)
    if tier:
        q = q.filter(models.LoyaltyMember.tier_code == tier)
    if search:
        q = q.filter(models.LoyaltyMember.pseudonymous_customer_id.ilike(f"%{search}%"))
    total = q.count()
    members = q.order_by(models.LoyaltyMember.id).offset(offset).limit(limit).all()
    wallets = {w.member_id: w for w in db.query(models.LoyaltyWallet).filter(
        models.LoyaltyWallet.member_id.in_([m.id for m in members])).all()}
    latest_run = db.query(func.max(models.CustomerValueScore.run_date)).scalar()
    scores = {}
    if latest_run:
        for s in db.query(models.CustomerValueScore).filter(
            models.CustomerValueScore.run_date == latest_run,
            models.CustomerValueScore.member_id.in_([m.id for m in members]),
        ).all():
            scores[s.member_id] = s
    items = []
    for m in members:
        d = _member_dict(m, wallets.get(m.id))
        s = scores.get(m.id)
        if s:
            d.update({
                "value_segment": s.value_segment,
                "clv_estimate": float(s.clv_estimate or 0),
                "churn_risk": s.churn_risk,
                "next_best_action": s.next_best_action,
            })
        items.append(d)
    if segment:
        items = [i for i in items if i.get("value_segment") == segment]
    return {"total": total, "items": items, "offset": offset, "limit": limit}


@router.get("/members/{member_id}")
def member_detail(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    m = db.query(models.LoyaltyMember).filter(models.LoyaltyMember.id == member_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Lid niet gevonden")
    wallet = db.query(models.LoyaltyWallet).filter(
        models.LoyaltyWallet.member_id == member_id).first()
    txns = db.query(models.LoyaltyTransaction).filter(
        models.LoyaltyTransaction.member_id == member_id
    ).order_by(models.LoyaltyTransaction.txn_date.desc(),
               models.LoyaltyTransaction.id.desc()).limit(200).all()
    score = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.member_id == member_id
    ).order_by(models.CustomerValueScore.run_date.desc()).first()
    vouchers = db.query(models.LoyaltyVoucher).filter(
        models.LoyaltyVoucher.member_id == member_id).all()
    frauds = db.query(models.LoyaltyFraudSignal).filter(
        models.LoyaltyFraudSignal.member_id == member_id,
        models.LoyaltyFraudSignal.status == "open",
    ).all()
    return {
        **_member_dict(m, wallet),
        "transactions": [
            {"id": t.id, "date": t.txn_date.isoformat(), "type": t.txn_type,
             "points_delta": t.points_delta, "order_reference": t.order_reference,
             "order_value": float(t.order_value) if t.order_value is not None else None,
             "description": t.description, "is_demo_data": bool(t.is_demo_data)}
            for t in txns
        ],
        "customer_value": None if not score else {
            "run_date": score.run_date.isoformat(),
            "recency_days": score.recency_days,
            "frequency_12m": score.frequency_12m,
            "monetary_12m": float(score.monetary_12m or 0),
            "avg_order_value": float(score.avg_order_value or 0),
            "clv_estimate": float(score.clv_estimate or 0),
            "churn_risk": score.churn_risk,
            "retention_probability": score.retention_probability,
            "value_segment": score.value_segment,
            "confidence": score.confidence,
            "explanation": score.explanation,
            "next_best_action": score.next_best_action,
            "nba_reason": score.nba_reason,
            "nba_expected_value": float(score.nba_expected_value or 0),
            "nba_alternative": score.nba_alternative,
            "nba_alternative_cost": float(score.nba_alternative_cost or 0),
        },
        "vouchers": [
            {"id": v.id, "code": v.code, "value": float(v.monetary_value or 0),
             "status": v.status,
             "issued_at": v.issued_at.isoformat() if v.issued_at else None,
             "expires_at": v.expires_at.isoformat() if v.expires_at else None}
            for v in vouchers
        ],
        "fraud_signals": [
            {"type": f.fraud_type, "severity": f.severity, "score": f.score,
             "explanation": f.explanation} for f in frauds
        ],
    }


@router.get("/customer-value")
def customer_value_overview(
    segment: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    latest_run = db.query(func.max(models.CustomerValueScore.run_date)).scalar()
    if not latest_run:
        return {"run_date": None, "items": [], "summary": {}}
    q = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.run_date == latest_run)
    if segment:
        q = q.filter(models.CustomerValueScore.value_segment == segment)
    scores = q.order_by(models.CustomerValueScore.clv_estimate.desc()).limit(limit).all()
    members = {m.id: m for m in db.query(models.LoyaltyMember).filter(
        models.LoyaltyMember.id.in_([s.member_id for s in scores])).all()}
    all_run = db.query(models.CustomerValueScore).filter(
        models.CustomerValueScore.run_date == latest_run).all()
    total_clv = sum(float(s.clv_estimate or 0) for s in all_run)
    avg_churn = (sum(s.churn_risk or 0 for s in all_run) / len(all_run)) if all_run else 0
    return {
        "run_date": latest_run.isoformat(),
        "summary": {
            "members_scored": len(all_run),
            "total_clv_estimate": round(total_clv, 2),
            "avg_churn_risk": round(avg_churn, 3),
            "avg_retention": round(1 - avg_churn, 3),
        },
        "items": [
            {
                "member_id": s.member_id,
                "pseudonymous_customer_id": members[s.member_id].pseudonymous_customer_id
                    if s.member_id in members else str(s.member_id),
                "tier_code": members[s.member_id].tier_code if s.member_id in members else None,
                "is_demo_data": bool(members[s.member_id].is_demo_data) if s.member_id in members else False,
                "recency_days": s.recency_days,
                "frequency_12m": s.frequency_12m,
                "monetary_12m": float(s.monetary_12m or 0),
                "clv_estimate": float(s.clv_estimate or 0),
                "churn_risk": s.churn_risk,
                "retention_probability": s.retention_probability,
                "value_segment": s.value_segment,
                "confidence": s.confidence,
                "next_best_action": s.next_best_action,
                "nba_expected_value": float(s.nba_expected_value or 0),
                "nba_alternative_cost": float(s.nba_alternative_cost or 0),
            } for s in scores
        ],
    }


@router.get("/liability")
def liability(db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    summary = li.liability_summary(db)
    per_tier = []
    for t in db.query(models.LoyaltyTier).order_by(models.LoyaltyTier.rank).all():
        pts = db.query(func.coalesce(func.sum(models.LoyaltyWallet.balance_points), 0)).join(
            models.LoyaltyMember, models.LoyaltyMember.id == models.LoyaltyWallet.member_id
        ).filter(models.LoyaltyMember.tier_code == t.code).scalar() or 0
        per_tier.append({"tier": t.code, "name": t.name, "points": int(pts),
                         "liability_eur": round(int(pts) * li.POINT_VALUE_EUR, 2)})
    return {**summary, "per_tier": per_tier}


@router.get("/fraud")
def fraud_signals(
    status: str = Query("open"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.LoyaltyFraudSignal)
    if status != "all":
        q = q.filter(models.LoyaltyFraudSignal.status == status)
    rows = q.order_by(models.LoyaltyFraudSignal.score.desc()).limit(200).all()
    members = {m.id: m for m in db.query(models.LoyaltyMember).filter(
        models.LoyaltyMember.id.in_([r.member_id for r in rows])).all()}
    return [
        {"id": f.id, "member_id": f.member_id,
         "pseudonymous_customer_id": members[f.member_id].pseudonymous_customer_id
             if f.member_id in members else str(f.member_id),
         "run_date": f.run_date.isoformat(), "fraud_type": f.fraud_type,
         "severity": f.severity, "score": f.score, "explanation": f.explanation,
         "evidence": f.evidence, "status": f.status}
        for f in rows
    ]

def _campaign_dict(c: models.LoyaltyCampaign, db: Session) -> dict:
    counts = dict(db.query(
        models.LoyaltyCampaignMembership.group_type,
        func.count(models.LoyaltyCampaignMembership.id),
    ).filter(models.LoyaltyCampaignMembership.campaign_id == c.id)
     .group_by(models.LoyaltyCampaignMembership.group_type).all())
    bonus_pts = db.query(func.coalesce(
        func.sum(models.LoyaltyTransaction.points_delta), 0)).filter(
        models.LoyaltyTransaction.campaign_id == c.id).scalar() or 0
    return {
        "id": c.id, "name": c.name, "campaign_type": c.campaign_type,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "status": c.status, "bonus_multiplier": c.bonus_multiplier,
        "control_group_pct": c.control_group_pct,
        "target_segment": c.target_segment,
        "treatment_members": int(counts.get("treatment", 0)),
        "control_members": int(counts.get("control", 0)),
        "bonus_points_issued": int(bonus_pts),
        "is_demo_data": bool(c.is_demo_data),
    }
@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    return [_campaign_dict(c, db) for c in db.query(models.LoyaltyCampaign).order_by(
        models.LoyaltyCampaign.created_at.desc()).all()]

@router.get("/campaigns/{campaign_id}/uplift")
def campaign_uplift(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Uplift-analyse voor een specifieke campagne (§22): besteding, frequentie en
    retentie van treatment vs. control in de campagneperiode, met significantie-
    indicatie (z-score, confidence) en uitleg.
    """
    c = db.query(models.LoyaltyCampaign).filter(
        models.LoyaltyCampaign.id == campaign_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campagne niet gevonden")

    uplift_list = li.compute_campaign_uplift(db, campaign_id=campaign_id)
    if not uplift_list:
        # Campagne bestaat maar heeft geen treatment én control leden
        return {
            **_campaign_dict(c, db),
            "uplift": None,
            "message": "Geen uplift-analyse beschikbaar — campagne heeft geen treatment- én control-leden.",
        }

    u = uplift_list[0]
    return {
        **_campaign_dict(c, db),
        "uplift": u,
        "period_estimated": bool(u.get("period_estimated")),
        "period_warning": u.get("period_warning"),
    }
@router.post("/run")
def run_engine(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    """Draai de volledige Loyalty & Customer Value Intelligence-run."""
    li.ensure_default_tiers(db)
    result = li.run_loyalty_engine(db)
    db.add(models.AuditLog(entity_type="loyalty_engine", entity_id="run",
                           action="loyalty_engine_run", performed_by=current_user.username,
                           details=str(result)))
    db.commit()
    return result


@router.post("/seed-demo")
def seed_demo(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Genereer expliciet gemarkeerde demodata (§64.5): 60 leden, 12 maanden
    transacties, vouchers, één campagne met controlegroep en enkele bewust
    verdachte patronen zodat fraudedetectie demonstreerbaar is.
    Alle rijen krijgen is_demo_data=True.
    """
    existing = db.query(func.count(models.LoyaltyMember.id)).filter(
        models.LoyaltyMember.is_demo_data == True).scalar() or 0  # noqa: E712
    if existing:
        raise HTTPException(status_code=409, detail=f"Er zijn al {existing} demo-leden; verwijder demodata eerst via DELETE /api/loyalty/demo-data")

    li.ensure_default_tiers(db)
    rnd = random.Random(42)
    today = date.today()

    reward = models.LoyaltyReward(name="€5 waardebon", reward_type="voucher",
                                  points_cost=500, monetary_value=5.0, is_demo_data=True)
    db.add(reward)
    db.flush()

    campaign = models.LoyaltyCampaign(
        name="[DEMO] Dubbele punten oktober", campaign_type="double_points",
        start_date=today - timedelta(days=45), end_date=today - timedelta(days=15),
        status="completed", bonus_multiplier=2.0, control_group_pct=20.0,
        target_segment="all", is_demo_data=True,
    )
    db.add(campaign)
    db.flush()

    members = []
    for i in range(60):
        pid = f"DEMO-CUST-{i+1:04d}"
        m = models.LoyaltyMember(
            pseudonymous_customer_id=pid,
            joined_at=today - timedelta(days=rnd.randint(60, 720)),
            referral_code="RC" + "".join(rnd.choices(string.ascii_uppercase, k=6)),
            consent_marketing=rnd.random() < 0.6,
            is_demo_data=True,
        )
        db.add(m)
        members.append(m)
    db.flush()

    # Referral-ring: lid 0 heeft 8 inactieve referrals (leden 50-57)
    for m in members[50:58]:
        m.referred_by = members[0].pseudonymous_customer_id

    for idx, m in enumerate(members):
        # Profielen: 0-9 high value, 10-29 mid, 30-44 low, 45-49 churn, 50-57 inactief, 58-59 fraude
        if idx < 10:
            n_orders, aov = rnd.randint(8, 16), rnd.uniform(60, 140)
        elif idx < 30:
            n_orders, aov = rnd.randint(3, 7), rnd.uniform(30, 80)
        elif idx < 45:
            n_orders, aov = rnd.randint(1, 3), rnd.uniform(15, 40)
        elif idx < 50:
            n_orders, aov = rnd.randint(2, 4), rnd.uniform(30, 60)  # maar lang geleden
        elif idx < 58:
            n_orders = 0
            aov = 0.0
        else:
            n_orders, aov = rnd.randint(4, 6), rnd.uniform(20, 40)

        for o in range(n_orders):
            if 45 <= idx < 50:
                d = today - timedelta(days=rnd.randint(200, 360))  # churn-risico
            else:
                d = today - timedelta(days=rnd.randint(1, 360))
            val = round(aov * rnd.uniform(0.7, 1.3), 2)
            pts = int(val * (8 if idx >= 58 else 1))  # fraude: abnormale earn-rate
            try:
                li.apply_ledger_entry(
                    db, m, d, "earn", max(pts, 1),
                    order_reference=f"DEMO-ORD-{idx}-{o}", order_value=val,
                    description="[DEMO] aankoop", is_demo_data=True,
                )
            except li.LedgerError:
                pass

        # Redemptions voor actieve leden
        wallet = li.ensure_wallet(db, m.id)
        if wallet.balance_points >= 500 and rnd.random() < 0.5:
            n_red = 4 if idx >= 58 else 1  # fraude: rapid redemption
            for r in range(n_red):
                if wallet.balance_points < 500:
                    break
                v = models.LoyaltyVoucher(
                    member_id=m.id, reward_id=reward.id,
                    code=f"DEMO-VCH-{idx}-{r}-" + "".join(rnd.choices(string.digits, k=4)),
                    monetary_value=5.0, status="issued",
                    issued_at=today - timedelta(days=rnd.randint(0, 25)),
                    expires_at=today + timedelta(days=rnd.randint(10, 90)),
                    is_demo_data=True,
                )
                db.add(v)
                db.flush()
                try:
                    li.apply_ledger_entry(
                        db, m, today - timedelta(days=rnd.randint(0, 25)),
                        "redeem", -500, voucher_id=v.id,
                        description="[DEMO] voucher ingewisseld", is_demo_data=True,
                    )
                except li.LedgerError:
                    break

    # Campagne-toewijzing met controlegroep + bonuspunten voor treatment
    for idx, m in enumerate(members[:40]):
        group = "control" if idx % 5 == 0 else "treatment"
        db.add(models.LoyaltyCampaignMembership(
            campaign_id=campaign.id, member_id=m.id, group_type=group))
        if group == "treatment" and idx < 20:
            try:
                li.apply_ledger_entry(
                    db, m, today - timedelta(days=rnd.randint(15, 45)),
                    "campaign_bonus", rnd.randint(50, 200), campaign_id=campaign.id,
                    description="[DEMO] campagnebonus", is_demo_data=True,
                )
            except li.LedgerError:
                pass

    db.commit()
    result = li.run_loyalty_engine(db)
    return {"message": "Demodata aangemaakt (expliciet gemarkeerd met is_demo_data=True)",
            "members_created": len(members), "engine_run": result}


@router.get("/expiry-policy")
def get_expiry_policy(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Haal het huidige verloopbeleid voor punten op."""
    policy = li._get_expiry_policy(db)
    db.commit()
    return {
        "enabled": policy.enabled,
        "expiry_months": policy.expiry_months,
        "warn_days_before": policy.warn_days_before,
        "description": (
            f"Punten verlopen {policy.expiry_months} maanden na verdienen (FIFO). "
            f"Leden worden {policy.warn_days_before} dagen van tevoren gewaarschuwd."
            if policy.enabled else "Verloopbeleid is uitgeschakeld."
        ),
    }


@router.put("/expiry-policy")
def update_expiry_policy(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Pas het verloopbeleid aan.

    Body: { "enabled": bool, "expiry_months": int (1-120), "warn_days_before": int (7-180) }
    """
    policy = li._get_expiry_policy(db)
    if "enabled" in body:
        policy.enabled = bool(body["enabled"])
    if "expiry_months" in body:
        v = int(body["expiry_months"])
        if not 1 <= v <= 120:
            raise HTTPException(status_code=422, detail="expiry_months moet tussen 1 en 120 liggen")
        policy.expiry_months = v
    if "warn_days_before" in body:
        v = int(body["warn_days_before"])
        if not 7 <= v <= 180:
            raise HTTPException(status_code=422, detail="warn_days_before moet tussen 7 en 180 liggen")
        policy.warn_days_before = v
    db.add(models.AuditLog(
        entity_type="loyalty_expiry_policy", entity_id="1",
        action="update_expiry_policy", performed_by=current_user.username,
        details=str(body),
    ))
    db.commit()
    return {
        "enabled": policy.enabled,
        "expiry_months": policy.expiry_months,
        "warn_days_before": policy.warn_days_before,
    }


@router.get("/expiring-soon")
def expiring_soon(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Leden met punten die binnenkort verlopen op basis van het verloopbeleid.
    Gesorteerd op urgentie (kortste vervaltijd eerst).
    """
    items = li.expiring_soon_members(db)
    policy = li._get_expiry_policy(db)
    db.commit()
    return {
        "policy": {
            "enabled": policy.enabled,
            "expiry_months": policy.expiry_months,
            "warn_days_before": policy.warn_days_before,
        },
        "total": len(items),
        "items": items,
    }


@router.post("/run-expiry")
def run_expiry(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Voer een expiry-run uit: genereer expire-ledger-entries voor alle leden
    waarvan punten de vervalgrens hebben overschreden.

    Met `?dry_run=true` worden geen mutaties geschreven — alleen een vooruitblik.
    """
    result = li.apply_expiry_run(db, dry_run=dry_run)
    if not dry_run:
        db.add(models.AuditLog(
            entity_type="loyalty_expiry", entity_id="run",
            action="expiry_run", performed_by=current_user.username,
            details=str(result),
        ))
        db.commit()
    return result


@router.delete("/demo-data")
def delete_demo_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """Verwijder uitsluitend als demo gemarkeerde loyaltydata."""
    demo_member_ids = [r[0] for r in db.query(models.LoyaltyMember.id).filter(
        models.LoyaltyMember.is_demo_data == True).all()]  # noqa: E712
    deleted = {"members": len(demo_member_ids)}
    if demo_member_ids:
        for model, col in [
            (models.LoyaltyTransaction, models.LoyaltyTransaction.member_id),
            (models.LoyaltyWallet, models.LoyaltyWallet.member_id),
            (models.LoyaltyVoucher, models.LoyaltyVoucher.member_id),
            (models.CustomerValueScore, models.CustomerValueScore.member_id),
            (models.LoyaltyFraudSignal, models.LoyaltyFraudSignal.member_id),
            (models.LoyaltyCampaignMembership, models.LoyaltyCampaignMembership.member_id),
        ]:
            deleted[model.__tablename__] = db.query(model).filter(
                col.in_(demo_member_ids)).delete(synchronize_session=False)
        db.query(models.LoyaltyMember).filter(
            models.LoyaltyMember.id.in_(demo_member_ids)).delete(synchronize_session=False)
    deleted["campaigns"] = db.query(models.LoyaltyCampaign).filter(
        models.LoyaltyCampaign.is_demo_data == True).delete(synchronize_session=False)  # noqa: E712
    deleted["rewards"] = db.query(models.LoyaltyReward).filter(
        models.LoyaltyReward.is_demo_data == True).delete(synchronize_session=False)  # noqa: E712
    db.commit()
    return {"message": "Demodata verwijderd", "deleted": deleted}
