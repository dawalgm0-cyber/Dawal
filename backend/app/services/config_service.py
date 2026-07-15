"""Typed accessors for pricing_config. Every Section-8 value is read through
here so nothing is hardcoded in business logic (Section 8 requirement)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import PricingConfig


class ConfigError(KeyError):
    pass


def _raw(db: Session, key: str) -> str:
    row = db.query(PricingConfig).filter_by(key=key).one_or_none()
    if row is None:
        raise ConfigError(f"pricing_config key not found: {key}")
    return row.value


def get_int(db: Session, key: str) -> int:
    return int(_raw(db, key))


def get_decimal(db: Session, key: str) -> Decimal:
    return Decimal(_raw(db, key))


def get_bool(db: Session, key: str) -> bool:
    return _raw(db, key).strip().lower() in ("true", "1", "yes", "on")


def get_str(db: Session, key: str) -> str:
    return _raw(db, key)
