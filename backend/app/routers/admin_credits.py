"""Admin: credit top-up approval queue, refunds, and promo/bonus credits."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, CreditTopupRequest, Driver, MembershipRequest
from app.models.enums import CreditTxnType, MembershipStatus, TopupStatus
from app.schemas.admin import (
    CreditAdjustRequest,
    MembershipRequestAdminOut,
    TopupOut,
)
from app.services import audit, credit, membership

router = APIRouter(
    prefix="/api/admin", tags=["admin-credits"], dependencies=[Depends(get_current_admin)]
)


def _get_topup(db: Session, topup_id: int) -> CreditTopupRequest:
    req = db.get(CreditTopupRequest, topup_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Top-up request not found.")
    return req


@router.get("/credit-topups", response_model=list[TopupOut])
def list_topups(
    db: Session = Depends(get_db),
    topup_status: TopupStatus = Query(default=TopupStatus.pending),
):
    return (
        db.query(CreditTopupRequest)
        .filter(CreditTopupRequest.status == topup_status)
        .order_by(CreditTopupRequest.created_at.asc())
        .all()
    )


@router.post("/credit-topups/{topup_id}/approve", response_model=TopupOut)
def approve_topup(
    topup_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    req = _get_topup(db, topup_id)
    try:
        credit.approve_topup(db, req, admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit.log_action(db, admin.id, "topup.approve", "credit_topup_request", topup_id,
                     {"driver_id": req.driver_id, "credits": req.amount_credits})
    db.commit()
    db.refresh(req)  # reflect the atomic status flip in the response
    return req


@router.post("/credit-topups/{topup_id}/reject", response_model=TopupOut)
def reject_topup(
    topup_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    req = _get_topup(db, topup_id)
    try:
        credit.reject_topup(db, req, admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit.log_action(db, admin.id, "topup.reject", "credit_topup_request", topup_id)
    db.commit()
    db.refresh(req)
    return req


def _require_driver(db: Session, driver_id: int) -> Driver:
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found.")
    return driver


@router.post("/credits/{driver_id}/refund")
def refund_credits(
    driver_id: int,
    payload: CreditAdjustRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _require_driver(db, driver_id)
    credit.adjust(db, driver_id, payload.amount_credits, CreditTxnType.refund,
                  admin.id, reference=payload.reason)
    audit.log_action(db, admin.id, "credit.refund", "driver", driver_id,
                     {"credits": payload.amount_credits, "reason": payload.reason})
    db.commit()
    return {"status": "ok", "driver_id": driver_id}


@router.post("/credits/{driver_id}/bonus")
def bonus_credits(
    driver_id: int,
    payload: CreditAdjustRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _require_driver(db, driver_id)
    credit.adjust(db, driver_id, payload.amount_credits, CreditTxnType.bonus,
                  admin.id, reference=payload.reason)
    audit.log_action(db, admin.id, "credit.bonus", "driver", driver_id,
                     {"credits": payload.amount_credits, "reason": payload.reason})
    db.commit()
    return {"status": "ok", "driver_id": driver_id}


# --- membership payment requests -----------------------------------------

def _get_membership_request(db: Session, req_id: int) -> MembershipRequest:
    req = db.get(MembershipRequest, req_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership request not found.")
    return req


def _claim_membership_pending(db: Session, req_id: int, new_status: TopupStatus,
                             admin_id: int) -> bool:
    """Atomic pending -> new_status flip; only one concurrent review wins."""
    result = db.execute(
        update(MembershipRequest)
        .where(MembershipRequest.id == req_id,
               MembershipRequest.status == TopupStatus.pending)
        .values(status=new_status, reviewed_by_admin_id=admin_id,
                reviewed_at=datetime.now(timezone.utc))
    )
    return result.rowcount == 1


@router.get("/membership-requests", response_model=list[MembershipRequestAdminOut])
def list_membership_requests(
    db: Session = Depends(get_db),
    request_status: TopupStatus = Query(default=TopupStatus.pending),
):
    return (
        db.query(MembershipRequest)
        .filter(MembershipRequest.status == request_status)
        .order_by(MembershipRequest.created_at.asc())
        .all()
    )


@router.post("/membership-requests/{req_id}/approve",
             response_model=MembershipRequestAdminOut)
def approve_membership_request(
    req_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    req = _get_membership_request(db, req_id)
    # Atomically claim the request so a concurrent double-approval can't activate
    # (and pay for) two memberships.
    if not _claim_membership_pending(db, req_id, TopupStatus.approved, admin.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Request is not pending.")
    membership.activate(db, req.driver_id, req.months, req.amount_gmd,
                        MembershipStatus.active, req.reference_number)
    audit.log_action(db, admin.id, "membership.approve", "membership_request", req_id,
                     {"driver_id": req.driver_id, "months": req.months})
    db.commit()
    db.refresh(req)
    return req


@router.post("/membership-requests/{req_id}/reject",
             response_model=MembershipRequestAdminOut)
def reject_membership_request(
    req_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    req = _get_membership_request(db, req_id)
    if not _claim_membership_pending(db, req_id, TopupStatus.rejected, admin.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Request is not pending.")
    audit.log_action(db, admin.id, "membership.reject", "membership_request", req_id)
    db.commit()
    db.refresh(req)
    return req
