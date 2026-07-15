"""Claim link generation (rule 4.2) and the atomic claim (rule 4.3).

Rule 4.3 is the highest-risk logic in the system: many drivers may tap the same
link within seconds. The winner is decided by a single conditional UPDATE
(`... WHERE status='posted'`) whose row lock serialises concurrent attempts;
exactly one gets rowcount==1. Membership/credit are checked BEFORE the flip so an
ineligible driver never consumes the booking, and the credit burn is guarded and
run in the SAME transaction so any failure rolls the claim back and leaves the
link open for the next driver.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Area, Booking, ClaimLink, CreditLedger, Driver, Membership, Rider
from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    MembershipStatus,
    VerificationStatus,
)
from app.security import verify_password
from app.services import templates
from app.services.sms import SmsError, get_sms_provider

dispatch_log = logging.getLogger("dawal.dispatch")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- link generation (rule 4.2) -----------------------------------------

def generate_claim_link(db: Session, booking: Booking) -> ClaimLink:
    """Create a single-use, crypto-random claim link for a posted booking and
    log the PII-free job-post text a dispatcher pastes into WhatsApp."""
    token = secrets.token_urlsafe(24)
    link = ClaimLink(
        booking_id=booking.id,
        token=token,
        expires_at=_now() + timedelta(minutes=settings.CLAIM_LINK_TTL_MINUTES),
    )
    db.add(link)
    db.flush()

    claim_url = f"{settings.APP_BASE_URL}/c/{token}"
    area = db.get(Area, booking.area_id) if booking.area_id else None
    text = templates.render(
        db,
        "job_post_text",
        ride_type=booking.ride_type.value,
        area_name=area.name if area else "unassigned",
        pickup_zone=area.name if area else "unknown",  # rough area only, no address/PII
        claim_url=claim_url,
    )
    dispatch_log.info("[JOB POST] booking=%s\n%s", booking.id, text)
    return link


# --- claim (rule 4.3) ----------------------------------------------------

@dataclass
class ClaimOutcome:
    status: str  # claimed | already_claimed | expired | not_found | bad_credentials
    #              | not_verified | membership_inactive | insufficient_credits
    booking_id: int | None = None
    rider_name: str | None = None
    rider_phone: str | None = None
    pickup_address_text: str | None = None
    destination_text: str | None = None


def _has_valid_membership(db: Session, driver_id: int, now: datetime) -> bool:
    # free_trial grants standing too (revenue model: first month free); credits
    # are checked separately and are what actually gate job access.
    return (
        db.query(Membership.id)
        .filter(
            Membership.driver_id == driver_id,
            Membership.status.in_(
                [MembershipStatus.active, MembershipStatus.free_trial]
            ),
            Membership.period_start <= now,
            Membership.period_end >= now,
        )
        .first()
        is not None
    )


def claim_booking(
    db: Session, token: str, driver_phone: str, driver_pin: str
) -> ClaimOutcome:
    now = _now()

    # Read-only guard paths below make no writes, so they need no rollback; the
    # request-scoped session ends the (empty) transaction on close.
    link = db.query(ClaimLink).filter_by(token=token).one_or_none()
    if link is None:
        return ClaimOutcome("not_found")
    if link.used_at is not None:
        return ClaimOutcome("already_claimed", booking_id=link.booking_id)
    if link.expires_at <= now:
        return ClaimOutcome("expired", booking_id=link.booking_id)

    booking = db.get(Booking, link.booking_id)
    if booking is None or booking.status != BookingStatus.posted:
        return ClaimOutcome("already_claimed", booking_id=link.booking_id)

    driver = db.query(Driver).filter_by(phone=driver_phone).one_or_none()
    # Phone + PIN checked first (generic failure), so we never reveal whether a
    # phone is registered or a driver's verification state to a bad guesser.
    if driver is None or driver.pin_hash is None or not verify_password(
        driver_pin, driver.pin_hash
    ):
        return ClaimOutcome("bad_credentials", booking_id=booking.id)
    if driver.verification_status != VerificationStatus.verified:
        return ClaimOutcome("not_verified", booking_id=booking.id)

    # Eligibility checks BEFORE the flip so an ineligible driver never consumes
    # the booking; the link stays open for the next driver (rule 4.3.4).
    if not _has_valid_membership(db, driver.id, now):
        return ClaimOutcome("membership_inactive", booking_id=booking.id)
    if driver.credit_balance < 1:
        return ClaimOutcome("insufficient_credits", booking_id=booking.id)

    # Single-use token the rider will use to confirm pickup (rule 4.4).
    confirm_token = secrets.token_urlsafe(16)

    # Atomic win: only one concurrent UPDATE flips posted->claimed.
    flipped = db.execute(
        update(Booking)
        .where(Booking.id == booking.id, Booking.status == BookingStatus.posted)
        .values(
            status=BookingStatus.claimed,
            assigned_driver_id=driver.id,
            claimed_at=now,
            confirm_token=confirm_token,
        )
    )
    if flipped.rowcount == 0:
        db.rollback()
        return ClaimOutcome("already_claimed", booking_id=booking.id)

    # Guarded credit burn in the same transaction. If the balance vanished under
    # a concurrent claim, roll the whole claim back (un-flips the booking).
    burned = db.execute(
        update(Driver)
        .where(Driver.id == driver.id, Driver.credit_balance >= 1)
        .values(credit_balance=Driver.credit_balance - 1)
    )
    if burned.rowcount == 0:
        db.rollback()
        return ClaimOutcome("insufficient_credits", booking_id=booking.id)

    db.add(
        CreditLedger(
            driver_id=driver.id,
            transaction_type=CreditTxnType.burn,
            amount_credits=-1,
            booking_id=booking.id,
        )
    )
    link.used_at = now
    link.used_by_driver_id = driver.id
    db.commit()

    # Notify the rider a driver is coming, with their one-tap confirm link. The
    # claim is already committed, so an SMS failure must NOT fail the claim —
    # the driver has the job and the credit is burned. Log and carry on.
    rider = db.get(Rider, booking.rider_id)
    # Deep-link into the rider PWA with booking + token so a tap can confirm.
    confirm_url = (
        f"{settings.RIDER_APP_URL}/?confirm={confirm_token}&booking={booking.id}"
    )
    try:
        get_sms_provider().send(
            rider.phone,
            f"A DAWAL driver has accepted your {booking.ride_type.value}. "
            f"After they arrive, confirm here: {confirm_url}",
        )
    except SmsError:
        dispatch_log.warning(
            "confirm SMS failed for booking %s; claim succeeded regardless", booking.id
        )

    # Only now — after a successful, credit-backed claim — release rider PII.
    return ClaimOutcome(
        "claimed",
        booking_id=booking.id,
        rider_name=rider.name,
        rider_phone=rider.phone,
        pickup_address_text=booking.pickup_address_text,
        destination_text=booking.destination_text,
    )
