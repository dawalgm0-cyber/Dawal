"""Checkpoint 6 admin endpoints: riders + PDPP export/erasure, analytics,
compliance (consent/retention/audit), settings (config/templates/admin users)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import (
    AdminUser,
    Booking,
    ConsentLog,
    CreditLedger,
    Dispute,
    Rider,
)
from app.models.enums import (
    AdminRole,
    BookingStatus,
    CreditTxnType,
    DisputeRaisedBy,
    DisputeStatus,
    DisputeType,
    RideType,
)
from app.security import hash_password
from app.services import retention


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _now():
    return datetime.now(timezone.utc)


def _rider(db, name="Awa", phone="+2207770001"):
    r = Rider(name=name, phone=phone)
    db.add(r)
    db.flush()
    return r


# --- riders + PDPP -------------------------------------------------------

def test_riders_list_and_detail(client, db_session, admin_token):
    r = _rider(db_session)
    db_session.add(Booking(rider_id=r.id, ride_type=RideType.ride,
                           status=BookingStatus.pending))
    db_session.flush()
    lst = client.get("/api/admin/riders", headers=H(admin_token))
    assert lst.status_code == 200 and any(x["id"] == r.id for x in lst.json())
    detail = client.get(f"/api/admin/riders/{r.id}", headers=H(admin_token))
    assert detail.json()["booking_count"] == 1


def test_blacklist_rider(client, db_session, admin_token):
    r = _rider(db_session, phone="+2207770002")
    resp = client.post(f"/api/admin/riders/{r.id}/blacklist", headers=H(admin_token),
                       json={"reason": "spam"})
    assert resp.status_code == 200 and resp.json()["blacklisted"] is True


def test_data_export_returns_related(client, db_session, admin_token):
    r = _rider(db_session, phone="+2207770003")
    b = Booking(rider_id=r.id, ride_type=RideType.ride, status=BookingStatus.pending)
    db_session.add(b)
    db_session.flush()
    db_session.add(ConsentLog(rider_id=r.id, booking_id=b.id, ip_address="1.2.3.4"))
    db_session.flush()
    resp = client.get(f"/api/admin/riders/{r.id}/data-export", headers=H(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["rider"]["id"] == r.id
    assert len(body["bookings"]) == 1 and len(body["consent_logs"]) == 1


def test_erase_data_scrubs_pii(client, db_session, admin_token):
    r = _rider(db_session, name="Real Name", phone="+2207770004")
    b = Booking(rider_id=r.id, ride_type=RideType.ride, status=BookingStatus.completed,
                pickup_address_text="12 Secret St")
    db_session.add(b)
    db_session.flush()
    resp = client.delete(f"/api/admin/riders/{r.id}/data", headers=H(admin_token))
    assert resp.status_code == 200
    db_session.expire_all()
    r2 = db_session.get(Rider, r.id)
    assert r2.name == "[erased]" and r2.phone.startswith("erased_")
    assert db_session.get(Booking, b.id).pickup_address_text is None


def test_erase_blocked_by_open_dispute(client, db_session, admin_token):
    r = _rider(db_session, phone="+2207770005")
    b = Booking(rider_id=r.id, ride_type=RideType.ride, status=BookingStatus.claimed)
    db_session.add(b)
    db_session.flush()
    db_session.add(Dispute(booking_id=b.id, raised_by=DisputeRaisedBy.driver,
                           type=DisputeType.no_show, status=DisputeStatus.open))
    db_session.flush()
    resp = client.delete(f"/api/admin/riders/{r.id}/data", headers=H(admin_token))
    assert resp.status_code == 409


# --- analytics -----------------------------------------------------------

def test_analytics_endpoints(client, db_session, admin_token):
    r = _rider(db_session, phone="+2207770006")
    db_session.add(Booking(rider_id=r.id, ride_type=RideType.ride,
                           status=BookingStatus.pending))
    db_session.flush()
    assert client.get("/api/admin/analytics/bookings-trend", headers=H(admin_token)).status_code == 200
    arpd = client.get("/api/admin/analytics/arpd", headers=H(admin_token))
    assert arpd.status_code == 200 and "arpd_gmd" in arpd.json()
    assert client.get("/api/admin/analytics/repurchase-rate", headers=H(admin_token)).status_code == 200
    assert client.get("/api/admin/analytics/area-heatmap", headers=H(admin_token)).status_code == 200


# --- compliance ----------------------------------------------------------

def test_retention_queue_and_run(client, db_session, admin_token):
    # a rider whose only booking is older than the retention window
    old = _rider(db_session, name="Old One", phone="+2207770007")
    old.created_at = _now() - timedelta(days=40)
    b = Booking(rider_id=old.id, ride_type=RideType.ride, status=BookingStatus.completed)
    db_session.add(b)
    db_session.flush()
    b.created_at = _now() - timedelta(days=40)
    db_session.flush()

    q = client.get("/api/admin/retention-queue", headers=H(admin_token))
    assert q.status_code == 200 and old.id in q.json()["eligible_rider_ids"]

    run = client.post("/api/admin/retention/run-now", headers=H(admin_token))
    assert run.status_code == 200 and run.json()["scrubbed"] >= 1
    db_session.expire_all()
    assert db_session.get(Rider, old.id).name == "[erased]"


def test_consent_and_audit_logs(client, db_session, admin_token):
    r = _rider(db_session, phone="+2207770008")
    b = Booking(rider_id=r.id, ride_type=RideType.ride, status=BookingStatus.pending)
    db_session.add(b)
    db_session.flush()
    db_session.add(ConsentLog(rider_id=r.id, booking_id=b.id, ip_address="9.9.9.9"))
    db_session.flush()
    # blacklist writes an audit entry
    client.post(f"/api/admin/riders/{r.id}/blacklist", headers=H(admin_token), json={})
    assert len(client.get("/api/admin/consent-logs", headers=H(admin_token)).json()) >= 1
    assert len(client.get("/api/admin/audit-log", headers=H(admin_token)).json()) >= 1


# --- settings ------------------------------------------------------------

def test_pricing_config_get_and_patch(client, db_session, admin_token):
    r = client.get("/api/admin/pricing-config", headers=H(admin_token))
    assert r.status_code == 200 and any(c["key"] == "membership_fee_gmd" for c in r.json())
    patch = client.patch("/api/admin/pricing-config", headers=H(admin_token),
                          json={"updates": {"membership_fee_gmd": "250"}})
    assert patch.status_code == 200
    val = next(c["value"] for c in patch.json() if c["key"] == "membership_fee_gmd")
    assert val == "250"


def test_pricing_patch_rejects_bad_value(client, db_session, admin_token):
    r = client.patch("/api/admin/pricing-config", headers=H(admin_token),
                     json={"updates": {"membership_fee_gmd": "not-a-number"}})
    assert r.status_code == 422


def test_message_template_patch(client, db_session, admin_token):
    r = client.patch("/api/admin/message-templates/consent_notice", headers=H(admin_token),
                     json={"template_text": "Updated consent text {retention_days}."})
    assert r.status_code == 200 and "Updated consent" in r.json()["template_text"]


def test_admin_user_crud_super_admin_only(client, db_session, admin_token):
    # admin_token fixture is super_admin -> can create
    create = client.post("/api/admin/users", headers=H(admin_token), json={
        "name": "Dispatcher", "email": "dispatch@dawal", "password": "pw12345",
        "role": "dispatcher"})
    assert create.status_code == 201
    new_id = create.json()["id"]
    lst = client.get("/api/admin/users", headers=H(admin_token))
    assert any(u["id"] == new_id for u in lst.json())
    patch = client.patch(f"/api/admin/users/{new_id}", headers=H(admin_token),
                         json={"role": "captain_viewer"})
    assert patch.status_code == 200 and patch.json()["role"] == "captain_viewer"


def test_non_super_admin_cannot_create_admin(client, db_session):
    from app.auth import create_access_token
    disp = AdminUser(name="D", email="d@dawal", password_hash=hash_password("x"),
                     role=AdminRole.dispatcher)
    db_session.add(disp)
    db_session.flush()
    token = create_access_token(disp)
    r = client.post("/api/admin/users", headers=H(token), json={
        "name": "X", "email": "x@dawal", "password": "pw12345", "role": "dispatcher"})
    assert r.status_code == 403
