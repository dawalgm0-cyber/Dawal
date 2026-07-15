"""Admin: driver verification queue, standing overrides, and membership
activate/extend. All routes require a valid admin JWT (Section 10)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, Driver, Membership
from app.models.enums import StandingTier, VerificationStatus
from app.schemas.admin import (
    DriverAdminOut,
    MembershipActivateRequest,
    MembershipOut,
    RejectRequest,
    StandingPatch,
)
from app.services import audit, membership

router = APIRouter(
    prefix="/api/admin", tags=["admin-drivers"], dependencies=[Depends(get_current_admin)]
)


def _get_driver(db: Session, driver_id: int) -> Driver:
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found.")
    return driver


@router.get("/drivers", response_model=list[DriverAdminOut])
def list_drivers(
    db: Session = Depends(get_db),
    verification_status: VerificationStatus | None = Query(default=None),
    area_id: int | None = Query(default=None),
    standing_tier: StandingTier | None = Query(default=None),
):
    q = db.query(Driver)
    if verification_status is not None:
        q = q.filter(Driver.verification_status == verification_status)
    if area_id is not None:
        q = q.filter(Driver.area_id == area_id)
    if standing_tier is not None:
        q = q.filter(Driver.standing_tier == standing_tier)
    return q.order_by(Driver.created_at.desc()).all()


@router.get("/drivers/{driver_id}", response_model=DriverAdminOut)
def get_driver(driver_id: int, db: Session = Depends(get_db)):
    return _get_driver(db, driver_id)


@router.post("/drivers/{driver_id}/verify", response_model=DriverAdminOut)
def verify_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    driver = _get_driver(db, driver_id)
    driver.verification_status = VerificationStatus.verified
    driver.verified_at = datetime.now(timezone.utc)
    # First-month-free promo (rule: membership standing, credits still separate).
    membership.grant_free_trial_if_eligible(db, driver_id)
    audit.log_action(db, admin.id, "driver.verify", "driver", driver_id)
    db.commit()
    return driver


@router.post("/drivers/{driver_id}/reject", response_model=DriverAdminOut)
def reject_driver(
    driver_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    driver = _get_driver(db, driver_id)
    driver.verification_status = VerificationStatus.rejected
    audit.log_action(db, admin.id, "driver.reject", "driver", driver_id,
                     {"reason": payload.reason})
    db.commit()
    return driver


@router.post("/drivers/{driver_id}/suspend", response_model=DriverAdminOut)
def suspend_driver(
    driver_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    driver = _get_driver(db, driver_id)
    driver.verification_status = VerificationStatus.suspended
    audit.log_action(db, admin.id, "driver.suspend", "driver", driver_id,
                     {"reason": payload.reason})
    db.commit()
    return driver


@router.post("/drivers/{driver_id}/reinstate", response_model=DriverAdminOut)
def reinstate_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    driver = _get_driver(db, driver_id)
    driver.verification_status = VerificationStatus.verified
    audit.log_action(db, admin.id, "driver.reinstate", "driver", driver_id)
    db.commit()
    return driver


@router.patch("/drivers/{driver_id}/standing", response_model=DriverAdminOut)
def override_standing(
    driver_id: int,
    payload: StandingPatch,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    driver = _get_driver(db, driver_id)
    driver.standing_tier = payload.standing_tier
    audit.log_action(db, admin.id, "driver.standing_override", "driver", driver_id,
                     {"standing_tier": payload.standing_tier.value})
    db.commit()
    return driver


# --- memberships ---------------------------------------------------------

@router.get("/memberships", response_model=list[MembershipOut])
def list_memberships(db: Session = Depends(get_db), driver_id: int | None = None):
    q = db.query(Membership)
    if driver_id is not None:
        q = q.filter(Membership.driver_id == driver_id)
    return q.order_by(Membership.period_end.desc()).all()


@router.post("/memberships/{driver_id}/activate", response_model=MembershipOut)
def activate_membership(
    driver_id: int,
    payload: MembershipActivateRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _get_driver(db, driver_id)
    m = membership.activate(db, driver_id, payload.months, payload.amount_paid,
                            payload.status, payload.payment_reference)
    audit.log_action(db, admin.id, "membership.activate", "driver", driver_id,
                     {"months": payload.months})
    db.commit()
    return m


@router.post("/memberships/{driver_id}/extend", response_model=MembershipOut)
def extend_membership(
    driver_id: int,
    months: int = Query(default=1, ge=1, le=12),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _get_driver(db, driver_id)
    m = membership.extend(db, driver_id, months)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No membership to extend.")
    audit.log_action(db, admin.id, "membership.extend", "driver", driver_id,
                     {"months": months})
    db.commit()
    return m
