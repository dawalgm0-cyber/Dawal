"""Schemas for the Checkpoint 6 admin pages: riders, analytics, compliance,
settings."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AdminRole, PricingValueType


# --- riders --------------------------------------------------------------

class RiderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    blacklisted: bool
    blacklist_reason: str | None
    fake_report_count: int
    consent_given_at: datetime | None
    created_at: datetime


class RiderDetail(RiderOut):
    booking_count: int = 0


class BlacklistRequest(BaseModel):
    reason: str | None = None


# --- analytics -----------------------------------------------------------

class TrendPoint(BaseModel):
    day: date
    count: int


class ArpdOut(BaseModel):
    revenue_gmd: Decimal
    active_drivers: int
    arpd_gmd: Decimal


class RepurchaseOut(BaseModel):
    drivers_purchased: int
    drivers_repurchased: int
    repurchase_rate: float


class AreaHeatPoint(BaseModel):
    area_id: int | None
    area_name: str | None
    bookings: int


# --- compliance ----------------------------------------------------------

class ConsentLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rider_id: int
    booking_id: int
    consent_type: str
    consented_at: datetime
    ip_address: str | None


class RetentionQueueOut(BaseModel):
    cutoff: datetime
    eligible_rider_ids: list[int]
    count: int


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int | None
    action: str
    target_type: str | None
    target_id: str | None
    details_json: dict | None
    created_at: datetime


# --- settings ------------------------------------------------------------

class PricingConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    value_type: PricingValueType
    updated_at: datetime


class PricingConfigPatch(BaseModel):
    # key -> new value (values are strings, coerced by value_type)
    updates: dict[str, str]


class MessageTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    template_text: str
    updated_at: datetime


class MessageTemplatePatch(BaseModel):
    template_text: str = Field(min_length=1)


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: AdminRole
    created_at: datetime


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str
    password: str = Field(min_length=6)
    role: AdminRole = AdminRole.dispatcher


class AdminUserPatch(BaseModel):
    name: str | None = None
    role: AdminRole | None = None
    password: str | None = Field(default=None, min_length=6)
