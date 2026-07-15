from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    PaymentMethod,
    RideType,
    StandingTier,
    VerificationStatus,
)


class DriverRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    license_number: str | None = Field(default=None, max_length=64)
    vehicle_type: str | None = Field(default=None, max_length=64)
    plate_number: str | None = Field(default=None, max_length=32)

    def normalized_phone(self) -> str:
        return self.phone.strip().replace(" ", "")


class DriverLogin(BaseModel):
    phone: str
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class DriverTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    driver_id: int
    verification_status: VerificationStatus


class DriverProfile(BaseModel):
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


class CreditBalanceOut(BaseModel):
    driver_id: int
    credit_balance: int


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_type: CreditTxnType
    amount_credits: int
    amount_gmd: Decimal | None
    reference_number: str | None
    booking_id: int | None
    created_at: datetime


class TopupRequestIn(BaseModel):
    amount_credits: int = Field(gt=0)
    amount_gmd: Decimal = Field(gt=0)
    payment_method: PaymentMethod
    reference_number: str | None = Field(default=None, max_length=120)
    proof_url: str | None = Field(default=None, max_length=500)


class TopupRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_credits: int
    amount_gmd: Decimal
    status: str
    created_at: datetime


class DriverBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ride_type: RideType
    status: BookingStatus
    area_id: int | None
    claimed_at: datetime | None
    created_at: datetime


class StandingOut(BaseModel):
    driver_id: int
    standing_tier: StandingTier
    completed_jobs: int
    no_shows: int


class MembershipOut(BaseModel):
    driver_id: int
    status: str | None            # active | free_trial | expired | None (never had one)
    period_start: datetime | None
    period_end: datetime | None


class CreditBlock(BaseModel):
    key: str
    credits: int
    amount_gmd: Decimal


class PaymentOptions(BaseModel):
    credit_blocks: list[CreditBlock]
    single_credit_gmd: Decimal
    membership_fee_gmd: Decimal
    payment_numbers: dict[str, str]   # method -> number to send to


class TopupRequestStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_credits: int
    amount_gmd: Decimal
    payment_method: PaymentMethod
    reference_number: str | None
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class MembershipRequestIn(BaseModel):
    months: int = Field(default=1, ge=1, le=12)
    payment_method: PaymentMethod
    reference_number: str | None = Field(default=None, max_length=120)
    proof_url: str | None = Field(default=None, max_length=500)


class MembershipRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    months: int
    amount_gmd: Decimal
    payment_method: PaymentMethod
    reference_number: str | None
    status: str
    created_at: datetime
    reviewed_at: datetime | None
