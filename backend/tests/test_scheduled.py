"""Checkpoint 8: membership expiry + combined scheduled-jobs run (retention scrub,
stale-unconfirmed sweep, membership expiry) with audit logging."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import AuditLog, Booking, Driver, Membership, Rider
from app.models.enums import (
    BookingStatus,
    MembershipStatus,
    RideType,
    VerificationStatus,
)
from app.security import hash_password
from app.services import membership


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _now():
    return datetime.now(timezone.utc)


def _driver(db, phone):
    d = Driver(name="D", phone=phone, verification_status=VerificationStatus.verified,
               pin_hash=hash_password("1234"))
    db.add(d)
    db.flush()
    return d


def test_expire_lapsed_flips_status(client, db_session):
    d = _driver(db_session, "+2208010001")
    # a lapsed free_trial and a lapsed active, plus a still-valid one
    db_session.add(Membership(driver_id=d.id, status=MembershipStatus.free_trial,
                              period_start=_now() - timedelta(days=40),
                              period_end=_now() - timedelta(days=10), amount_paid=Decimal("0")))
    db_session.add(Membership(driver_id=d.id, status=MembershipStatus.active,
                              period_start=_now() - timedelta(days=40),
                              period_end=_now() - timedelta(days=1), amount_paid=Decimal("200")))
    valid = Membership(driver_id=d.id, status=MembershipStatus.active,
                       period_start=_now() - timedelta(days=1),
                       period_end=_now() + timedelta(days=29), amount_paid=Decimal("200"))
    db_session.add(valid)
    db_session.flush()

    n = membership.expire_lapsed(db_session)
    db_session.flush()
    assert n == 2
    statuses = [m.status for m in db_session.query(Membership).filter_by(driver_id=d.id).all()]
    assert statuses.count(MembershipStatus.expired) == 2
    db_session.refresh(valid)
    assert valid.status == MembershipStatus.active  # untouched


def test_run_now_runs_all_jobs_and_audits(client, db_session, admin_token):
    # lapsed membership -> should expire
    d = _driver(db_session, "+2208010002")
    db_session.add(Membership(driver_id=d.id, status=MembershipStatus.free_trial,
                              period_start=_now() - timedelta(days=40),
                              period_end=_now() - timedelta(days=5), amount_paid=Decimal("0")))
    # stale claimed booking -> should flag pending_review
    r = Rider(name="Old", phone="+2208010003")
    db_session.add(r)
    db_session.flush()
    stale = Booking(rider_id=r.id, ride_type=RideType.ride, status=BookingStatus.claimed,
                    assigned_driver_id=d.id, claimed_at=_now() - timedelta(hours=5))
    db_session.add(stale)
    db_session.flush()

    resp = client.post("/api/admin/scheduled-jobs/run-now", headers=H(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["memberships_expired"] >= 1
    assert body["bookings_flagged"] >= 1

    db_session.expire_all()
    assert db_session.get(Booking, stale.id).status == BookingStatus.pending_review
    assert db_session.get(Membership, db_session.query(Membership.id).filter_by(
        driver_id=d.id).scalar()).status == MembershipStatus.expired

    # audit entries written for each job (admin_id None = system)
    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert {"scheduled.retention", "scheduled.stale_unconfirmed",
            "scheduled.membership_expiry"} <= actions


def test_run_now_requires_auth(client, db_session):
    assert client.post("/api/admin/scheduled-jobs/run-now").status_code == 401
