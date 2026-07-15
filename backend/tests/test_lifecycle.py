"""Checkpoint 4: rider confirmation, rating, no-show + priority rebook, fake
flagging (refund + blacklist), override-assign, stale-unconfirmed sweep,
standing recalc, and disputes."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.auth import create_driver_token
from app.models import (
    Area,
    BlacklistEntry,
    Booking,
    ClaimLink,
    CreditLedger,
    Dispute,
    Driver,
    Membership,
    Rating,
    Rider,
)
from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    MembershipStatus,
    RideType,
    StandingTier,
    VerificationStatus,
)
from app.security import hash_password
from app.services import booking_ops, standing

TOKEN = "confirmtoken12345"
RIDER_TOKEN = "ridertoken1234567890"


def _now():
    return datetime.now(timezone.utc)


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _claimed(db, *, credit_balance=4, status=BookingStatus.claimed, confirm_token=TOKEN,
             claimed_delta=timedelta(minutes=5), rider_phone="+2207001111",
             driver_phone="+2208002222"):
    area = Area(name="Banjul", center_lat=Decimal("13.4549"),
                center_lng=Decimal("-16.5790"), radius_meters=5000)
    db.add(area)
    rider = Rider(name="Isatou", phone=rider_phone)
    db.add(rider)
    driver = Driver(name="Modou", phone=driver_phone,
                    verification_status=VerificationStatus.verified,
                    credit_balance=credit_balance, pin_hash=hash_password("1234"))
    db.add(driver)
    db.flush()
    db.add(Membership(driver_id=driver.id, status=MembershipStatus.active,
                      period_start=_now() - timedelta(days=1),
                      period_end=_now() + timedelta(days=30), amount_paid=Decimal("200")))
    booking = Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.ride,
                      status=status, assigned_driver_id=driver.id,
                      claimed_at=_now() - claimed_delta, confirm_token=confirm_token,
                      rider_access_token=RIDER_TOKEN,
                      pickup_address_text="12 Ave", destination_text="Airport")
    db.add(booking)
    db.flush()
    return {"area": area, "rider": rider, "driver": driver, "booking": booking}


# --- confirm-pickup (rule 4.4) ------------------------------------------

def test_confirm_pickup_completes(client, db_session):
    ctx = _claimed(db_session)
    bid = ctx["booking"].id
    r = client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    b = db_session.get(Booking, bid)
    assert b.status == BookingStatus.completed and b.completed_at is not None


def test_confirm_wrong_token_403(client, db_session):
    bid = _claimed(db_session)["booking"].id
    r = client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": "wrongtoken12345"})
    assert r.status_code == 403
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.claimed


def test_confirm_non_claimed_409(client, db_session):
    bid = _claimed(db_session, status=BookingStatus.posted)["booking"].id
    r = client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    assert r.status_code == 409


def test_confirm_idempotent(client, db_session):
    bid = _claimed(db_session)["booking"].id
    client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    again = client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    assert again.status_code == 200 and "Already confirmed" in again.json()["message"]


# --- rider access token (CP9 SPA support) --------------------------------

def test_status_enriches_driver_contact_only_with_token(client, db_session):
    bid = _claimed(db_session)["booking"].id
    # without token: no driver contact leaked
    plain = client.get(f"/api/bookings/{bid}/status").json()
    assert plain["assigned_driver_id"] is not None
    assert plain["driver_name"] is None and plain["driver_phone"] is None
    # with the rider token: driver contact shown
    enriched = client.get(f"/api/bookings/{bid}/status?token={RIDER_TOKEN}").json()
    assert enriched["driver_name"] == "Modou" and enriched["driver_phone"] == "+2208002222"


def test_confirm_with_rider_token(client, db_session):
    bid = _claimed(db_session)["booking"].id
    r = client.post(f"/api/bookings/{bid}/confirm-pickup",
                    json={"confirm_token": RIDER_TOKEN})
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.completed


def test_create_returns_rider_token(client, db_session, last_otp_code):
    db_session.add(Area(name="Banjul", center_lat=Decimal("13.4549"),
                        center_lng=Decimal("-16.5790"), radius_meters=5000))
    db_session.flush()
    r = client.post("/api/bookings", json={
        "name": "Awa", "phone": "+2203001299", "ride_type": "ride",
        "pickup_lat": 13.4549, "pickup_lng": -16.5790, "consent": True})
    assert r.status_code == 201
    assert len(r.json()["rider_token"]) > 20


# --- rate ----------------------------------------------------------------

def test_rate_after_confirm(client, db_session):
    ctx = _claimed(db_session)
    bid, did = ctx["booking"].id, ctx["driver"].id
    client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    r = client.post(f"/api/bookings/{bid}/rate",
                    json={"confirm_token": TOKEN, "rating_value": 5, "comment": "great"})
    assert r.status_code == 200
    rating = db_session.query(Rating).filter_by(booking_id=bid).one()
    assert rating.rating_value == 5 and rating.driver_id == did


def test_rate_before_confirm_409(client, db_session):
    bid = _claimed(db_session)["booking"].id
    r = client.post(f"/api/bookings/{bid}/rate",
                    json={"confirm_token": TOKEN, "rating_value": 4})
    assert r.status_code == 409


def test_double_rate_409(client, db_session):
    bid = _claimed(db_session)["booking"].id
    client.post(f"/api/bookings/{bid}/confirm-pickup", json={"confirm_token": TOKEN})
    client.post(f"/api/bookings/{bid}/rate", json={"confirm_token": TOKEN, "rating_value": 5})
    again = client.post(f"/api/bookings/{bid}/rate", json={"confirm_token": TOKEN, "rating_value": 1})
    assert again.status_code == 409


# --- no-show + priority rebook (rule 4.5) -------------------------------

def test_mark_no_show_creates_priority_rebook_no_refund(client, db_session, admin_token):
    ctx = _claimed(db_session, credit_balance=4)
    bid, did = ctx["booking"].id, ctx["driver"].id
    r = client.post(f"/api/admin/bookings/{bid}/mark-no-show", headers=H(admin_token))
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.no_show
    # credit NOT refunded
    assert db_session.get(Driver, did).credit_balance == 4
    # a priority rebook exists, posted, with a claim link
    rebook = db_session.query(Booking).filter_by(rebook_of_booking_id=bid).one()
    assert rebook.priority is True and rebook.status == BookingStatus.posted
    assert db_session.query(ClaimLink).filter_by(booking_id=rebook.id).one() is not None


# --- flag-fake (rule 4.5) -----------------------------------------------

def test_flag_fake_refunds_credit_and_counts(client, db_session, admin_token):
    ctx = _claimed(db_session, credit_balance=4)
    bid, did = ctx["booking"].id, ctx["driver"].id
    r = client.post(f"/api/admin/bookings/{bid}/flag-fake", headers=H(admin_token))
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.fake_flagged
    assert db_session.get(Driver, did).credit_balance == 5  # refunded 1
    refund = db_session.query(CreditLedger).filter_by(
        driver_id=did, transaction_type=CreditTxnType.refund).one()
    assert refund.amount_credits == 1 and refund.booking_id == bid
    assert db_session.get(Rider, ctx["rider"].id).fake_report_count == 1


def test_fake_report_blacklists_at_threshold(client, db_session, admin_token):
    ctx = _claimed(db_session)
    rider = ctx["rider"]
    rider.fake_report_count = 2  # threshold is 3
    db_session.flush()
    client.post(f"/api/admin/bookings/{ctx['booking'].id}/flag-fake", headers=H(admin_token))
    db_session.expire_all()
    r = db_session.get(Rider, rider.id)
    assert r.fake_report_count == 3 and r.blacklisted is True
    assert db_session.query(BlacklistEntry).filter_by(entity_ref=str(r.id)).count() == 1


# --- override-assign (rule 4.1) -----------------------------------------

def test_override_assign_unassigned_to_posted(client, db_session, admin_token):
    area = Area(name="Serekunda", center_lat=Decimal("13.43"), center_lng=Decimal("-16.67"),
                radius_meters=5000)
    rider = Rider(name="X", phone="+2201112222")
    db_session.add_all([area, rider])
    db_session.flush()
    booking = Booking(rider_id=rider.id, area_id=None, ride_type=RideType.ride,
                      status=BookingStatus.unassigned)
    db_session.add(booking)
    db_session.flush()
    r = client.post(f"/api/admin/bookings/{booking.id}/override-assign",
                    headers=H(admin_token), json={"area_id": area.id})
    assert r.status_code == 200
    db_session.expire_all()
    b = db_session.get(Booking, booking.id)
    assert b.status == BookingStatus.posted and b.area_id == area.id
    assert db_session.query(ClaimLink).filter_by(booking_id=b.id).one() is not None


# --- stale unconfirmed sweep (rule 4.4) ---------------------------------

def test_stale_unconfirmed_flagged_pending_review(client, db_session):
    fresh = _claimed(db_session, claimed_delta=timedelta(minutes=5))["booking"]
    stale = _claimed(db_session, confirm_token="othertoken12345",
                     claimed_delta=timedelta(hours=5), rider_phone="+2209990000",
                     driver_phone="+2209990001")["booking"]

    n = booking_ops.flag_stale_unconfirmed(db_session)
    db_session.flush()
    assert n == 1
    assert db_session.get(Booking, stale.id).status == BookingStatus.pending_review
    assert db_session.get(Booking, fresh.id).status == BookingStatus.claimed


# --- standing recalc (rule 4.8) -----------------------------------------

def _completed_booking(db, driver_id, rider_id, area_id, rating=None):
    b = Booking(rider_id=rider_id, area_id=area_id, ride_type=RideType.ride,
                status=BookingStatus.completed, assigned_driver_id=driver_id,
                completed_at=_now())
    db.add(b)
    db.flush()
    if rating is not None:
        db.add(Rating(booking_id=b.id, driver_id=driver_id, rider_id=rider_id,
                      rating_value=rating))
    db.flush()
    return b


def test_standing_standard_after_three_completed(client, db_session):
    ctx = _claimed(db_session)
    d, r, a = ctx["driver"], ctx["rider"], ctx["area"]
    for _ in range(3):
        _completed_booking(db_session, d.id, r.id, a.id, rating=5)
    tier = standing.recalc(db_session, d.id)
    assert tier == StandingTier.standard


def test_standing_new_below_threshold(client, db_session):
    ctx = _claimed(db_session)
    tier = standing.recalc(db_session, ctx["driver"].id)
    assert tier == StandingTier.new


def test_standing_gold_when_thresholds_met(client, db_session):
    from app.models import PricingConfig
    # lower the gold completed-jobs threshold for a compact test
    db_session.query(PricingConfig).filter_by(key="standing_gold_min_completed").one().value = "2"
    db_session.flush()
    ctx = _claimed(db_session)
    d, r, a = ctx["driver"], ctx["rider"], ctx["area"]
    for _ in range(2):
        _completed_booking(db_session, d.id, r.id, a.id, rating=5)
    tier = standing.recalc(db_session, d.id)
    assert tier == StandingTier.gold


# --- disputes (rule 4.5) ------------------------------------------------

def test_driver_raises_dispute_admin_resolves(client, db_session, admin_token):
    ctx = _claimed(db_session)
    bid, driver = ctx["booking"].id, ctx["driver"]
    dtoken = create_driver_token(driver)
    r = client.post(f"/api/bookings/{bid}/dispute", headers=H(dtoken),
                    json={"type": "no_show", "description": "rider never showed"})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    # admin sees it open and resolves
    lst = client.get("/api/admin/disputes?dispute_status=open", headers=H(admin_token))
    assert any(d["id"] == did for d in lst.json())
    res = client.post(f"/api/admin/disputes/{did}/resolve", headers=H(admin_token),
                      json={"resolution": "confirmed no-show", "status": "resolved"})
    assert res.status_code == 200
    d = db_session.get(Dispute, did)
    assert d.status.value == "resolved" and d.resolved_by_admin_id is not None


def test_driver_cannot_dispute_others_booking(client, db_session):
    ctx = _claimed(db_session)
    other = Driver(name="Other", phone="+2208887777",
                   verification_status=VerificationStatus.verified,
                   pin_hash=hash_password("1234"))
    db_session.add(other)
    db_session.flush()
    r = client.post(f"/api/bookings/{ctx['booking'].id}/dispute",
                    headers=H(create_driver_token(other)),
                    json={"type": "fraud"})
    assert r.status_code == 403
