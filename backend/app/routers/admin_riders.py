"""Admin: riders directory, blacklist, and PDPP subject-access export / erasure."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import (
    AdminUser,
    BlacklistEntry,
    Booking,
    ConsentLog,
    Rating,
    Rider,
)
from app.models.enums import BlacklistEntityType
from app.schemas.admin_pages import BlacklistRequest, RiderDetail, RiderOut
from app.services import audit, retention

router = APIRouter(
    prefix="/api/admin/riders", tags=["admin-riders"],
    dependencies=[Depends(get_current_admin)],
)


def _get_rider(db: Session, rider_id: int) -> Rider:
    rider = db.get(Rider, rider_id)
    if rider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found.")
    return rider


@router.get("", response_model=list[RiderOut])
def list_riders(
    db: Session = Depends(get_db),
    blacklisted: bool | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    q = db.query(Rider)
    if blacklisted is not None:
        q = q.filter(Rider.blacklisted == blacklisted)
    return q.order_by(Rider.created_at.desc()).limit(limit).all()


@router.get("/{rider_id}", response_model=RiderDetail)
def get_rider(rider_id: int, db: Session = Depends(get_db)):
    rider = _get_rider(db, rider_id)
    count = db.query(func.count(Booking.id)).filter(Booking.rider_id == rider_id).scalar()
    detail = RiderDetail.model_validate(rider)
    detail.booking_count = count
    return detail


@router.post("/{rider_id}/blacklist", response_model=RiderOut)
def blacklist_rider(
    rider_id: int,
    payload: BlacklistRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    rider = _get_rider(db, rider_id)
    rider.blacklisted = True
    rider.blacklist_reason = payload.reason
    db.add(BlacklistEntry(entity_type=BlacklistEntityType.rider, entity_ref=str(rider_id),
                          reason=payload.reason, created_by_admin_id=admin.id))
    audit.log_action(db, admin.id, "rider.blacklist", "rider", rider_id,
                     {"reason": payload.reason})
    db.commit()
    return rider


@router.get("/{rider_id}/data-export")
def data_export(rider_id: int, db: Session = Depends(get_db),
                admin: AdminUser = Depends(get_current_admin)):
    """PDPP subject-access: everything held about a rider."""
    rider = _get_rider(db, rider_id)
    bookings = db.query(Booking).filter(Booking.rider_id == rider_id).all()
    consents = db.query(ConsentLog).filter(ConsentLog.rider_id == rider_id).all()
    ratings = db.query(Rating).filter(Rating.rider_id == rider_id).all()
    audit.log_action(db, admin.id, "rider.data_export", "rider", rider_id)
    db.commit()
    return {
        "rider": RiderOut.model_validate(rider).model_dump(mode="json"),
        "bookings": [
            {"id": b.id, "status": b.status.value, "ride_type": b.ride_type.value,
             "pickup_address_text": b.pickup_address_text,
             "destination_text": b.destination_text,
             "created_at": b.created_at.isoformat()} for b in bookings
        ],
        "consent_logs": [
            {"id": c.id, "booking_id": c.booking_id, "consent_type": c.consent_type,
             "consented_at": c.consented_at.isoformat(), "ip_address": c.ip_address}
            for c in consents
        ],
        "ratings": [
            {"id": r.id, "booking_id": r.booking_id, "rating_value": r.rating_value,
             "comment": r.comment} for r in ratings
        ],
    }


@router.delete("/{rider_id}/data")
def erase_data(rider_id: int, db: Session = Depends(get_db),
               admin: AdminUser = Depends(get_current_admin)):
    """PDPP erasure request. Refused while a dispute on the rider is open."""
    rider = _get_rider(db, rider_id)
    if retention._has_open_dispute(db, rider_id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Cannot erase: an open dispute references this rider.")
    retention.scrub_rider(db, rider, reason="pdpp_erasure_request")
    audit.log_action(db, admin.id, "rider.data_erase", "rider", rider_id)
    db.commit()
    return {"status": "erased", "rider_id": rider_id}
