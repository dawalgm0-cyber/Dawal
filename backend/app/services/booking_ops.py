"""Booking lifecycle operations for rider confirmation and admin no-show/fake
handling (rules 4.4, 4.5). Standing is recalculated inline (rule 4.8)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import BlacklistEntry, Booking, Rider
from app.models.enums import (
    BlacklistEntityType,
    BookingStatus,
    CreditTxnType,
)
from app.services import config_service, credit, standing
from app.services.claim import generate_claim_link

# Standard cost of a claim, refunded when a booking is ruled fake (rule 4.5).
CLAIM_COST_CREDITS = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def confirm_pickup(db: Session, booking: Booking) -> None:
    """Rider confirms the driver arrived: booking -> completed (rule 4.4)."""
    booking.status = BookingStatus.completed
    booking.completed_at = _now()
    if booking.assigned_driver_id is not None:
        standing.recalc(db, booking.assigned_driver_id)


def create_priority_rebook(db: Session, original: Booking) -> Booking:
    """Free priority rebook after a no-show (rule 4.5). A new posted booking the
    dispatcher sees as priority; dispatch to WhatsApp stays manual."""
    rebook = Booking(
        rider_id=original.rider_id,
        area_id=original.area_id,
        pickup_lat=original.pickup_lat,
        pickup_lng=original.pickup_lng,
        pickup_address_text=original.pickup_address_text,
        destination_text=original.destination_text,
        ride_type=original.ride_type,
        status=BookingStatus.posted if original.area_id else BookingStatus.unassigned,
        priority=True,
        rebook_of_booking_id=original.id,
        posted_at=_now() if original.area_id else None,
    )
    db.add(rebook)
    db.flush()
    if rebook.status == BookingStatus.posted:
        generate_claim_link(db, rebook)
    return rebook


def mark_no_show(db: Session, booking: Booking) -> Booking:
    """Admin marks no-show: credit is NOT refunded, driver standing recalcs, and
    the rider gets a free priority rebook (rule 4.5)."""
    booking.status = BookingStatus.no_show
    if booking.assigned_driver_id is not None:
        standing.recalc(db, booking.assigned_driver_id)
    return create_priority_rebook(db, booking)


def flag_fake(db: Session, booking: Booking, admin_id: int) -> None:
    """Admin rules a booking fake after a driver dispute (rule 4.5): refund the
    burned credit, increment the rider's fake counter, blacklist at threshold."""
    booking.status = BookingStatus.fake_flagged

    if booking.assigned_driver_id is not None:
        credit.adjust(
            db,
            booking.assigned_driver_id,
            CLAIM_COST_CREDITS,
            CreditTxnType.refund,
            admin_id,
            reference="fake_flagged",
            booking_id=booking.id,
        )

    rider = db.get(Rider, booking.rider_id)
    if rider is not None:
        rider.fake_report_count = (rider.fake_report_count or 0) + 1
        threshold = config_service.get_int(db, "fake_report_blacklist_threshold")
        if rider.fake_report_count >= threshold and not rider.blacklisted:
            rider.blacklisted = True
            rider.blacklist_reason = "Auto: fake booking reports reached threshold"
            db.add(
                BlacklistEntry(
                    entity_type=BlacklistEntityType.rider,
                    entity_ref=str(rider.id),
                    reason=rider.blacklist_reason,
                    created_by_admin_id=admin_id,
                )
            )


def cancel(db: Session, booking: Booking) -> None:
    booking.status = BookingStatus.cancelled


def override_assign(db: Session, booking: Booking, area_id: int) -> None:
    """Admin assigns an area to an unassigned booking (rule 4.1); once it has an
    area it becomes posted with a claim link."""
    booking.area_id = area_id
    if booking.status == BookingStatus.unassigned:
        booking.status = BookingStatus.posted
        booking.posted_at = _now()
        generate_claim_link(db, booking)


def flag_stale_unconfirmed(db: Session) -> int:
    """Sweep claimed bookings unconfirmed past the configured window and flag
    them pending_review for admin (rule 4.4). Never auto-completes or no-shows.

    Callable now (admin trigger / tests); scheduled wiring lands in Checkpoint 8
    alongside the retention job.
    """
    window_hours = config_service.get_int(db, "no_show_review_window_hours")
    cutoff = _now() - timedelta(hours=window_hours)
    stale = (
        db.query(Booking)
        .filter(
            Booking.status == BookingStatus.claimed,
            Booking.claimed_at < cutoff,
        )
        .all()
    )
    for b in stale:
        b.status = BookingStatus.pending_review
    return len(stale)
