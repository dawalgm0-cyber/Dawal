"""Checkpoint 10 (Driver Portal): registration stores PIN, session token,
payment options from config, membership + top-up request status, membership
renewal request + admin approval."""

from decimal import Decimal

from app.models import Driver, Membership
from app.models.enums import MembershipStatus, VerificationStatus
from app.security import verify_password


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, phone="+2205560001", pin="4321"):
    return client.post("/api/drivers/register", json={
        "name": "Test Driver", "phone": phone, "pin": pin,
        "vehicle_type": "sedan", "plate_number": "BJL 0001",
        "license_number": "LIC-1"}).json()


# --- registration stores the PIN -----------------------------------------

def test_register_stores_pin_hash(client, db_session):
    reg = _register(client, phone="+2205560002")
    d = db_session.get(Driver, reg["driver_id"])
    assert d.pin_hash is not None and d.pin_hash != "4321"
    assert verify_password("4321", d.pin_hash)
    assert d.verification_status == VerificationStatus.pending


def test_register_requires_pin(client, db_session):
    r = client.post("/api/drivers/register", json={"name": "X", "phone": "+2205560003"})
    assert r.status_code == 422


# --- session token scoping -----------------------------------------------

def test_endpoints_require_token_and_are_self_scoped(client, db_session):
    a = _register(client, phone="+2205560004")
    b = _register(client, phone="+2205560005")
    # no token
    assert client.get(f"/api/drivers/{a['driver_id']}/membership").status_code == 401
    # a's token on b's data
    r = client.get(f"/api/drivers/{b['driver_id']}/payment-options",
                   headers=H(a["access_token"]))
    assert r.status_code == 403


# --- payment options come from config ------------------------------------

def test_payment_options_from_config(client, db_session, admin_token):
    reg = _register(client, phone="+2205560006")
    did, tok = reg["driver_id"], reg["access_token"]
    # admin sets a Wave number via pricing-config (proves it's not hardcoded)
    client.patch("/api/admin/pricing-config", headers=H(admin_token),
                 json={"updates": {"payment_wave_number": "+2203000001"}})
    r = client.get(f"/api/drivers/{did}/payment-options", headers=H(tok))
    assert r.status_code == 200
    body = r.json()
    blocks = {b["credits"]: b["amount_gmd"] for b in body["credit_blocks"]}
    assert blocks[5] == "100" and blocks[10] == "190" and blocks[25] == "450"
    assert body["membership_fee_gmd"] == "200"
    assert body["payment_numbers"]["wave"] == "+2203000001"


# --- membership + top-up status views ------------------------------------

def test_membership_none_then_topup_request_status(client, db_session):
    reg = _register(client, phone="+2205560007")
    did, tok = reg["driver_id"], reg["access_token"]
    # no membership yet
    m = client.get(f"/api/drivers/{did}/membership", headers=H(tok)).json()
    assert m["status"] is None
    # submit a top-up request, then see it in own list as pending
    client.post(f"/api/drivers/{did}/credit-topup-request", headers=H(tok), json={
        "amount_credits": 10, "amount_gmd": "190.00", "payment_method": "wave",
        "reference_number": "R1"})
    reqs = client.get(f"/api/drivers/{did}/topup-requests", headers=H(tok)).json()
    assert len(reqs) == 1 and reqs[0]["status"] == "pending"


# --- membership renewal request + admin approval -------------------------

def test_membership_request_approved_activates_membership(client, db_session, admin_token):
    reg = _register(client, phone="+2205560008")
    did, tok = reg["driver_id"], reg["access_token"]
    # driver submits a 2-month membership payment
    sub = client.post(f"/api/drivers/{did}/membership-request", headers=H(tok), json={
        "months": 2, "payment_method": "afrimoney", "reference_number": "AFRI-9"})
    assert sub.status_code == 201
    req = sub.json()
    # amount = fee(200) * 2 months = 400
    assert req["amount_gmd"] == "400" and req["status"] == "pending"
    rid = req["id"]

    # driver sees it in own list
    mine = client.get(f"/api/drivers/{did}/membership-requests", headers=H(tok)).json()
    assert any(x["id"] == rid for x in mine)

    # admin approves -> membership becomes active
    ap = client.post(f"/api/admin/membership-requests/{rid}/approve", headers=H(admin_token))
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    db_session.expire_all()
    m = db_session.query(Membership).filter_by(driver_id=did).one()
    assert m.status == MembershipStatus.active and m.amount_paid == Decimal("400.00")
    # driver now sees active membership
    dm = client.get(f"/api/drivers/{did}/membership", headers=H(tok)).json()
    assert dm["status"] == "active"


def test_membership_request_reject(client, db_session, admin_token):
    reg = _register(client, phone="+2205560009")
    did, tok = reg["driver_id"], reg["access_token"]
    rid = client.post(f"/api/drivers/{did}/membership-request", headers=H(tok),
                      json={"months": 1, "payment_method": "wave"}).json()["id"]
    r = client.post(f"/api/admin/membership-requests/{rid}/reject", headers=H(admin_token))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert db_session.query(Membership).filter_by(driver_id=did).count() == 0
    # double-review conflicts
    again = client.post(f"/api/admin/membership-requests/{rid}/approve", headers=H(admin_token))
    assert again.status_code == 409
