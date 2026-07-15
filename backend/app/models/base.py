from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraint convention -> stable, readable Alembic autogenerate diffs.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)

    # Every `Mapped[datetime]` column is timezone-aware (stored UTC). Guarantees
    # consistency for the time-window logic (no-show window, OTP expiry, PDPP
    # retention) across the whole schema — no naive/aware mixing.
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Adds a UTC-stored created_at set by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
