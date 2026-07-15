from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    MembershipStatus,
    PaymentMethod,
    RideType,
    StandingTier,
    TopupStatus,
    VerificationStatus,
)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


class DriverAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    license_number: str | None
    license_doc_url: str | None
    vehicle_type: str | None
    plate_number: str | None
    area_id: int | None
    verification_status: VerificationStatus
    standing_tier: StandingTier
    credit_balance: int
    verified_at: datetime | None
    created_at: datetime


class RejectRequest(BaseModel):
    reason: str | None = None


class OverrideAssignRequest(BaseModel):
    area_id: int


class StandingPatch(BaseModel):
    standing_tier: StandingTier


class TopupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    amount_credits: int
    amount_gmd: Decimal
    payment_method: PaymentMethod
    reference_number: str | None
    proof_url: str | None
    status: TopupStatus
    created_at: datetime


class CreditAdjustRequest(BaseModel):
    amount_credits: int = Field(gt=0)
    reason: str | None = None


class MembershipRequestAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    months: int
    amount_gmd: Decimal
    payment_method: PaymentMethod
    reference_number: str | None
    proof_url: str | None
    status: TopupStatus
    created_at: datetime


class MembershipActivateRequest(BaseModel):
    months: int = Field(default=1, ge=1, le=12)
    amount_paid: Decimal = Field(default=Decimal("0"))
    status: MembershipStatus = MembershipStatus.active
    payment_reference: str | None = None


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    status: MembershipStatus
    period_start: datetime
    period_end: datetime
    amount_paid: Decimal
    payment_reference: str | None


# --- dashboard + reports -------------------------------------------------

class DashboardAlerts(BaseModel):
    pending_verifications: int
    open_disputes: int
    unassigned_bookings: int
    pending_review_bookings: int
    pending_topups: int


class DashboardSummary(BaseModel):
    bookings_today: int
    bookings_by_status_today: dict[str, int]
    active_drivers: int
    revenue_today_gmd: Decimal
    revenue_month_gmd: Decimal
    alerts: DashboardAlerts


class BookingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rider_name: str | None = None
    rider_phone: str | None = None
    area_id: int | None
    ride_type: RideType
    status: BookingStatus
    priority: bool
    assigned_driver_id: int | None
    created_at: datetime
    posted_at: datetime | None
    claimed_at: datetime | None


class BookingDetail(BookingListItem):
    pickup_lat: Decimal | None
    pickup_lng: Decimal | None
    pickup_address_text: str | None
    destination_text: str | None
    completed_at: datetime | None
    rebook_of_booking_id: int | None
    driver_name: str | None = None
    driver_phone: str | None = None
    claim_token: str | None = None
    claim_used_at: datetime | None = None


class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    transaction_type: CreditTxnType
    amount_credits: int
    amount_gmd: Decimal | None
    reference_number: str | None
    payment_method: PaymentMethod | None
    booking_id: int | None
    topup_request_id: int | None
    created_at: datetime
