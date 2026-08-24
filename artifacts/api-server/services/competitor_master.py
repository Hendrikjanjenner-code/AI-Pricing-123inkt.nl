"""
Goedkeurings- en blokkeerstatus op de canonieke competitor-master (taak #288).

De discovery-wachtrij blijft de plek waar beslissingen worden genomen; dit
servicelaagje houdt de canonieke DimCompetitor-rij synchroon zodat schermen en
pipelines de status direct van de master kunnen lezen. Feed-sync/upsert raakt
deze velden nooit aan (zie feed_ingest._reconcile_competitors).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import models
from services.domain_normalize import normalize_domain


def _master_row(db: Session, domain: str) -> models.DimCompetitor:
    """Vind (of maak) de canonieke masterrij voor een (ruwe) domeinnaam.

    Race-safe: een gelijktijdige feed-sync kan dezelfde naam net eerder
    aanmaken; de unieke naamconstraint wordt dan via een savepoint opgevangen
    en de bestaande rij wordt gebruikt (nooit een IntegrityError naar buiten).
    """
    from sqlalchemy.exc import IntegrityError

    canon = normalize_domain(domain) or (domain or "").strip().lower()
    row = db.query(models.DimCompetitor).filter(
        models.DimCompetitor.competitor_name == canon).first()
    if row is None:
        try:
            with db.begin_nested():
                row = models.DimCompetitor(competitor_name=canon)
                db.add(row)
        except IntegrityError:
            row = db.query(models.DimCompetitor).filter(
                models.DimCompetitor.competitor_name == canon).one()
    return row


def sync_master_approval(db: Session, domain: str, status: str,
                         username: Optional[str]) -> models.DimCompetitor:
    """Zet de goedkeuringsstatus (APPROVED/REJECTED/UNREVIEWED) op de master."""
    row = _master_row(db, domain)
    row.approval_status = status
    row.approved_by = username
    row.approved_at = datetime.utcnow()
    return row


def set_master_blocked(db: Session, domain: str, blocked: bool,
                       username: Optional[str]) -> models.DimCompetitor:
    """(De)blokkeer een concurrent op de master."""
    row = _master_row(db, domain)
    row.blocked = blocked
    row.blocked_by = username if blocked else None
    row.blocked_at = datetime.utcnow() if blocked else None
    return row


def blocked_competitor_names(db: Session) -> set[str]:
    """Canonieke namen van geblokkeerde concurrenten (globaal register)."""
    return {n for (n,) in db.query(models.DimCompetitor.competitor_name)
            .filter(models.DimCompetitor.blocked == True).all()}  # noqa: E712


def backfill_master_approvals(db: Session) -> int:
    """Eenmalige migratie: bestaande discovery-beslissingen naar de master.

    Idempotent en niet-destructief: alleen masterrijen die nog UNREVIEWED (of
    NULL, direct na de kolom-migratie) zijn krijgen de wachtrij-beslissing;
    een al gezette masterstatus wordt nooit overschreven. Bij meerdere
    wachtrijrijen per domein wint de meest recente beslissing.
    """
    decided = (db.query(models.CompetitorDiscoveryQueue)
               .filter(models.CompetitorDiscoveryQueue.status.in_(
                   ["APPROVED", "REJECTED"]))
               .order_by(models.CompetitorDiscoveryQueue.approved_at.asc().nullsfirst())
               .all())
    if not decided:
        return 0
    # Meest recente beslissing per canoniek domein wint: door de oplopende
    # sortering overschrijft een latere beslissing de eerdere in deze dict.
    latest_by_canon: dict[str, models.CompetitorDiscoveryQueue] = {}
    for item in decided:
        canon = normalize_domain(item.domain) or (item.domain or "").strip().lower()
        if canon:
            latest_by_canon[canon] = item
    updated = 0
    for canon, item in latest_by_canon.items():
        row = db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name == canon).first()
        if row is None:
            continue  # geen masterrij: niets te migreren
        if row.approval_status not in (None, "UNREVIEWED"):
            continue  # al beslist op de master: nooit overschrijven
        row.approval_status = item.status
        row.approved_by = item.approved_by
        row.approved_at = item.approved_at
        updated += 1
    if updated:
        db.commit()
    return updated
