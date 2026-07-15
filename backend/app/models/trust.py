from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import DisputeRaisedBy, DisputeStatus, DisputeType


class Rating(Base, TimestampMixin):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    rider_id: Mapped[int] = mapped_column(ForeignKey("riders.id"))
    # 1-5 scale; rider UI renders a simple thumbs up (5) / down (1).
    rating_value: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None]

    __table_args__ = (
        CheckConstraint("rating_value BETWEEN 1 AND 5", name="rating_range"),
    )


class Dispute(Base, TimestampMixin):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    raised_by: Mapped[DisputeRaisedBy]
    type: Mapped[DisputeType]
    description: Mapped[str | None]
    status: Mapped[DisputeStatus] = mapped_column(
        default=DisputeStatus.open, index=True
    )
    resolution: Mapped[str | None]
    resolved_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )
    resolved_at: Mapped[datetime | None]
