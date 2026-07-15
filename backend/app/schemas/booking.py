from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BookingStatus, RideType


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    ride_type: RideType
    pickup_lat: Decimal | None = Field(default=None, ge=-90, le=90)
    pickup_lng: Decimal | None = Field(default=None, ge=-180, le=180)
    pickup_address_text: str | None = Field(default=None, max_length=500)
    destination_text: str | None = Field(default=None, max_length=500)
    # PDPP consent (rule 4.7): must be explicitly true before we accept a booking.
    consent: bool

    @field_validator("consent")
    @classmethod
    def consent_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent must be given before booking")
        return v

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return v.strip().replace(" ", "")


class BookingCreateResponse(BaseModel):
    id: int
    status: BookingStatus
    area_id: int | None
    area_name: str | None
    otp_required: bool = True
    message: str
    # Held by the rider's browser to authorize status enrichment + confirm/rate.
    rider_token: str


class OtpVerifyRequest(BaseModel):
    code: str = Field(min_length=3, max_length=12)


class OtpVerifyResponse(BaseModel):
    id: int
    status: BookingStatus
    message: str


class BookingStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: BookingStatus
    area_id: int | None
    assigned_driver_id: int | None
    # Populated only when a valid rider token is presented and the job is claimed.
    driver_name: str | None = None
    driver_phone: str | None = None


class ConfirmPickupRequest(BaseModel):
    confirm_token: str = Field(min_length=8, max_length=64)


class RateRequest(BaseModel):
    confirm_token: str = Field(min_length=8, max_length=64)
    rating_value: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class BookingActionResponse(BaseModel):
    id: int
    status: BookingStatus
    message: str


class AreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    center_lat: Decimal
    center_lng: Decimal
    radius_meters: int
