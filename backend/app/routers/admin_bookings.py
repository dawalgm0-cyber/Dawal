"""Admin booking actions: no-show, fake-flag, cancel, override-assign (rules
4.1, 4.5). All require a valid admin JWT."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, Area, Booking, ClaimLink, Driver, Rider
from app.models.enums import BookingStatus
from app.schemas.admin import (
    BookingDetail,
    BookingListItem,
    OverrideAssignRequest,
    RejectRequest,
)
from app.schemas.booking import BookingActionResponse
from app.services import audit, booking_ops

router = APIRouter(
    prefix="/api/admin/bookings",
    tags=["admin-bookings"],
    dependencies=[Depends(get_current_admin)],
)


def _get_booking(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    return booking


@router.get("", response_model=list[BookingListItem])
def list_bookings(
    db: Session = Depends(get_db),
    booking_status: BookingStatus | None = Query(default=None),
    area_id: int | None = Query(default=None),
    driver_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    q = db.query(Booking, Rider.name, Rider.phone).join(Rider, Booking.rider_id == Rider.id)
    if booking_status is not None:
        q = q.filter(Booking.status == booking_status)
    if area_id is not None:
        q = q.filter(Booking.area_id == area_id)
    if driver_id is not None:
        q = q.filter(Booking.assigned_driver_id == driver_id)
    if date_from is not None:
        q = q.filter(Booking.created_at >= date_from)
    if date_to is not None:
        q = q.filter(Booking.created_at <= date_to)
    rows = q.order_by(Booking.created_at.desc()).limit(limit).all()

    out = []
    for booking, rider_name, rider_phone in rows:
        item = BookingListItem.model_validate(booking)
        item.rider_name = rider_name
        item.rider_phone = rider_phone
        out.append(item)
    return out


@router.get("/{booking_id}", response_model=BookingDetail)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = _get_booking(db, booking_id)
    detail = BookingDetail.model_validate(booking)
    rider = db.get(Rider, booking.rider_id)
    if rider:
        detail.rider_name, detail.rider_phone = rider.name, rider.phone
    if booking.assigned_driver_id:
        driver = db.get(Driver, booking.assigned_driver_id)
        if driver:
            detail.driver_name, detail.driver_phone = driver.name, driver.phone
    link = db.query(ClaimLink).filter_by(booking_id=booking.id).one_or_none()
    if link:
        detail.claim_token, detail.claim_used_at = link.token, link.used_at
    return detail


@router.post("/{booking_id}/mark-no-show", response_model=BookingActionResponse)
def mark_no_show(
    booking_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    booking = _get_booking(db, booking_id)
    if booking.status not in (BookingStatus.claimed, BookingStatus.pending_review):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Only a claimed booking can be marked no-show.")
    rebook = booking_ops.mark_no_show(db, booking)
    audit.log_action(db, admin.id, "booking.mark_no_show", "booking", booking_id,
                     {"rebook_booking_id": rebook.id})
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message=f"Marked no-show. Priority rebook #{rebook.id} created.")


@router.post("/{booking_id}/flag-fake", response_model=BookingActionResponse)
def flag_fake(
    booking_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    booking = _get_booking(db, booking_id)
    booking_ops.flag_fake(db, booking, admin.id)
    audit.log_action(db, admin.id, "booking.flag_fake", "booking", booking_id)
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message="Booking flagged fake; credit refunded to driver.")


@router.post("/{booking_id}/cancel", response_model=BookingActionResponse)
def cancel(
    booking_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    booking = _get_booking(db, booking_id)
    booking_ops.cancel(db, booking)
    audit.log_action(db, admin.id, "booking.cancel", "booking", booking_id,
                     {"reason": payload.reason})
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message="Booking cancelled.")


@router.post("/{booking_id}/override-assign", response_model=BookingActionResponse)
def override_assign(
    booking_id: int,
    payload: OverrideAssignRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    booking = _get_booking(db, booking_id)
    if db.get(Area, payload.area_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Area not found.")
    booking_ops.override_assign(db, booking, payload.area_id)
    audit.log_action(db, admin.id, "booking.override_assign", "booking", booking_id,
                     {"area_id": payload.area_id})
    db.commit()
    return BookingActionResponse(id=booking.id, status=booking.status,
                                 message=f"Assigned to area {payload.area_id}.")
