from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import StandingTier, VerificationStatus


class Rider(Base, TimestampMixin):
    __tablename__ = "riders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    phone: Mapped[str] = mapped_column(unique=True, index=True)
    consent_given_at: Mapped[datetime | None]
    blacklisted: Mapped[bool] = mapped_column(default=False, server_default="false")
    blacklist_reason: Mapped[str | None]
    fake_report_count: Mapped[int] = mapped_column(default=0, server_default="0")  # rule 4.5


class Driver(Base, TimestampMixin):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    phone: Mapped[str] = mapped_column(unique=True, index=True)
    license_number: Mapped[str | None]
    license_doc_url: Mapped[str | None]
    vehicle_type: Mapped[str | None]
    plate_number: Mapped[str | None]
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        default=VerificationStatus.pending
    )
    standing_tier: Mapped[StandingTier] = mapped_column(default=StandingTier.new)
    # Denormalized cache; the credit_ledger is the source of truth (rule 4.3).
    credit_balance: Mapped[int] = mapped_column(default=0, server_default="0")
    # Static 4-digit claim PIN (hashed). Required with phone to claim a job, so
    # a known phone number alone cannot burn a driver's credits.
    pin_hash: Mapped[str | None]
    verified_at: Mapped[datetime | None]


class Area(Base, TimestampMixin):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    center_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    center_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    radius_meters: Mapped[int]


class Captain(Base, TimestampMixin):
    __tablename__ = "captains"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    # Single source of truth for area->captain; unique => one captain per area.
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), unique=True)
    revenue_share_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("10.00")
    )
