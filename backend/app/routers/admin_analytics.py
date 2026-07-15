"""Admin analytics: booking trend, ARPD, repurchase rate, area heatmap."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import Area, Booking, CreditLedger, Driver
from app.models.enums import CreditTxnType, VerificationStatus
from app.schemas.admin_pages import ArpdOut, AreaHeatPoint, RepurchaseOut, TrendPoint

router = APIRouter(
    prefix="/api/admin/analytics", tags=["admin-analytics"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/bookings-trend", response_model=list[TrendPoint])
def bookings_trend(db: Session = Depends(get_db), days: int = Query(default=30, le=365)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date(Booking.created_at)
    rows = (
        db.query(day.label("day"), func.count(Booking.id).label("count"))
        .filter(Booking.created_at >= since)
        .group_by(day)
        .order_by(day)
        .all()
    )
    return [TrendPoint(day=r.day, count=r.count) for r in rows]


@router.get("/arpd", response_model=ArpdOut)
def arpd(db: Session = Depends(get_db)):
    revenue = db.query(func.coalesce(func.sum(CreditLedger.amount_gmd), 0)).filter(
        CreditLedger.transaction_type == CreditTxnType.purchase).scalar()
    active = db.query(func.count(Driver.id)).filter(
        Driver.verification_status == VerificationStatus.verified).scalar()
    revenue = Decimal(revenue)
    per = (revenue / active) if active else Decimal("0")
    return ArpdOut(revenue_gmd=revenue, active_drivers=active,
                   arpd_gmd=per.quantize(Decimal("0.01")))


@router.get("/repurchase-rate", response_model=RepurchaseOut)
def repurchase_rate(db: Session = Depends(get_db)):
    # count purchases per driver
    per_driver = (
        db.query(CreditLedger.driver_id, func.count(CreditLedger.id).label("n"))
        .filter(CreditLedger.transaction_type == CreditTxnType.purchase)
        .group_by(CreditLedger.driver_id)
        .subquery()
    )
    purchased = db.query(func.count()).select_from(per_driver).scalar()
    repurchased = db.query(func.count()).select_from(per_driver).filter(
        per_driver.c.n >= 2).scalar()
    rate = (repurchased / purchased) if purchased else 0.0
    return RepurchaseOut(drivers_purchased=purchased, drivers_repurchased=repurchased,
                         repurchase_rate=round(rate, 3))


@router.get("/area-heatmap", response_model=list[AreaHeatPoint])
def area_heatmap(db: Session = Depends(get_db)):
    rows = (
        db.query(Booking.area_id, Area.name, func.count(Booking.id).label("n"))
        .outerjoin(Area, Booking.area_id == Area.id)
        .group_by(Booking.area_id, Area.name)
        .order_by(func.count(Booking.id).desc())
        .all()
    )
    return [AreaHeatPoint(area_id=r.area_id, area_name=r.name, bookings=r.n) for r in rows]
