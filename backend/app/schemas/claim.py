from pydantic import BaseModel, Field

from app.models.enums import RideType


class ClaimView(BaseModel):
    """Pre-claim job details shown to a driver who taps the link. Contains NO
    rider PII (Section 10)."""

    booking_id: int
    ride_type: RideType
    area_name: str | None
    pickup_zone: str | None
    destination_text: str | None
    claimable: bool
    status_label: str


class ClaimRequest(BaseModel):
    driver_phone: str = Field(min_length=5, max_length=32)
    # Static claim PIN set at registration; guards against phone-only impersonation.
    driver_pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class ClaimSuccess(BaseModel):
    """Returned only after a successful, credit-backed claim (rule 4.3)."""

    booking_id: int
    rider_name: str
    rider_phone: str
    pickup_address_text: str | None
    destination_text: str | None
    message: str
