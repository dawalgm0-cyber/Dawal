"""OTP generation and verification (rule 4.6). Codes are hashed (never stored
plaintext), expire after a TTL, and verification attempts are capped."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.models import OtpVerification
from app.security import hash_password, verify_password
from app.services.sms import get_sms_provider


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_code() -> str:
    """Zero-padded numeric code of configured length."""
    upper = 10**settings.OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(settings.OTP_LENGTH)


def create_and_send(db: Session, phone: str, booking_id: int) -> OtpVerification:
    code = generate_code()
    otp = OtpVerification(
        phone=phone,
        booking_id=booking_id,
        code_hash=hash_password(code),
        expires_at=_now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
        attempts=0,
    )
    db.add(otp)
    db.flush()  # assign id without committing (caller owns the transaction)
    get_sms_provider().send(
        phone,
        f"Your DAWAL verification code is {code}. "
        f"It expires in {settings.OTP_TTL_MINUTES} minutes.",
    )
    return otp


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""  # machine-readable: "", expired, too_many_attempts, no_code, bad_code


def verify(db: Session, booking_id: int, code: str) -> VerifyResult:
    otp = (
        db.query(OtpVerification)
        .filter(
            OtpVerification.booking_id == booking_id,
            OtpVerification.verified_at.is_(None),
        )
        .order_by(desc(OtpVerification.created_at))
        .first()
    )
    if otp is None:
        return VerifyResult(False, "no_code")
    if otp.expires_at <= _now():
        return VerifyResult(False, "expired")
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        return VerifyResult(False, "too_many_attempts")

    if not verify_password(code, otp.code_hash):
        otp.attempts += 1
        db.flush()
        return VerifyResult(False, "bad_code")

    otp.verified_at = _now()
    db.flush()
    return VerifyResult(True)
