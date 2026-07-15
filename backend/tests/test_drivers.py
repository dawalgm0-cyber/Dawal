"""Driver registration, PIN login, and self-scoped account endpoints."""

from decimal import Decimal

from app.models import CreditTopupRequest, Driver
from app.models.enums import VerificationStatus
from app.security import hash_password


def _register(client, phone="+2208001111", pin="1234", name="Ebrima"):
    return client.post("/api/drivers/register", json={
        "name": name, "phone": phone, "pin": pin,
        "vehicle_type": "sedan", "plate_number": "BJL 1234"})


def H(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_token_and_pending(client, db_session):
    r = _register(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verification_status"] == "pending"
    assert body["access_token"]
    driver = db_session.get(Driver, body["driver_id"])
    assert driver.pin_hash is not None and driver.pin_hash != "1234"  # hashed


def test_duplicate_phone_rejected(client, db_session):
    _register(client, phone="+2208002222")
    r = _register(client, phone="+2208002222")
    assert r.status_code == 409


def test_login_wrong_pin_401(client, db_session):
    _register(client, phone="+2208003333", pin="1234")
    r = client.post("/api/drivers/login", json={"phone": "+2208003333", "pin": "9999"})
    assert r.status_code == 401


def test_profile_requires_auth(client, db_session):
    body = _register(client, phone="+2208004444").json()
    assert client.get(f"/api/drivers/{body['driver_id']}/profile").status_code == 401


def test_driver_cannot_access_other_driver(client, db_session):
    a = _register(client, phone="+2208005555").json()
    b = _register(client, phone="+2208006666").json()
    # A's token, B's id -> 403
    r = client.get(f"/api/drivers/{b['driver_id']}/profile", headers=H(a["access_token"]))
    assert r.status_code == 403


def test_credit_topup_request_created(client, db_session):
    reg = _register(client, phone="+2208007777").json()
    did, tok = reg["driver_id"], reg["access_token"]
    r = client.post(f"/api/drivers/{did}/credit-topup-request", headers=H(tok), json={
        "amount_credits": 10, "amount_gmd": "190.00", "payment_method": "wave",
        "reference_number": "WAVE123"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    req = db_session.query(CreditTopupRequest).filter_by(driver_id=did).one()
    assert req.amount_credits == 10 and req.amount_gmd == Decimal("190.00")


def test_credit_balance_and_standing(client, db_session):
    reg = _register(client, phone="+2208008888").json()
    did, tok = reg["driver_id"], reg["access_token"]
    assert client.get(f"/api/drivers/{did}/credit-balance",
                      headers=H(tok)).json()["credit_balance"] == 0
    s = client.get(f"/api/drivers/{did}/standing", headers=H(tok)).json()
    assert s["standing_tier"] == "new" and s["completed_jobs"] == 0
