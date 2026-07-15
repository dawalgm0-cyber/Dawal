import enum


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    suspended = "suspended"


class StandingTier(str, enum.Enum):
    new = "new"
    standard = "standard"
    gold = "gold"


class RideType(str, enum.Enum):
    ride = "ride"
    delivery = "delivery"


class BookingStatus(str, enum.Enum):
    pending = "pending"
    posted = "posted"
    claimed = "claimed"
    confirmed = "confirmed"
    completed = "completed"
    no_show = "no_show"
    cancelled = "cancelled"
    fake_flagged = "fake_flagged"
    unassigned = "unassigned"        # rule 4.1: no area matched
    pending_review = "pending_review"  # rule 4.4: unconfirmed past window


class CreditTxnType(str, enum.Enum):
    purchase = "purchase"
    burn = "burn"
    refund = "refund"
    bonus = "bonus"


class PaymentMethod(str, enum.Enum):
    wave = "wave"
    afrimoney = "afrimoney"
    qmoney = "qmoney"
    cash = "cash"


class TopupStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MembershipStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    free_trial = "free_trial"


class DisputeRaisedBy(str, enum.Enum):
    rider = "rider"
    driver = "driver"
    admin = "admin"


class DisputeType(str, enum.Enum):
    no_show = "no_show"
    fraud = "fraud"
    safety = "safety"
    payment = "payment"


class DisputeStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    dispatcher = "dispatcher"
    captain_viewer = "captain_viewer"


class BlacklistEntityType(str, enum.Enum):
    rider = "rider"
    driver = "driver"
    phone = "phone"


class PricingValueType(str, enum.Enum):
    int = "int"
    decimal = "decimal"
    bool = "bool"
    string = "string"
