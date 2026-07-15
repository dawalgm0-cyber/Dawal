"""SQLAlchemy models for DAWAL. Importing this package registers every table
on Base.metadata (used by Alembic autogenerate and create_all)."""

from app.models.base import Base, TimestampMixin
from app.models.core import Area, Captain, Driver, Rider
from app.models.booking import Booking, ClaimLink, OtpVerification
from app.models.credit import (
    CreditLedger,
    CreditTopupRequest,
    Membership,
    MembershipRequest,
)
from app.models.trust import Dispute, Rating
from app.models.admin import (
    AdminUser,
    AuditLog,
    BlacklistEntry,
    ConsentLog,
    MessageTemplate,
    PricingConfig,
    RetentionLog,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "Area",
    "Captain",
    "Driver",
    "Rider",
    "Booking",
    "ClaimLink",
    "OtpVerification",
    "CreditLedger",
    "CreditTopupRequest",
    "Membership",
    "MembershipRequest",
    "Dispute",
    "Rating",
    "AdminUser",
    "AuditLog",
    "BlacklistEntry",
    "ConsentLog",
    "MessageTemplate",
    "PricingConfig",
    "RetentionLog",
]
