from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    center_lat: Decimal = Field(ge=-90, le=90)
    center_lng: Decimal = Field(ge=-180, le=180)
    radius_meters: int = Field(gt=0)


class AreaPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    center_lat: Decimal | None = Field(default=None, ge=-90, le=90)
    center_lng: Decimal | None = Field(default=None, ge=-180, le=180)
    radius_meters: int | None = Field(default=None, gt=0)


class AreaAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    center_lat: Decimal
    center_lng: Decimal
    radius_meters: int
    captain_id: int | None = None
    captain_driver_id: int | None = None
    captain_driver_name: str | None = None


class AssignCaptainRequest(BaseModel):
    driver_id: int
    # Defaults to captain_revenue_share_pct from pricing_config when omitted.
    revenue_share_pct: Decimal | None = Field(default=None, ge=0, le=100)


class CaptainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    driver_name: str | None = None
    area_id: int
    area_name: str | None = None
    revenue_share_pct: Decimal
    created_at: datetime


class PayoutSummary(BaseModel):
    captain_id: int
    driver_id: int
    driver_name: str | None
    area_id: int
    area_name: str | None
    period_from: date | None
    period_to: date | None
    driver_count: int
    total_purchase_gmd: Decimal
    revenue_share_pct: Decimal
    payout_gmd: Decimal
