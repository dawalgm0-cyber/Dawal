"""Driver-facing endpoints: registration, PIN login, license upload, self
profile/credit/booking reads, and credit top-up requests. Self endpoints are
scoped to the authenticated driver's own record."""

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import create_driver_token, get_current_driver
from app.db import get_db
from app.models import (
    Booking,
    CreditLedger,
    CreditTopupRequest,
    Driver,
    Membership,
    MembershipRequest,
)
from app.models.enums import BookingStatus, TopupStatus, VerificationStatus
from app.schemas.driver import (
    CreditBalanceOut,
    CreditBlock,
    DriverBookingOut,
    DriverLogin,
    DriverProfile,
    DriverRegister,
    DriverTokenResponse,
    LedgerEntryOut,
    MembershipOut,
    MembershipRequestIn,
    MembershipRequestOut,
    PaymentOptions,
    StandingOut,
    TopupRequestIn,
    TopupRequestOut,
    TopupRequestStatusOut,
)
from app.security import hash_password, verify_password
from app.services import config_service

router = APIRouter(prefix="/api/drivers", tags=["drivers"])

UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", "/app/uploads")


def _self(driver_id: int, driver: Driver = Depends(get_current_driver)) -> Driver:
    """Ensure the authenticated driver is acting on their own record."""
    if driver.id != driver_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own account.")
    return driver


@router.post("/register", response_model=DriverTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: DriverRegister, db: Session = Depends(get_db)):
    phone = payload.normalized_phone()
    if db.query(Driver).filter_by(phone=phone).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A driver with this phone already exists.")
    driver = Driver(
        name=payload.name,
        phone=phone,
        pin_hash=hash_password(payload.pin),
        license_number=payload.license_number,
        vehicle_type=payload.vehicle_type,
        plate_number=payload.plate_number,
        verification_status=VerificationStatus.pending,
    )
    db.add(driver)
    db.commit()
    return DriverTokenResponse(
        access_token=create_driver_token(driver),
        driver_id=driver.id,
        verification_status=driver.verification_status,
    )


@router.post("/login", response_model=DriverTokenResponse)
def login(payload: DriverLogin, db: Session = Depends(get_db)):
    phone = payload.phone.strip().replace(" ", "")
    driver = db.query(Driver).filter_by(phone=phone).one_or_none()
    if driver is None or driver.pin_hash is None or not verify_password(
        payload.pin, driver.pin_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect phone or PIN.")
    return DriverTokenResponse(
        access_token=create_driver_token(driver),
        driver_id=driver.id,
        verification_status=driver.verification_status,
    )


@router.post("/{driver_id}/upload-license", response_model=DriverProfile)
def upload_license(
    driver_id: int,
    file: UploadFile = File(...),
    driver: Driver = Depends(_self),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1][:10]
    folder = os.path.join(UPLOAD_ROOT, str(driver_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"license{ext}")
    with open(path, "wb") as f:
        f.write(file.file.read())
    driver.license_doc_url = f"/uploads/{driver_id}/license{ext}"
    db.commit()
    return driver


@router.post("/{driver_id}/upload-proof")
def upload_proof(
    driver_id: int,
    file: UploadFile = File(...),
    driver: Driver = Depends(_self),
):
    """Upload a proof-of-payment photo; returns a URL to attach to a top-up or
    membership request as proof_url."""
    ext = os.path.splitext(file.filename or "")[1][:10]
    folder = os.path.join(UPLOAD_ROOT, str(driver_id))
    os.makedirs(folder, exist_ok=True)
    import time
    name = f"proof-{int(time.time())}{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(file.file.read())
    return {"proof_url": f"/uploads/{driver_id}/{name}"}


@router.get("/{driver_id}/profile", response_model=DriverProfile)
def profile(driver_id: int, driver: Driver = Depends(_self)):
    return driver


@router.get("/{driver_id}/credit-balance", response_model=CreditBalanceOut)
def credit_balance(driver_id: int, driver: Driver = Depends(_self)):
    return CreditBalanceOut(driver_id=driver.id, credit_balance=driver.credit_balance)


@router.get("/{driver_id}/credit-history", response_model=list[LedgerEntryOut])
def credit_history(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    return (
        db.query(CreditLedger)
        .filter_by(driver_id=driver_id)
        .order_by(desc(CreditLedger.created_at))
        .all()
    )


@router.post("/{driver_id}/credit-topup-request", response_model=TopupRequestOut,
             status_code=status.HTTP_201_CREATED)
def credit_topup_request(
    driver_id: int,
    payload: TopupRequestIn,
    driver: Driver = Depends(_self),
    db: Session = Depends(get_db),
):
    req = CreditTopupRequest(
        driver_id=driver_id,
        amount_credits=payload.amount_credits,
        amount_gmd=payload.amount_gmd,
        payment_method=payload.payment_method,
        reference_number=payload.reference_number,
        proof_url=payload.proof_url,
        status=TopupStatus.pending,
    )
    db.add(req)
    db.commit()
    return req


@router.get("/{driver_id}/bookings", response_model=list[DriverBookingOut])
def driver_bookings(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    return (
        db.query(Booking)
        .filter_by(assigned_driver_id=driver_id)
        .order_by(desc(Booking.created_at))
        .all()
    )


@router.get("/{driver_id}/standing", response_model=StandingOut)
def standing(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    completed = (
        db.query(Booking)
        .filter_by(assigned_driver_id=driver_id, status=BookingStatus.completed)
        .count()
    )
    no_shows = (
        db.query(Booking)
        .filter_by(assigned_driver_id=driver_id, status=BookingStatus.no_show)
        .count()
    )
    return StandingOut(
        driver_id=driver.id,
        standing_tier=driver.standing_tier,
        completed_jobs=completed,
        no_shows=no_shows,
    )


@router.get("/{driver_id}/membership", response_model=MembershipOut)
def current_membership(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    m = (
        db.query(Membership)
        .filter_by(driver_id=driver_id)
        .order_by(desc(Membership.period_end))
        .first()
    )
    return MembershipOut(
        driver_id=driver_id,
        status=m.status.value if m else None,
        period_start=m.period_start if m else None,
        period_end=m.period_end if m else None,
    )


# Credit-block config keys and the number of credits each grants.
_BLOCKS = [(5, "credit_block_5_gmd"), (10, "credit_block_10_gmd"), (25, "credit_block_25_gmd")]
_PAY_KEYS = {"wave": "payment_wave_number", "afrimoney": "payment_afrimoney_number",
             "qmoney": "payment_qmoney_number"}


@router.get("/{driver_id}/payment-options", response_model=PaymentOptions)
def payment_options(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    blocks = [
        CreditBlock(key=key, credits=credits,
                    amount_gmd=config_service.get_decimal(db, key))
        for credits, key in _BLOCKS
    ]
    numbers = {m: config_service.get_str(db, k) for m, k in _PAY_KEYS.items()}
    return PaymentOptions(
        credit_blocks=blocks,
        single_credit_gmd=config_service.get_decimal(db, "credit_price_single_gmd"),
        membership_fee_gmd=config_service.get_decimal(db, "membership_fee_gmd"),
        payment_numbers=numbers,
    )


@router.get("/{driver_id}/topup-requests", response_model=list[TopupRequestStatusOut])
def my_topup_requests(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    return (
        db.query(CreditTopupRequest)
        .filter_by(driver_id=driver_id)
        .order_by(desc(CreditTopupRequest.created_at))
        .all()
    )


@router.post("/{driver_id}/membership-request", response_model=MembershipRequestOut,
             status_code=status.HTTP_201_CREATED)
def submit_membership_request(
    driver_id: int,
    payload: MembershipRequestIn,
    driver: Driver = Depends(_self),
    db: Session = Depends(get_db),
):
    fee = config_service.get_decimal(db, "membership_fee_gmd")
    req = MembershipRequest(
        driver_id=driver_id,
        months=payload.months,
        amount_gmd=fee * payload.months,
        payment_method=payload.payment_method,
        reference_number=payload.reference_number,
        proof_url=payload.proof_url,
        status=TopupStatus.pending,
    )
    db.add(req)
    db.commit()
    return req


@router.get("/{driver_id}/membership-requests", response_model=list[MembershipRequestOut])
def my_membership_requests(
    driver_id: int, driver: Driver = Depends(_self), db: Session = Depends(get_db)
):
    return (
        db.query(MembershipRequest)
        .filter_by(driver_id=driver_id)
        .order_by(desc(MembershipRequest.created_at))
        .all()
    )
