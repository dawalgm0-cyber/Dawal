from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    CreditTxnType,
    MembershipStatus,
    PaymentMethod,
    TopupStatus,
)


class CreditTopupRequest(Base, TimestampMixin):
    """Pending state for a driver's credit purchase, before it becomes a
    finalized credit_ledger entry (approved by admin, rule 4.3 / Section 5)."""

    __tablename__ = "credit_topup_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    amount_credits: Mapped[int]
    amount_gmd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[PaymentMethod]
    reference_number: Mapped[str | None]
    proof_url: Mapped[str | None]
    status: Mapped[TopupStatus] = mapped_column(
        default=TopupStatus.pending, index=True
    )
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )
    reviewed_at: Mapped[datetime | None]


class CreditLedger(Base, TimestampMixin):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    transaction_type: Mapped[CreditTxnType]
    # Signed: +purchase/bonus/refund, -burn.
    amount_credits: Mapped[int]
    amount_gmd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    reference_number: Mapped[str | None]
    payment_method: Mapped[PaymentMethod | None]
    approved_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )
    # Traceability: which approved top-up funded a purchase (compliance audit)...
    topup_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_topup_requests.id")
    )
    # ...and which booking a burn/refund is tied to (dispute logic, rule 4.5).
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))


class MembershipRequest(Base, TimestampMixin):
    """Driver-submitted membership payment awaiting admin approval — same manual
    proof-of-payment pattern as credit top-ups. On approval it activates a
    membership."""

    __tablename__ = "membership_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    months: Mapped[int]
    amount_gmd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[PaymentMethod]
    reference_number: Mapped[str | None]
    proof_url: Mapped[str | None]
    status: Mapped[TopupStatus] = mapped_column(default=TopupStatus.pending, index=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )
    reviewed_at: Mapped[datetime | None]


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    status: Mapped[MembershipStatus]
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_reference: Mapped[str | None]
