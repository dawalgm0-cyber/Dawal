"""Rider-facing booking endpoints (Checkpoint 1): create + OTP verify + status.

Claim-link generation on OTP success is intentionally deferred to Checkpoint 2
(rule 4.2); the hook point is marked below.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Booking, BlacklistEntry, ConsentLog, Driver, Rating, Rider
from app.models.enums import BlacklistEntityType, BookingStatus
from app.schemas.booking import (
    BookingActionResponse,
    BookingCreate,
    BookingCreateResponse,
    BookingStatusResponse,
    ConfirmPickupRequest,
    OtpVerifyRequest,
    OtpVerifyResponse,
    RateRequest,
)
from app.services import booking_ops, config_service, otp
from app.services.sms import SmsError

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

# Reasons from the OTP service that should read as client errors.
_OTP_MESSAGES = {
    "no_code": "No active verification code. Please request a new booking.",
    "expired": "Your verification code has expired. Please book again.",
    "too_many_attempts": "Too many incorrect attempts. Please book again.",
    "bad_code": "Incorrect verification code.",
}


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _phone_blacklisted(db: Session, phone: str) -> bool:
    return (
        db.query(BlacklistEntry)
        .filter(
            BlacklistEntry.entity_type == BlacklistEntityType.phone,
            BlacklistEntry.entity_ref == phone,
        )
        .first()
        is not None
    )


@router.post("", response_model=BookingCreateResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate, request: Request, db: Session = Depends(get_db)
):
    phone = payload.phone

    # 1. Find or create the rider (phone is the identity key).
    rider = db.query(Rider).filter_by(phone=phone).one_or_none()
    if rider is not None and rider.blacklisted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account cannot book.")
    if _phone_blacklisted(db, phone):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account cannot book.")

    if rider is None:
        rider = Rider(name=payload.name, phone=phone)
        db.add(rider)
        db.flush()
    else:
        rider.name = payload.name

    # 2. Anti-fraud rate limit (rule 4.6): cap unconfirmed (pending) bookings
    #    per phone per rolling 24h.
    limit = config_service.get_int(db, "booking_rate_limit_per_phone_per_day")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    pending_count = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.rider_id == rider.id,
            Booking.status == BookingStatus.pending,
            Booking.created_at >= since,
        )
        .scalar()
    )
    if pending_count >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many pending bookings. Please verify or wait before booking again.",
        )

    # 3. PDPP consent: schema guarantees consent is True here. Record it.
    rider.consent_given_at = datetime.now(timezone.utc)

    # 4. Area matching (rule 4.1). No match -> area_id stays null; the booking is
    #    surfaced as unassigned only after OTP so we never task admins with
    #    unverified (possibly fake) bookings.
    from app.services.geo import match_area

    area = match_area(db, payload.pickup_lat, payload.pickup_lng)

    booking = Booking(
        rider_id=rider.id,
        area_id=area.id if area else None,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        pickup_address_text=payload.pickup_address_text,
        destination_text=payload.destination_text,
        ride_type=payload.ride_type,
        status=BookingStatus.pending,
        rider_access_token=secrets.token_urlsafe(24),
    )
    db.add(booking)
    db.flush()

    # 5. Consent log with IP (rule 4.7).
    db.add(
        ConsentLog(
            rider_id=rider.id,
            booking_id=booking.id,
            consent_type="data_sharing",
            ip_address=_client_ip(request),
        )
    )

    # 6. Issue OTP (rule 4.6). If the SMS gateway fails, don't leak a 500 — roll
    #    the whole booking back and return a clean, retryable error (the booking
    #    is useless without a deliverable code anyway).
    try:
        otp.create_and_send(db, phone=phone, booking_id=booking.id)
    except SmsError:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "We couldn't send your verification code right now. Please try again shortly.",
        )

    db.commit()
    return BookingCreateResponse(
        id=booking.id,
        status=booking.status,
        area_id=area.id if area else None,
        area_name=area.name if area else None,
        message=f"Verification code sent to {phone}.",
        rider_token=booking.rider_access_token,
    )


@router.post("/{booking_id}/verify-otp", response_model=OtpVerifyResponse)
def verify_otp(
    booking_id: int, payload: OtpVerifyRequest, db: Session = Depends(get_db)
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This booking is no longer awaiting verification."
        )

    result = otp.verify(db, booking_id=booking_id, code=payload.code)
    if not result.ok:
        db.commit()  # persist the incremented attempt counter on bad codes
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            _OTP_MESSAGES.get(result.reason, "Verification failed."),
        )

    # Phone verified. Move the booking forward. With an area -> posted (ready for
    # a claim link in Checkpoint 2); without -> unassigned for admin assignment.
    if booking.area_id is not None:
        booking.status = BookingStatus.posted
        booking.posted_at = datetime.now(timezone.utc)
        message = "Verified. Looking for a driver."
        # Generate the single-use claim link + PII-free job post (rule 4.2).
        from app.services.claim import generate_claim_link

        generate_claim_link(db, booking)
    else:
        booking.status = BookingStatus.unassigned
        message = "Verified. We're matching your pickup to an area."

    db.commit()
    return OtpVerifyResponse(id=booking.id, status=booking.status, message=message)


@router.get("/{booking_id}/status", response_model=BookingStatusResponse)
def booking_status(
    booking_id: int,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    resp = BookingStatusResponse.model_validate(booking)
    # Enrich with driver contact only for the rider holding the access token.
    if (
        token
        and booking.rider_access_token
        and secrets.compare_digest(token, booking.rider_access_token)
        and booking.assigned_driver_id is not None
    ):
        driver = db.get(Driver, booking.assigned_driver_id)
        if driver is not None:
            resp.driver_name = driver.name
            resp.driver_phone = driver.phone
    return resp


def _authorize_rider(db: Session, booking_id: int, token: str) -> Booking:
    """Authorize a rider action by either the SMS confirm token or the browser
    rider-access token."""
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    ok = any(
        stored and secrets.compare_digest(token, stored)
        for stored in (booking.confirm_token, booking.rider_access_token)
    )
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid confirmation link.")
    return booking


@router.post("/{booking_id}/confirm-pickup", response_model=BookingActionResponse)
def confirm_pickup(
    booking_id: int, payload: ConfirmPickupRequest, db: Session = Depends(get_db)
):
    booking = _authorize_rider(db, booking_id, payload.confirm_token)
    if booking.status == BookingStatus.completed:
        return BookingActionResponse(id=booking.id, status=booking.status,
                                     message="Already confirmed.")
    if booking.status != BookingStatus.claimed:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This booking cannot be confirmed in its current state.")
    booking_ops.confirm_pickup(db, booking)
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message="Thank you — pickup confirmed.")


@router.post("/{booking_id}/rate", response_model=BookingActionResponse)
def rate(booking_id: int, payload: RateRequest, db: Session = Depends(get_db)):
    booking = _authorize_rider(db, booking_id, payload.confirm_token)
    if booking.status != BookingStatus.completed:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "You can rate only after confirming the trip.")
    if booking.assigned_driver_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No driver to rate.")
    if db.query(Rating).filter_by(booking_id=booking.id).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already rated this trip.")
    db.add(Rating(booking_id=booking.id, driver_id=booking.assigned_driver_id,
                  rider_id=booking.rider_id, rating_value=payload.rating_value,
                  comment=payload.comment))
    # Ratings feed standing (rule 4.8).
    from app.services import standing
    standing.recalc(db, booking.assigned_driver_id)
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message="Thank you for your feedback.")
