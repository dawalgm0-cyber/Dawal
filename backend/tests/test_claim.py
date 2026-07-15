"""Checkpoint 2 claim logic (non-concurrent): eligibility gating, PII release
only on success, link stays open when a driver is ineligible, expiry, and the
PII-free pre-claim view. The race-safety proof lives in test_claim_concurrency.py.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import (
    Area,
    Booking,
    ClaimLink,
    CreditLedger,
    Driver,
    Membership,
    Rider,
)
from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    MembershipStatus,
    RideType,
    VerificationStatus,
)
from app.security import hash_password

PIN = "1234"


def _now():
    return datetime.now(timezone.utc)


def _setup_claimable(db, *, credits=5, verified=True, membership=True, expired=False):
    area = Area(name="Banjul", center_lat=Decimal("13.4549"),
                center_lng=Decimal("-16.5790"), radius_meters=5000)
    db.add(area)
    rider = Rider(name="Isatou Jallow", phone="+2207001111")
    db.add(rider)
    db.flush()
    booking = Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.ride,
                      status=BookingStatus.posted, pickup_address_text="12 Liberation Ave",
                      destination_text="Airport", posted_at=_now())
    db.add(booking)
    db.flush()
    link = ClaimLink(
        booking_id=booking.id,
        token="tok_" + str(booking.id),
        expires_at=_now() + (timedelta(minutes=-1) if expired else timedelta(hours=2)),
    )
    db.add(link)
    driver = Driver(
        name="Modou Njie", phone="+2208002222",
        verification_status=VerificationStatus.verified if verified
        else VerificationStatus.pending,
        credit_balance=credits, pin_hash=hash_password(PIN),
    )
    db.add(driver)
    db.flush()
    if membership:
        db.add(Membership(driver_id=driver.id, status=MembershipStatus.active,
                          period_start=_now() - timedelta(days=1),
                          period_end=_now() + timedelta(days=30),
                          amount_paid=Decimal("200.00")))
    db.flush()
    return {"booking": booking, "link": link, "driver": driver, "rider": rider}


# --- success + PII release ----------------------------------------------

def test_claim_success_releases_pii_and_burns_one_credit(client, db_session):
    ctx = _setup_claimable(db_session, credits=5)
    token, phone, bid = ctx["link"].token, ctx["driver"].phone, ctx["booking"].id

    r = client.post(f"/api/claim/{token}", json={"driver_phone": phone, "driver_pin": PIN})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rider_name"] == "Isatou Jallow"
    assert body["rider_phone"] == "+2207001111"
    assert body["pickup_address_text"] == "12 Liberation Ave"

    db_session.expire_all()
    booking = db_session.get(Booking, bid)
    assert booking.status == BookingStatus.claimed
    assert booking.assigned_driver_id == ctx["driver"].id
    driver = db_session.get(Driver, ctx["driver"].id)
    assert driver.credit_balance == 4
    burns = (
        db_session.query(CreditLedger)
        .filter_by(booking_id=bid, transaction_type=CreditTxnType.burn)
        .all()
    )
    assert len(burns) == 1 and burns[0].amount_credits == -1
    link = db_session.query(ClaimLink).filter_by(token=token).one()
    assert link.used_at is not None and link.used_by_driver_id == driver.id


def test_second_claim_after_success_is_conflict(client, db_session):
    ctx = _setup_claimable(db_session)
    token = ctx["link"].token
    client.post(f"/api/claim/{token}", json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN})
    # a different verified driver tries the used link
    other = Driver(name="Other", phone="+2208009999",
                   verification_status=VerificationStatus.verified, credit_balance=5,
                   pin_hash=hash_password(PIN))
    db_session.add(other)
    db_session.flush()
    r = client.post(f"/api/claim/{token}",
                    json={"driver_phone": other.phone, "driver_pin": PIN})
    assert r.status_code == 409


# --- eligibility gating; link must stay open ----------------------------

def test_insufficient_credits_rejected_and_link_stays_open(client, db_session):
    ctx = _setup_claimable(db_session, credits=0)
    token, bid = ctx["link"].token, ctx["booking"].id
    r = client.post(f"/api/claim/{token}", json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN})
    assert r.status_code == 402
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.posted  # still open
    assert db_session.query(ClaimLink).filter_by(token=token).one().used_at is None
    assert db_session.query(CreditLedger).filter_by(booking_id=bid).count() == 0


def test_inactive_membership_rejected(client, db_session):
    ctx = _setup_claimable(db_session, membership=False)
    r = client.post(
        f"/api/claim/{ctx['link'].token}",
        json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN},
    )
    assert r.status_code == 402
    assert "membership" in r.json()["detail"].lower()


def test_unverified_driver_rejected(client, db_session):
    ctx = _setup_claimable(db_session, verified=False)
    r = client.post(
        f"/api/claim/{ctx['link'].token}",
        json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN},
    )
    assert r.status_code == 403


def test_unknown_driver_rejected(client, db_session):
    ctx = _setup_claimable(db_session)
    r = client.post(
        f"/api/claim/{ctx['link'].token}",
        json={"driver_phone": "+220000nobody", "driver_pin": PIN},
    )
    assert r.status_code == 403


def test_wrong_pin_rejected_and_link_stays_open(client, db_session):
    ctx = _setup_claimable(db_session)
    token, bid = ctx["link"].token, ctx["booking"].id
    r = client.post(f"/api/claim/{token}",
                    json={"driver_phone": ctx["driver"].phone, "driver_pin": "9999"})
    assert r.status_code == 403
    assert "PIN" in r.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.posted  # untouched
    assert db_session.query(ClaimLink).filter_by(token=token).one().used_at is None


def test_missing_pin_is_422(client, db_session):
    ctx = _setup_claimable(db_session)
    r = client.post(f"/api/claim/{ctx['link'].token}",
                    json={"driver_phone": ctx["driver"].phone})
    assert r.status_code == 422


# --- link state ----------------------------------------------------------

def test_expired_link_rejected(client, db_session):
    ctx = _setup_claimable(db_session, expired=True)
    r = client.post(
        f"/api/claim/{ctx['link'].token}",
        json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN},
    )
    assert r.status_code == 410


def test_unknown_token_404(client, db_session):
    r = client.post("/api/claim/nope",
                    json={"driver_phone": "+2208002222", "driver_pin": PIN})
    assert r.status_code == 404


# --- pre-claim view (no PII) ---------------------------------------------

def test_claim_view_hides_pii(client, db_session):
    ctx = _setup_claimable(db_session)
    r = client.get(f"/api/claim/{ctx['link'].token}")
    assert r.status_code == 200
    body = r.json()
    assert body["claimable"] is True
    assert body["area_name"] == "Banjul"
    # no rider identity anywhere in the payload
    assert "Isatou" not in r.text and "7001111" not in r.text


def test_claim_view_after_claim_shows_claimed(client, db_session):
    ctx = _setup_claimable(db_session)
    token = ctx["link"].token
    client.post(f"/api/claim/{token}", json={"driver_phone": ctx["driver"].phone, "driver_pin": PIN})
    r = client.get(f"/api/claim/{token}")
    assert r.json()["claimable"] is False
    assert r.json()["status_label"] == "Already claimed"


# --- integration with the booking flow ----------------------------------

def test_verify_otp_generates_claim_link(client, db_session, last_otp_code):
    db_session.add(Area(name="Banjul", center_lat=Decimal("13.4549"),
                        center_lng=Decimal("-16.5790"), radius_meters=5000))
    db_session.flush()
    r = client.post("/api/bookings", json={
        "name": "Awa", "phone": "+2203001234", "ride_type": "ride",
        "pickup_lat": 13.4549, "pickup_lng": -16.5790, "consent": True})
    bid = r.json()["id"]
    client.post(f"/api/bookings/{bid}/verify-otp", json={"code": last_otp_code()})
    link = db_session.query(ClaimLink).filter_by(booking_id=bid).one_or_none()
    assert link is not None and link.token
