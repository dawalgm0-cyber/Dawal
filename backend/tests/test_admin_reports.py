"""Admin read endpoints: dashboard summary, bookings list/detail, credit ledger."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Area, Booking, CreditLedger, Driver, Rider
from app.models.enums import (
    BookingStatus,
    CreditTxnType,
    RideType,
    VerificationStatus,
)
from app.security import hash_password


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _now():
    return datetime.now(timezone.utc)


def test_reports_require_auth(client, db_session):
    assert client.get("/api/admin/dashboard/summary").status_code == 401
    assert client.get("/api/admin/bookings").status_code == 401


def test_dashboard_summary_counts(client, db_session, admin_token):
    area = Area(name="Banjul", center_lat=Decimal("13.45"), center_lng=Decimal("-16.57"),
                radius_meters=5000)
    rider = Rider(name="R", phone="+2201230000")
    db_session.add_all([area, rider])
    db_session.flush()
    # one pending (unassigned) booking today, one pending-verification driver
    db_session.add(Booking(rider_id=rider.id, area_id=None, ride_type=RideType.ride,
                           status=BookingStatus.unassigned))
    drv = Driver(name="D", phone="+2209990000",
                 verification_status=VerificationStatus.verified,
                 pin_hash=hash_password("1234"))
    db_session.add(drv)
    db_session.add(Driver(name="P", phone="+2209990001",
                          verification_status=VerificationStatus.pending,
                          pin_hash=hash_password("1234")))
    db_session.flush()
    # a purchase today -> revenue
    db_session.add(CreditLedger(driver_id=drv.id, transaction_type=CreditTxnType.purchase,
                                amount_credits=10, amount_gmd=Decimal("190.00")))
    db_session.flush()

    r = client.get("/api/admin/dashboard/summary", headers=H(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bookings_today"] >= 1
    assert body["active_drivers"] >= 1
    assert body["alerts"]["pending_verifications"] >= 1
    assert body["alerts"]["unassigned_bookings"] >= 1
    assert Decimal(str(body["revenue_today_gmd"])) >= Decimal("190.00")


def test_bookings_list_and_filter(client, db_session, admin_token):
    area = Area(name="Banjul", center_lat=Decimal("13.45"), center_lng=Decimal("-16.57"),
                radius_meters=5000)
    rider = Rider(name="Fatou", phone="+2201231111")
    db_session.add_all([area, rider])
    db_session.flush()
    db_session.add(Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.ride,
                           status=BookingStatus.posted))
    db_session.add(Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.delivery,
                           status=BookingStatus.completed))
    db_session.flush()

    r = client.get("/api/admin/bookings", headers=H(admin_token))
    assert r.status_code == 200
    assert any(b["rider_name"] == "Fatou" for b in r.json())

    r2 = client.get("/api/admin/bookings?booking_status=posted", headers=H(admin_token))
    assert all(b["status"] == "posted" for b in r2.json())


def test_booking_detail_includes_rider(client, db_session, admin_token):
    area = Area(name="Banjul", center_lat=Decimal("13.45"), center_lng=Decimal("-16.57"),
                radius_meters=5000)
    rider = Rider(name="Musa", phone="+2201232222")
    db_session.add_all([area, rider])
    db_session.flush()
    b = Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.ride,
                status=BookingStatus.pending, pickup_address_text="Main St")
    db_session.add(b)
    db_session.flush()

    r = client.get(f"/api/admin/bookings/{b.id}", headers=H(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["rider_name"] == "Musa" and body["pickup_address_text"] == "Main St"


def test_credit_ledger_view(client, db_session, admin_token):
    drv = Driver(name="D", phone="+2209992222",
                 verification_status=VerificationStatus.verified, pin_hash=hash_password("1234"))
    db_session.add(drv)
    db_session.flush()
    db_session.add(CreditLedger(driver_id=drv.id, transaction_type=CreditTxnType.bonus,
                                amount_credits=5))
    db_session.flush()
    r = client.get(f"/api/admin/credit-ledger?driver_id={drv.id}", headers=H(admin_token))
    assert r.status_code == 200
    assert len(r.json()) == 1 and r.json()[0]["transaction_type"] == "bonus"
