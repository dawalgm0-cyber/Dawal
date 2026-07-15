"""Checkpoint 1 behaviour tests: area matching (+ unassigned fallback), rate
limiting, OTP flow, and consent logging."""

from datetime import datetime, timedelta, timezone

from app.models import Area, Booking, ConsentLog, Rider
from app.models.enums import BookingStatus
from app.services import otp as otp_mod
from app.services.sms import SmsError

# Banjul-ish coordinates for fixtures.
BANJUL = (13.4549, -16.5790)
SEREKUNDA = (13.4382, -16.6781)


def _make_area(db, name, lat, lng, radius_m):
    a = Area(name=name, center_lat=lat, center_lng=lng, radius_meters=radius_m)
    db.add(a)
    db.flush()
    return a


def _booking_payload(**over):
    base = {
        "name": "Awa Ceesay",
        "phone": "+2203001234",
        "ride_type": "ride",
        "pickup_lat": BANJUL[0],
        "pickup_lng": BANJUL[1],
        "destination_text": "Airport",
        "consent": True,
    }
    base.update(over)
    return base


# --- SMS gateway resilience ----------------------------------------------

def test_booking_returns_502_when_sms_fails(client, db_session, monkeypatch):
    """A gateway failure must not 500; the booking rolls back and returns 502."""
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)

    class _Boom:
        def send(self, to, body):
            raise SmsError("gateway unreachable")

    monkeypatch.setattr(otp_mod, "get_sms_provider", lambda: _Boom())

    r = client.post("/api/bookings", json=_booking_payload(phone="+2203009999"))
    assert r.status_code == 502
    # nothing persisted for that phone
    assert db_session.query(Rider).filter_by(phone="+2203009999").count() == 0
    assert db_session.query(Booking).count() == 0


# --- area matching -------------------------------------------------------

def test_booking_matches_nearest_area(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    _make_area(db_session, "Serekunda", SEREKUNDA[0], SEREKUNDA[1], 5000)

    r = client.post("/api/bookings", json=_booking_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["area_name"] == "Banjul"
    assert body["status"] == "pending"


def test_booking_unassigned_when_no_area_matches(client, db_session, last_otp_code):
    # Area far from the pickup point, small radius -> no match.
    _make_area(db_session, "Faraway", 13.0, -16.9, 1000)

    r = client.post("/api/bookings", json=_booking_payload())
    assert r.status_code == 201, r.text
    booking_id = r.json()["id"]
    assert r.json()["area_id"] is None

    # After OTP it becomes 'unassigned' (surfaced to admin), not silently dropped.
    r2 = client.post(
        f"/api/bookings/{booking_id}/verify-otp", json={"code": last_otp_code()}
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "unassigned"


def test_address_only_booking_is_unassigned(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    payload = _booking_payload(pickup_lat=None, pickup_lng=None,
                               pickup_address_text="Somewhere in town")
    r = client.post("/api/bookings", json=payload)
    assert r.status_code == 201, r.text
    assert r.json()["area_id"] is None


# --- OTP flow ------------------------------------------------------------

def test_otp_happy_path_moves_to_posted(client, db_session, last_otp_code):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    booking_id = r.json()["id"]

    r2 = client.post(
        f"/api/bookings/{booking_id}/verify-otp", json={"code": last_otp_code()}
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "posted"

    booking = db_session.get(Booking, booking_id)
    assert booking.status == BookingStatus.posted
    assert booking.posted_at is not None


def test_otp_wrong_then_right(client, db_session, last_otp_code):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    booking_id = r.json()["id"]
    code = last_otp_code()

    bad = client.post(f"/api/bookings/{booking_id}/verify-otp", json={"code": "000000"})
    assert bad.status_code == 400
    # booking still pending after a bad attempt
    assert db_session.get(Booking, booking_id).status == BookingStatus.pending

    good = client.post(f"/api/bookings/{booking_id}/verify-otp", json={"code": code})
    assert good.status_code == 200
    assert good.json()["status"] == "posted"


def test_otp_expired_is_rejected(client, db_session, last_otp_code):
    from app.models import OtpVerification

    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    booking_id = r.json()["id"]
    code = last_otp_code()

    otp_row = (
        db_session.query(OtpVerification).filter_by(booking_id=booking_id).one()
    )
    otp_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    r2 = client.post(f"/api/bookings/{booking_id}/verify-otp", json={"code": code})
    assert r2.status_code == 400
    assert "expired" in r2.json()["detail"].lower()


def test_cannot_verify_already_posted_booking(client, db_session, last_otp_code):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    booking_id = r.json()["id"]
    code = last_otp_code()
    client.post(f"/api/bookings/{booking_id}/verify-otp", json={"code": code})

    again = client.post(f"/api/bookings/{booking_id}/verify-otp", json={"code": code})
    assert again.status_code == 409


# --- rate limiting -------------------------------------------------------

def test_rate_limit_blocks_fourth_pending_booking(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    for _ in range(3):  # default limit = 3
        ok = client.post("/api/bookings", json=_booking_payload())
        assert ok.status_code == 201
    blocked = client.post("/api/bookings", json=_booking_payload())
    assert blocked.status_code == 429


def test_verified_booking_frees_rate_limit_slot(client, db_session, last_otp_code):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    code = last_otp_code()
    client.post(f"/api/bookings/{r.json()['id']}/verify-otp", json={"code": code})
    # Two more pending are still allowed since the first is no longer pending.
    for _ in range(3):
        assert client.post("/api/bookings", json=_booking_payload()).status_code == 201


# --- consent + guards ----------------------------------------------------

def test_consent_is_logged_with_ip(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    r = client.post("/api/bookings", json=_booking_payload())
    booking_id = r.json()["id"]
    log = db_session.query(ConsentLog).filter_by(booking_id=booking_id).one()
    assert log.consent_type == "data_sharing"
    assert log.ip_address is not None
    rider = db_session.get(Rider, log.rider_id)
    assert rider.consent_given_at is not None


def test_consent_must_be_true(client, db_session):
    r = client.post("/api/bookings", json=_booking_payload(consent=False))
    assert r.status_code == 422


def test_blacklisted_rider_cannot_book(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    db_session.add(Rider(name="Bad Actor", phone="+2209998888", blacklisted=True))
    db_session.flush()
    r = client.post("/api/bookings", json=_booking_payload(phone="+2209998888"))
    assert r.status_code == 403


# --- areas endpoint ------------------------------------------------------

def test_list_areas(client, db_session):
    _make_area(db_session, "Banjul", BANJUL[0], BANJUL[1], 5000)
    _make_area(db_session, "Serekunda", SEREKUNDA[0], SEREKUNDA[1], 5000)
    r = client.get("/api/areas")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert names == ["Banjul", "Serekunda"]
