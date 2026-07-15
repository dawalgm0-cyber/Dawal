"""Append-only audit logging for admin actions (Section 10). Only ever inserts;
there is deliberately no update/delete helper anywhere."""

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details_json=details,
        )
    )
