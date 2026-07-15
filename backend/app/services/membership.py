"""Membership helpers: free-trial grant on verification and activate/extend."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc, update
from sqlalchemy.orm import Session

from app.models import Membership
from app.models.enums import MembershipStatus
from app.services import config_service

TRIAL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def grant_free_trial_if_eligible(db: Session, driver_id: int) -> Membership | None:
    """On verification, give a 30-day free_trial membership if the promo is on
    and the driver has no membership yet (rule: first-month-free)."""
    if not config_service.get_bool(db, "free_trial_first_month"):
        return None
    existing = db.query(Membership.id).filter_by(driver_id=driver_id).first()
    if existing is not None:
        return None
    now = _now()
    m = Membership(
        driver_id=driver_id,
        status=MembershipStatus.free_trial,
        period_start=now,
        period_end=now + timedelta(days=TRIAL_DAYS),
        amount_paid=Decimal("0"),
    )
    db.add(m)
    return m


def activate(
    db: Session,
    driver_id: int,
    months: int,
    amount_paid: Decimal,
    status: MembershipStatus,
    payment_reference: str | None,
) -> Membership:
    now = _now()
    m = Membership(
        driver_id=driver_id,
        status=status,
        period_start=now,
        period_end=now + timedelta(days=30 * months),
        amount_paid=amount_paid,
        payment_reference=payment_reference,
    )
    db.add(m)
    return m


def expire_lapsed(db: Session) -> int:
    """Flip active/free_trial memberships past their period_end to expired, so the
    status column stays honest (claim access is already gated on period_end, but
    reporting and admin views rely on the status). Returns rows changed."""
    result = db.execute(
        update(Membership)
        .where(
            Membership.status.in_(
                [MembershipStatus.active, MembershipStatus.free_trial]
            ),
            Membership.period_end < _now(),
        )
        .values(status=MembershipStatus.expired)
    )
    return result.rowcount


def extend(db: Session, driver_id: int, months: int) -> Membership | None:
    """Extend the driver's latest membership by N months from its current end
    (or from now if already lapsed)."""
    m = (
        db.query(Membership)
        .filter_by(driver_id=driver_id)
        .order_by(desc(Membership.period_end))
        .first()
    )
    if m is None:
        return None
    base = max(m.period_end, _now())
    m.period_end = base + timedelta(days=30 * months)
    m.status = MembershipStatus.active
    return m
