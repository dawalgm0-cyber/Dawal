from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import BookingStatus, RideType


class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("riders.id"))
    # Nullable: an unmatched booking has no area yet (rule 4.1, status=unassigned).
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    pickup_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    pickup_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    pickup_address_text: Mapped[str | None]
    destination_text: Mapped[str | None]
    ride_type: Mapped[RideType]
    status: Mapped[BookingStatus] = mapped_column(
        default=BookingStatus.pending, index=True
    )
    assigned_driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    # rule 4.5: free priority rebook is a flag admin can see, not auto-reposting.
    priority: Mapped[bool] = mapped_column(default=False, server_default="false")
    rebook_of_booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    # Single-use token the rider uses to confirm pickup (rule 4.4); delivered to
    # the rider only (via SMS), never exposed on the public status endpoint.
    confirm_token: Mapped[str | None]
    # Issued to the rider's browser at booking creation. Authorizes the enriched
    # status view (driver contact) and in-app confirm/rate without needing the
    # SMS. Kept out of the public (token-less) status response.
    rider_access_token: Mapped[str | None] = mapped_column(index=True)
    posted_at: Mapped[datetime | None]
    claimed_at: Mapped[datetime | None]
    confirmed_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class ClaimLink(Base, TimestampMixin):
    __tablename__ = "claim_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    token: Mapped[str] = mapped_column(unique=True, index=True)  # crypto-random (4.2)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    used_by_driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))


class OtpVerification(Base, TimestampMixin):
    __tablename__ = "otp_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    code_hash: Mapped[str]  # hashed; plaintext OTP is never stored (rule 4.6)
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    verified_at: Mapped[datetime | None]
