"""Driver-facing claim endpoints. No auth (token-based, single-use per Section 2);
the claiming driver is identified by registered phone. GET is PII-free; POST
releases rider contact only after a successful, credit-backed claim (rule 4.3)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Area, Booking, ClaimLink
from app.models.enums import BookingStatus
from app.schemas.claim import ClaimRequest, ClaimSuccess, ClaimView
from app.services.claim import claim_booking

router = APIRouter(prefix="/api/claim", tags=["claim"])

# Map claim outcomes to HTTP responses.
_ERROR_MAP = {
    "not_found": (status.HTTP_404_NOT_FOUND, "This claim link is not valid."),
    "expired": (status.HTTP_410_GONE, "This job has expired."),
    "already_claimed": (status.HTTP_409_CONFLICT, "This job has already been claimed."),
    "bad_credentials": (
        status.HTTP_403_FORBIDDEN,
        "Incorrect phone or PIN.",
    ),
    "not_verified": (
        status.HTTP_403_FORBIDDEN,
        "Your driver account is not verified yet.",
    ),
    "membership_inactive": (
        status.HTTP_402_PAYMENT_REQUIRED,
        "Your membership is not active. Please renew to claim jobs.",
    ),
    "insufficient_credits": (
        status.HTTP_402_PAYMENT_REQUIRED,
        "You have no job credits left. Please top up to claim.",
    ),
}


@router.get("/{token}", response_model=ClaimView)
def view_claim(token: str, db: Session = Depends(get_db)):
    link = db.query(ClaimLink).filter_by(token=token).one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This claim link is not valid.")

    booking = db.get(Booking, link.booking_id)
    area = db.get(Area, booking.area_id) if booking and booking.area_id else None
    now = datetime.now(timezone.utc)
    claimable = (
        booking is not None
        and booking.status == BookingStatus.posted
        and link.used_at is None
        and link.expires_at > now
    )
    if claimable:
        label = "Available to claim"
    elif link.used_at is not None or (booking and booking.status != BookingStatus.posted):
        label = "Already claimed"
    else:
        label = "Expired"

    return ClaimView(
        booking_id=booking.id,
        ride_type=booking.ride_type,
        area_name=area.name if area else None,
        pickup_zone=area.name if area else None,
        destination_text=booking.destination_text,
        claimable=claimable,
        status_label=label,
    )


@router.post("/{token}", response_model=ClaimSuccess)
def submit_claim(token: str, payload: ClaimRequest, db: Session = Depends(get_db)):
    outcome = claim_booking(
        db, token=token, driver_phone=payload.driver_phone, driver_pin=payload.driver_pin
    )

    if outcome.status != "claimed":
        code, detail = _ERROR_MAP[outcome.status]
        raise HTTPException(code, detail)

    return ClaimSuccess(
        booking_id=outcome.booking_id,
        rider_name=outcome.rider_name,
        rider_phone=outcome.rider_phone,
        pickup_address_text=outcome.pickup_address_text,
        destination_text=outcome.destination_text,
        message="Job claimed. Contact the rider now to arrange pickup.",
    )
