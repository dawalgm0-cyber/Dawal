from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import AdminRole, BlacklistEntityType, PricingValueType


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    role: Mapped[AdminRole]


class ConsentLog(Base):
    __tablename__ = "consent_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("riders.id"))
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    consent_type: Mapped[str] = mapped_column(
        default="data_sharing", server_default="data_sharing"
    )
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip_address: Mapped[str | None]


class AuditLog(Base):
    """APPEND-ONLY. No update/delete code path exists for this table anywhere
    in the codebase (Section 10)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[str | None]
    details_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BlacklistEntry(Base, TimestampMixin):
    __tablename__ = "blacklist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[BlacklistEntityType]
    entity_ref: Mapped[str]  # phone string, or rider/driver id as text
    reason: Mapped[str | None]
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )


class PricingConfig(Base):
    """Runtime-adjustable config (Section 8). Values stored as text and coerced
    per value_type so nothing in Section 8 is hardcoded in business logic."""

    __tablename__ = "pricing_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    value: Mapped[str]
    value_type: Mapped[PricingValueType]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )


class RetentionLog(Base):
    """PDPP deletion audit trail (rule 4.7)."""

    __tablename__ = "retention_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reason: Mapped[str]


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    template_text: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id")
    )
