"""Admin auth + driver verification queue + membership + credit top-up approval."""

from decimal import Decimal

from app.models import CreditLedger, CreditTopupRequest, Driver, Membership
from app.models.enums import (
    CreditTxnType,
    MembershipStatus,
    TopupStatus,
    VerificationStatus,
)
from app.security import hash_password


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _driver(db, phone="+2209001111", status=VerificationStatus.pending):
    d = Driver(name="Sana", phone=phone, verification_status=status,
               pin_hash=hash_password("1234"))
    db.add(d)
    db.flush()
    return d


# --- auth guards ---------------------------------------------------------

def test_admin_endpoint_requires_token(client, db_session):
    assert client.get("/api/admin/drivers").status_code == 401


def test_bad_login_401(client, db_session, admin_token):
    r = client.post("/api/admin/login",
                    json={"email": "admin@test.dawal", "password": "wrong"})
    assert r.status_code == 401


def test_driver_token_cannot_access_admin(client, db_session):
    reg = client.post("/api/drivers/register", json={
        "name": "D", "phone": "+2209002222", "pin": "1234"}).json()
    r = client.get("/api/admin/drivers", headers=H(reg["access_token"]))
    assert r.status_code == 401  # typ mismatch


# --- verification queue + free trial ------------------------------------

def test_verify_grants_free_trial_membership(client, db_session, admin_token):
    d = _driver(db_session)
    r = client.post(f"/api/admin/drivers/{d.id}/verify", headers=H(admin_token))
    assert r.status_code == 200
    assert r.json()["verification_status"] == "verified"
    db_session.expire_all()
    assert db_session.get(Driver, d.id).verified_at is not None
    m = db_session.query(Membership).filter_by(driver_id=d.id).one()
    assert m.status == MembershipStatus.free_trial
    assert m.amount_paid == Decimal("0")


def test_reject_suspend_reinstate(client, db_session, admin_token):
    d = _driver(db_session)
    client.post(f"/api/admin/drivers/{d.id}/reject", headers=H(admin_token), json={})
    db_session.expire_all()
    assert db_session.get(Driver, d.id).verification_status == VerificationStatus.rejected
    client.post(f"/api/admin/drivers/{d.id}/suspend", headers=H(admin_token), json={})
    db_session.expire_all()
    assert db_session.get(Driver, d.id).verification_status == VerificationStatus.suspended
    client.post(f"/api/admin/drivers/{d.id}/reinstate", headers=H(admin_token))
    db_session.expire_all()
    assert db_session.get(Driver, d.id).verification_status == VerificationStatus.verified


def test_list_drivers_filter(client, db_session, admin_token):
    _driver(db_session, phone="+220900A", status=VerificationStatus.pending)
    _driver(db_session, phone="+220900B", status=VerificationStatus.verified)
    r = client.get("/api/admin/drivers?verification_status=pending", headers=H(admin_token))
    assert r.status_code == 200
    assert all(d["verification_status"] == "pending" for d in r.json())


# --- credit top-up approval ---------------------------------------------

def _pending_topup(db, driver_id, credits=10):
    req = CreditTopupRequest(driver_id=driver_id, amount_credits=credits,
                             amount_gmd=Decimal("190.00"), payment_method="wave",
                             reference_number="R1", status=TopupStatus.pending)
    db.add(req)
    db.flush()
    return req


def test_approve_topup_increments_balance_and_writes_ledger(client, db_session, admin_token):
    d = _driver(db_session, status=VerificationStatus.verified)
    req = _pending_topup(db_session, d.id, credits=10)
    r = client.post(f"/api/admin/credit-topups/{req.id}/approve", headers=H(admin_token))
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Driver, d.id).credit_balance == 10
    ledger = db_session.query(CreditLedger).filter_by(
        driver_id=d.id, transaction_type=CreditTxnType.purchase).one()
    assert ledger.amount_credits == 10 and ledger.topup_request_id == req.id
    assert db_session.get(CreditTopupRequest, req.id).status == TopupStatus.approved


def test_double_approve_is_conflict(client, db_session, admin_token):
    d = _driver(db_session, status=VerificationStatus.verified)
    req = _pending_topup(db_session, d.id)
    client.post(f"/api/admin/credit-topups/{req.id}/approve", headers=H(admin_token))
    again = client.post(f"/api/admin/credit-topups/{req.id}/approve", headers=H(admin_token))
    assert again.status_code == 409


def test_reject_topup(client, db_session, admin_token):
    d = _driver(db_session, status=VerificationStatus.verified)
    req = _pending_topup(db_session, d.id)
    r = client.post(f"/api/admin/credit-topups/{req.id}/reject", headers=H(admin_token))
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Driver, d.id).credit_balance == 0  # no credits granted
    assert db_session.get(CreditTopupRequest, req.id).status == TopupStatus.rejected


def test_refund_and_bonus_adjust_balance(client, db_session, admin_token):
    d = _driver(db_session, status=VerificationStatus.verified)
    client.post(f"/api/admin/credits/{d.id}/bonus", headers=H(admin_token),
                json={"amount_credits": 5, "reason": "referral"})
    client.post(f"/api/admin/credits/{d.id}/refund", headers=H(admin_token),
                json={"amount_credits": 1, "reason": "no-show"})
    db_session.expire_all()
    assert db_session.get(Driver, d.id).credit_balance == 6


# --- memberships ---------------------------------------------------------

def test_activate_and_extend_membership(client, db_session, admin_token):
    d = _driver(db_session, status=VerificationStatus.verified)
    r = client.post(f"/api/admin/memberships/{d.id}/activate", headers=H(admin_token),
                    json={"months": 1, "amount_paid": "200.00"})
    assert r.status_code == 200
    end1 = r.json()["period_end"]
    r2 = client.post(f"/api/admin/memberships/{d.id}/extend?months=2", headers=H(admin_token))
    assert r2.status_code == 200
    assert r2.json()["period_end"] > end1
