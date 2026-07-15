"""Disputes: an assigned driver can raise a dispute on their booking (rule 4.5
"after driver dispute"); admins list, view, and resolve them."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_current_driver
from app.db import get_db
from app.models import AdminUser, Booking, Dispute, Driver
from app.models.enums import DisputeRaisedBy, DisputeStatus
from app.schemas.dispute import DisputeCreate, DisputeOut, DisputeResolve
from app.services import audit

driver_router = APIRouter(prefix="/api/bookings", tags=["disputes"])
admin_router = APIRouter(
    prefix="/api/admin/disputes",
    tags=["admin-disputes"],
    dependencies=[Depends(get_current_admin)],
)


@driver_router.post("/{booking_id}/dispute", response_model=DisputeOut,
                    status_code=status.HTTP_201_CREATED)
def raise_dispute(
    booking_id: int,
    payload: DisputeCreate,
    db: Session = Depends(get_db),
    driver: Driver = Depends(get_current_driver),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    if booking.assigned_driver_id != driver.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You can only dispute a booking you claimed.")
    dispute = Dispute(
        booking_id=booking_id,
        raised_by=DisputeRaisedBy.driver,
        type=payload.type,
        description=payload.description,
        status=DisputeStatus.open,
    )
    db.add(dispute)
    db.commit()
    return dispute


@admin_router.get("", response_model=list[DisputeOut])
def list_disputes(
    db: Session = Depends(get_db),
    dispute_status: DisputeStatus | None = Query(default=None),
):
    q = db.query(Dispute)
    if dispute_status is not None:
        q = q.filter(Dispute.status == dispute_status)
    return q.order_by(Dispute.created_at.desc()).all()


@admin_router.get("/{dispute_id}", response_model=DisputeOut)
def get_dispute(dispute_id: int, db: Session = Depends(get_db)):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found.")
    return dispute


@admin_router.post("/{dispute_id}/resolve", response_model=DisputeOut)
def resolve_dispute(
    dispute_id: int,
    payload: DisputeResolve,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found.")
    dispute.resolution = payload.resolution
    dispute.status = payload.status
    dispute.resolved_by_admin_id = admin.id
    dispute.resolved_at = datetime.now(timezone.utc)
    audit.log_action(db, admin.id, "dispute.resolve", "dispute", dispute_id,
                     {"status": payload.status.value})
    db.commit()
    return dispute
