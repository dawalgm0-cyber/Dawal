"""Daily maintenance jobs, run by the scheduler or triggered manually by an
admin. Each job is an existing, independently-tested service; this orchestrator
runs them together and writes a system audit entry per job."""

from sqlalchemy.orm import Session

from app.services import audit, booking_ops, membership, retention


def run_daily_jobs(db: Session) -> dict[str, int]:
    """Run all maintenance jobs and audit-log each. Caller commits."""
    scrubbed = retention.run_retention(db)  # PDPP rule 4.7
    flagged = booking_ops.flag_stale_unconfirmed(db)  # rule 4.4
    expired = membership.expire_lapsed(db)  # free_trial/active -> expired

    audit.log_action(db, None, "scheduled.retention", "system", None,
                     {"riders_scrubbed": scrubbed})
    audit.log_action(db, None, "scheduled.stale_unconfirmed", "system", None,
                     {"bookings_flagged": flagged})
    audit.log_action(db, None, "scheduled.membership_expiry", "system", None,
                     {"memberships_expired": expired})

    return {
        "riders_scrubbed": scrubbed,
        "bookings_flagged": flagged,
        "memberships_expired": expired,
    }
