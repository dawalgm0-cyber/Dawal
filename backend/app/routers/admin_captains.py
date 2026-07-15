"""Admin: areas CRUD, captain assignment, and captain payout report.

Rule 4.9: the payout summary is a CALCULATION for manual payout only — there is
deliberately no automated disbursement here.
"""

from datetime import datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, Area, Captain, CreditLedger, Driver
from app.models.enums import CreditTxnType
from app.schemas.captain import (
    AreaAdminOut,
    AreaCreate,
    AreaPatch,
    AssignCaptainRequest,
    CaptainOut,
    PayoutSummary,
)
from app.services import audit, config_service

router = APIRouter(
    prefix="/api/admin", tags=["admin-captains"],
    dependencies=[Depends(get_current_admin)],
)


def _area_out(db: Session, area: Area) -> AreaAdminOut:
    out = AreaAdminOut.model_validate(area)
    captain = db.query(Captain).filter_by(area_id=area.id).one_or_none()
    if captain is not None:
        driver = db.get(Driver, captain.driver_id)
        out.captain_id = captain.id
        out.captain_driver_id = captain.driver_id
        out.captain_driver_name = driver.name if driver else None
    return out


# --- areas ---------------------------------------------------------------

@router.get("/areas", response_model=list[AreaAdminOut])
def list_areas(db: Session = Depends(get_db)):
    return [_area_out(db, a) for a in db.query(Area).order_by(Area.name).all()]


@router.post("/areas", response_model=AreaAdminOut, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: Session = Depends(get_db),
                admin: AdminUser = Depends(get_current_admin)):
    area = Area(name=payload.name, center_lat=payload.center_lat,
                center_lng=payload.center_lng, radius_meters=payload.radius_meters)
    db.add(area)
    db.flush()
    audit.log_action(db, admin.id, "area.create", "area", area.id)
    db.commit()
    return _area_out(db, area)


@router.patch("/areas/{area_id}", response_model=AreaAdminOut)
def update_area(area_id: int, payload: AreaPatch, db: Session = Depends(get_db),
                admin: AdminUser = Depends(get_current_admin)):
    area = db.get(Area, area_id)
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Area not found.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(area, field, value)
    audit.log_action(db, admin.id, "area.update", "area", area_id)
    db.commit()
    return _area_out(db, area)


@router.post("/areas/{area_id}/assign-captain", response_model=AreaAdminOut)
def assign_captain(area_id: int, payload: AssignCaptainRequest,
                   db: Session = Depends(get_db),
                   admin: AdminUser = Depends(get_current_admin)):
    area = db.get(Area, area_id)
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Area not found.")
    driver = db.get(Driver, payload.driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found.")

    pct = payload.revenue_share_pct
    if pct is None:
        pct = config_service.get_decimal(db, "captain_revenue_share_pct")

    # One captain per area (unique area_id): update in place or create.
    captain = db.query(Captain).filter_by(area_id=area_id).one_or_none()
    if captain is None:
        captain = Captain(driver_id=driver.id, area_id=area_id, revenue_share_pct=pct)
        db.add(captain)
    else:
        captain.driver_id = driver.id
        captain.revenue_share_pct = pct
    audit.log_action(db, admin.id, "area.assign_captain", "area", area_id,
                     {"driver_id": driver.id, "revenue_share_pct": str(pct)})
    db.commit()
    return _area_out(db, area)


# --- captains + payout ---------------------------------------------------

@router.get("/captains", response_model=list[CaptainOut])
def list_captains(db: Session = Depends(get_db)):
    out = []
    for c in db.query(Captain).all():
        driver = db.get(Driver, c.driver_id)
        area = db.get(Area, c.area_id)
        item = CaptainOut.model_validate(c)
        item.driver_name = driver.name if driver else None
        item.area_name = area.name if area else None
        out.append(item)
    return out


@router.get("/captains/{captain_id}/payout-summary", response_model=PayoutSummary)
def payout_summary(
    captain_id: int,
    db: Session = Depends(get_db),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    """Sum credit-purchase revenue for drivers in the captain's area over the
    period, times the captain's share. Report only — no disbursement (rule 4.9)."""
    captain = db.get(Captain, captain_id)
    if captain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Captain not found.")
    area = db.get(Area, captain.area_id)
    driver = db.get(Driver, captain.driver_id)

    # Drivers whose home area is the captain's area.
    driver_ids = [d.id for d in db.query(Driver.id).filter(Driver.area_id == captain.area_id)]

    total = Decimal("0")
    if driver_ids:
        q = db.query(func.coalesce(func.sum(CreditLedger.amount_gmd), 0)).filter(
            CreditLedger.transaction_type == CreditTxnType.purchase,
            CreditLedger.driver_id.in_(driver_ids),
        )
        if date_from is not None:
            q = q.filter(CreditLedger.created_at >= date_from)
        if date_to is not None:
            # inclusive of the whole end day
            end = datetime.combine(date_to.date(), time.max, tzinfo=timezone.utc)
            q = q.filter(CreditLedger.created_at <= end)
        total = Decimal(q.scalar())

    payout = (total * captain.revenue_share_pct / Decimal("100")).quantize(Decimal("0.01"))

    return PayoutSummary(
        captain_id=captain.id,
        driver_id=captain.driver_id,
        driver_name=driver.name if driver else None,
        area_id=captain.area_id,
        area_name=area.name if area else None,
        period_from=date_from.date() if date_from else None,
        period_to=date_to.date() if date_to else None,
        driver_count=len(driver_ids),
        total_purchase_gmd=total,
        revenue_share_pct=captain.revenue_share_pct,
        payout_gmd=payout,
    )
