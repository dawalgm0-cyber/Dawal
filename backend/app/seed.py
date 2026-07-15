"""Idempotent seeder for config-style data. Kept OUT of migrations so editing
values later never conflicts with a migration. Safe to re-run.

Usage:  python -m app.seed
"""

from app.config import settings
from app.db import SessionLocal
from app.models import AdminUser, MessageTemplate, PricingConfig
from app.models.enums import AdminRole, PricingValueType
from app.security import hash_password

# (key, value, value_type) — all defaults from Section 8. Nothing hardcoded in
# business logic; every one of these is editable via the admin panel later.
PRICING_DEFAULTS = [
    ("membership_fee_gmd", "200", PricingValueType.decimal),
    ("credit_price_single_gmd", "20", PricingValueType.decimal),
    ("credit_block_5_gmd", "100", PricingValueType.decimal),
    ("credit_block_10_gmd", "190", PricingValueType.decimal),
    ("credit_block_25_gmd", "450", PricingValueType.decimal),
    ("captain_revenue_share_pct", "10", PricingValueType.decimal),
    ("free_trial_first_month", "true", PricingValueType.bool),
    ("referral_bonus_credits", "5", PricingValueType.int),
    ("no_show_review_window_hours", "3", PricingValueType.int),
    ("fake_report_blacklist_threshold", "3", PricingValueType.int),
    ("pdpp_retention_days", "30", PricingValueType.int),
    ("booking_rate_limit_per_phone_per_day", "3", PricingValueType.int),
    # Standing-tier thresholds (rule 4.8) — configurable, never hardcoded.
    ("standing_standard_min_completed", "3", PricingValueType.int),
    ("standing_gold_min_completed", "20", PricingValueType.int),
    ("standing_gold_min_avg_rating", "4.5", PricingValueType.decimal),
    ("standing_gold_max_no_shows", "1", PricingValueType.int),
    # Mobile-money numbers drivers send payment to (admin-editable, no redeploy).
    ("payment_wave_number", "", PricingValueType.string),
    ("payment_afrimoney_number", "", PricingValueType.string),
    ("payment_qmoney_number", "", PricingValueType.string),
]

# Placeholder syntax = {curly}. Job post text carries NO rider PII (rule 4.2 /
# Section 10): area + type + a rough pickup zone only, never name/phone/address.
MESSAGE_TEMPLATES = {
    "job_post_text": (
        "\U0001F697 New DAWAL {ride_type} request in {area_name}.\n"
        "Pickup zone: {pickup_zone}.\n"
        "Tap to claim (costs 1 credit): {claim_url}\n"
        "First verified driver to claim gets the job."
    ),
    "consent_notice": (
        "By booking, you agree that if a driver accepts your request, DAWAL will "
        "share your name and phone number with that assigned driver so they can "
        "reach you. Your details are shared only with the assigned driver and are "
        "deleted after {retention_days} days. Do you agree?"
    ),
    "no_show_notice": (
        "We're sorry your driver did not arrive. You can rebook now with priority "
        "at no extra charge, and the issue has been reported to our team."
    ),
}


def seed_pricing_config(db) -> int:
    changed = 0
    for key, value, value_type in PRICING_DEFAULTS:
        row = db.query(PricingConfig).filter_by(key=key).one_or_none()
        if row is None:
            db.add(PricingConfig(key=key, value=value, value_type=value_type))
            changed += 1
    return changed


def seed_message_templates(db) -> int:
    changed = 0
    for key, text in MESSAGE_TEMPLATES.items():
        row = db.query(MessageTemplate).filter_by(key=key).one_or_none()
        if row is None:
            db.add(MessageTemplate(key=key, template_text=text))
            changed += 1
    return changed


def seed_admin(db) -> int:
    email = settings.ADMIN_DEFAULT_EMAIL
    if db.query(AdminUser).filter_by(email=email).one_or_none() is not None:
        return 0
    db.add(
        AdminUser(
            name="Default Admin",
            email=email,
            password_hash=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
            role=AdminRole.super_admin,
        )
    )
    return 1


def run() -> None:
    db = SessionLocal()
    try:
        p = seed_pricing_config(db)
        m = seed_message_templates(db)
        a = seed_admin(db)
        db.commit()
        print(f"Seed complete: +{p} pricing_config, +{m} templates, +{a} admin.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
