"""Credit operations. Every balance change writes a credit_ledger row (source of
truth) and updates drivers.credit_balance (denormalized cache) in the same
transaction, so the two never drift."""

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import CreditLedger, CreditTopupRequest, Driver
from app.models.enums import CreditTxnType, TopupStatus


def _bump_balance(db: Session, driver_id: int, delta: int) -> None:
    db.execute(
        update(Driver)
        .where(Driver.id == driver_id)
        .values(credit_balance=Driver.credit_balance + delta)
    )


def _claim_pending(db: Session, req_id: int, new_status: TopupStatus, admin_id: int) -> bool:
    """Atomically flip a top-up request pending -> new_status. The row lock
    serialises concurrent reviews so only one wins (guards against a
    double-approval crediting twice). Returns True if this call won."""
    result = db.execute(
        update(CreditTopupRequest)
        .where(
            CreditTopupRequest.id == req_id,
            CreditTopupRequest.status == TopupStatus.pending,
        )
        .values(
            status=new_status,
            reviewed_by_admin_id=admin_id,
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    return result.rowcount == 1


def approve_topup(
    db: Session, req: CreditTopupRequest, admin_id: int
) -> CreditLedger:
    if not _claim_pending(db, req.id, TopupStatus.approved, admin_id):
        raise ValueError("Top-up request is not pending.")
    ledger = CreditLedger(
        driver_id=req.driver_id,
        transaction_type=CreditTxnType.purchase,
        amount_credits=req.amount_credits,
        amount_gmd=req.amount_gmd,
        reference_number=req.reference_number,
        payment_method=req.payment_method,
        approved_by_admin_id=admin_id,
        topup_request_id=req.id,
    )
    db.add(ledger)
    _bump_balance(db, req.driver_id, req.amount_credits)
    return ledger


def reject_topup(db: Session, req: CreditTopupRequest, admin_id: int) -> None:
    if not _claim_pending(db, req.id, TopupStatus.rejected, admin_id):
        raise ValueError("Top-up request is not pending.")


def adjust(
    db: Session,
    driver_id: int,
    amount_credits: int,
    txn_type: CreditTxnType,
    admin_id: int,
    reference: str | None = None,
    booking_id: int | None = None,
) -> CreditLedger:
    """Admin refund/bonus: positive credits added to the driver's balance."""
    ledger = CreditLedger(
        driver_id=driver_id,
        transaction_type=txn_type,
        amount_credits=amount_credits,
        reference_number=reference,
        approved_by_admin_id=admin_id,
        booking_id=booking_id,
    )
    db.add(ledger)
    _bump_balance(db, driver_id, amount_credits)
    return ledger
