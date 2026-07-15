"""Admin compliance views: consent logs, retention queue + manual run, audit log."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, AuditLog, ConsentLog
from app.schemas.admin_pages import AuditLogOut, ConsentLogOut, RetentionQueueOut
from app.services import audit, retention, scheduled_jobs

router = APIRouter(
    prefix="/api/admin", tags=["admin-compliance"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/consent-logs", response_model=list[ConsentLogOut])
def consent_logs(db: Session = Depends(get_db), limit: int = Query(default=200, le=1000)):
    return (
        db.query(ConsentLog).order_by(ConsentLog.consented_at.desc()).limit(limit).all()
    )


@router.get("/retention-queue", response_model=RetentionQueueOut)
def retention_queue(db: Session = Depends(get_db)):
    ids = retention.eligible_rider_ids(db)
    return RetentionQueueOut(cutoff=retention.cutoff(db), eligible_rider_ids=ids,
                             count=len(ids))


@router.post("/retention/run-now")
def retention_run_now(db: Session = Depends(get_db),
                      admin: AdminUser = Depends(get_current_admin)):
    n = retention.run_retention(db)
    audit.log_action(db, admin.id, "retention.run_now", "system", None, {"scrubbed": n})
    db.commit()
    return {"status": "ok", "scrubbed": n}


@router.post("/scheduled-jobs/run-now")
def scheduled_jobs_run_now(db: Session = Depends(get_db),
                           admin: AdminUser = Depends(get_current_admin)):
    """Manually run the daily maintenance jobs (retention scrub, stale-unconfirmed
    sweep, membership expiry) — the same set the scheduler runs."""
    counts = scheduled_jobs.run_daily_jobs(db)
    audit.log_action(db, admin.id, "scheduled_jobs.run_now", "system", None, counts)
    db.commit()
    return {"status": "ok", **counts}


@router.get("/audit-log", response_model=list[AuditLogOut])
def audit_log(db: Session = Depends(get_db), limit: int = Query(default=200, le=1000)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
