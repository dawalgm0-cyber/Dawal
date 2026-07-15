"""Checkpoint 7: areas CRUD, captain assignment, and payout report (rule 4.9)."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import Captain, CreditLedger, Driver
from app.models.enums import CreditTxnType, VerificationStatus
from app.security import hash_password


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _driver(db, phone, area_id=None):
    d = Driver(name="D" + phone[-3:], phone=phone, area_id=area_id,
               verification_status=VerificationStatus.verified, pin_hash=hash_password("1234"))
    db.add(d)
    db.flush()
    return d


def _make_area(client, token, name="Banjul"):
    r = client.post("/api/admin/areas", headers=H(token), json={
        "name": name, "center_lat": "13.4549", "center_lng": "-16.5790",
        "radius_meters": 5000})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_area_crud(client, db_session, admin_token):
    aid = _make_area(client, admin_token)
    # patch radius
    p = client.patch(f"/api/admin/areas/{aid}", headers=H(admin_token),
                     json={"radius_meters": 8000})
    assert p.status_code == 200 and p.json()["radius_meters"] == 8000
    # list shows it (no captain yet)
    lst = client.get("/api/admin/areas", headers=H(admin_token))
    area = next(a for a in lst.json() if a["id"] == aid)
    assert area["captain_driver_id"] is None


def test_assign_captain_and_default_share(client, db_session, admin_token):
    aid = _make_area(client, admin_token)
    driver = _driver(db_session, "+2208001001", area_id=aid)
    r = client.post(f"/api/admin/areas/{aid}/assign-captain", headers=H(admin_token),
                    json={"driver_id": driver.id})
    assert r.status_code == 200
    assert r.json()["captain_driver_id"] == driver.id
    # default share from config (10)
    cap = db_session.query(Captain).filter_by(area_id=aid).one()
    assert cap.revenue_share_pct == Decimal("10")


def test_reassign_captain_replaces(client, db_session, admin_token):
    aid = _make_area(client, admin_token)
    d1 = _driver(db_session, "+2208001002", area_id=aid)
    d2 = _driver(db_session, "+2208001003", area_id=aid)
    client.post(f"/api/admin/areas/{aid}/assign-captain", headers=H(admin_token),
                json={"driver_id": d1.id})
    client.post(f"/api/admin/areas/{aid}/assign-captain", headers=H(admin_token),
                json={"driver_id": d2.id, "revenue_share_pct": "15"})
    caps = db_session.query(Captain).filter_by(area_id=aid).all()
    assert len(caps) == 1  # unique area -> replaced, not duplicated
    assert caps[0].driver_id == d2.id and caps[0].revenue_share_pct == Decimal("15")


def test_payout_summary_calculation(client, db_session, admin_token):
    aid = _make_area(client, admin_token)
    cap_driver = _driver(db_session, "+2208001004", area_id=aid)
    # two drivers in the area with purchases
    d1 = _driver(db_session, "+2208001005", area_id=aid)
    d2 = _driver(db_session, "+2208001006", area_id=aid)
    # a driver in a different area should NOT count
    other = _driver(db_session, "+2208001007", area_id=None)
    for drv, amt in [(d1, "190.00"), (d2, "100.00"), (other, "450.00")]:
        db_session.add(CreditLedger(driver_id=drv.id, transaction_type=CreditTxnType.purchase,
                                    amount_credits=10, amount_gmd=Decimal(amt),
                                    created_at=datetime.now(timezone.utc)))
    db_session.flush()
    client.post(f"/api/admin/areas/{aid}/assign-captain", headers=H(admin_token),
                json={"driver_id": cap_driver.id, "revenue_share_pct": "10"})
    cap = db_session.query(Captain).filter_by(area_id=aid).one()

    r = client.get(f"/api/admin/captains/{cap.id}/payout-summary", headers=H(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    # 190 + 100 = 290 (other area's 450 excluded); 10% -> 29.00
    assert Decimal(body["total_purchase_gmd"]) == Decimal("290.00")
    assert Decimal(body["payout_gmd"]) == Decimal("29.00")


def test_list_captains(client, db_session, admin_token):
    aid = _make_area(client, admin_token, name="Serekunda")
    d = _driver(db_session, "+2208001008", area_id=aid)
    client.post(f"/api/admin/areas/{aid}/assign-captain", headers=H(admin_token),
                json={"driver_id": d.id})
    r = client.get("/api/admin/captains", headers=H(admin_token))
    assert r.status_code == 200
    assert any(c["area_name"] == "Serekunda" and c["driver_id"] == d.id for c in r.json())
