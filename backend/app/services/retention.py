"""PDPP data retention (rule 4.7). Anonymizes rider PII once their activity is
older than the configured retention window and no dispute is open, and logs each
action to retention_log. Callable now (manual run-now + subject erasure); the
scheduled daily run is wired in Checkpoint 8.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Booking, Dispute, RetentionLog, Rider
from app.models.enums import DisputeStatus
from app.services import config_service

ANON_NAME = "[erased]"
OPEN_DISPUTE_STATES = (DisputeStatus.open, DisputeStatus.investigating)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cutoff(db: Session) -> datetime:
    days = config_service.get_int(db, "pdpp_retention_days")
    return _now() - timedelta(days=days)


def _has_open_dispute(db: Session, rider_id: int) -> bool:
    return (
        db.query(Dispute.id)
        .join(Booking, Dispute.booking_id == Booking.id)
        .filter(Booking.rider_id == rider_id, Dispute.status.in_(OPEN_DISPUTE_STATES))
        .first()
        is not None
    )


def _is_anonymized(rider: Rider) -> bool:
    return rider.name == ANON_NAME or rider.phone.startswith("erased_")


def eligible_rider_ids(db: Session) -> list[int]:
    """Riders whose most recent activity predates the retention window, are not
    already anonymized, and have no open dispute."""
    cut = cutoff(db)
    # newest booking timestamp per rider (NULL if none)
    latest = (
        db.query(Booking.rider_id, func.max(Booking.created_at).label("last"))
        .group_by(Booking.rider_id)
        .subquery()
    )
    rows = (
        db.query(Rider)
        .outerjoin(latest, Rider.id == latest.c.rider_id)
        .filter(
            or_(latest.c.last < cut, latest.c.last.is_(None)),
            Rider.created_at < cut,
        )
        .all()
    )
    return [r.id for r in rows if not _is_anonymized(r) and not _has_open_dispute(db, r.id)]


def scrub_rider(db: Session, rider: Rider, reason: str) -> None:
    """Anonymize a rider's PII and their bookings' PII, logging the action."""
    rider.name = ANON_NAME
    rider.phone = f"erased_{rider.id}"
    rider.consent_given_at = None
    rider.blacklist_reason = None
    for b in db.query(Booking).filter(Booking.rider_id == rider.id).all():
        b.pickup_address_text = None
        b.destination_text = None
        b.pickup_lat = None
        b.pickup_lng = None
    db.add(RetentionLog(entity_type="rider", entity_id=str(rider.id), reason=reason))


def run_retention(db: Session) -> int:
    ids = eligible_rider_ids(db)
    for rid in ids:
        rider = db.get(Rider, rid)
        if rider is not None:
            scrub_rider(db, rider, reason="pdpp_retention_auto")
    return len(ids)
