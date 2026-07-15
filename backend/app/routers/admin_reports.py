"""Admin read-only reporting: dashboard summary + credit ledger views. Banjul is
UTC+0 year-round, so calendar-day boundaries use UTC directly."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import Booking, CreditLedger, CreditTopupRequest, Dispute, Driver
from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    DisputeStatus,
    TopupStatus,
    VerificationStatus,
)
from app.schemas.admin import (
    DashboardAlerts,
    DashboardSummary,
    LedgerOut,
)

router = APIRouter(
    prefix="/api/admin", tags=["admin-reports"], dependencies=[Depends(get_current_admin)]
)


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    bookings_today = (
        db.query(func.count(Booking.id))
        .filter(Booking.created_at >= day_start)
        .scalar()
    )
    by_status = dict(
        db.query(Booking.status, func.count(Booking.id))
        .filter(Booking.created_at >= day_start)
        .group_by(Booking.status)
        .all()
    )

    def _revenue(since):
        return db.query(
            func.coalesce(func.sum(CreditLedger.amount_gmd), 0)
        ).filter(
            CreditLedger.transaction_type == CreditTxnType.purchase,
            CreditLedger.created_at >= since,
        ).scalar()

    alerts = DashboardAlerts(
        pending_verifications=db.query(func.count(Driver.id)).filter(
            Driver.verification_status == VerificationStatus.pending).scalar(),
        open_disputes=db.query(func.count(Dispute.id)).filter(
            Dispute.status == DisputeStatus.open).scalar(),
        unassigned_bookings=db.query(func.count(Booking.id)).filter(
            Booking.status == BookingStatus.unassigned).scalar(),
        pending_review_bookings=db.query(func.count(Booking.id)).filter(
            Booking.status == BookingStatus.pending_review).scalar(),
        pending_topups=db.query(func.count(CreditTopupRequest.id)).filter(
            CreditTopupRequest.status == TopupStatus.pending).scalar(),
    )

    return DashboardSummary(
        bookings_today=bookings_today,
        bookings_by_status_today={k.value: v for k, v in by_status.items()},
        active_drivers=db.query(func.count(Driver.id)).filter(
            Driver.verification_status == VerificationStatus.verified).scalar(),
        revenue_today_gmd=_revenue(day_start),
        revenue_month_gmd=_revenue(month_start),
        alerts=alerts,
    )


@router.get("/credit-ledger", response_model=list[LedgerOut])
def credit_ledger(
    db: Session = Depends(get_db),
    driver_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    q = db.query(CreditLedger)
    if driver_id is not None:
        q = q.filter(CreditLedger.driver_id == driver_id)
    return q.order_by(CreditLedger.created_at.desc()).limit(limit).all()


@router.get("/drivers/{driver_id}/credit-history", response_model=list[LedgerOut])
def driver_credit_history(driver_id: int, db: Session = Depends(get_db)):
    return (
        db.query(CreditLedger)
        .filter(CreditLedger.driver_id == driver_id)
        .order_by(CreditLedger.created_at.desc())
        .all()
    )
