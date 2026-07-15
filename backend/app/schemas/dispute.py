from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DisputeRaisedBy, DisputeStatus, DisputeType


class DisputeCreate(BaseModel):
    type: DisputeType
    description: str | None = Field(default=None, max_length=1000)


class DisputeResolve(BaseModel):
    resolution: str = Field(min_length=1, max_length=1000)
    status: DisputeStatus = DisputeStatus.resolved


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    raised_by: DisputeRaisedBy
    type: DisputeType
    description: str | None
    status: DisputeStatus
    resolution: str | None
    resolved_by_admin_id: int | None
    created_at: datetime
    resolved_at: datetime | None
