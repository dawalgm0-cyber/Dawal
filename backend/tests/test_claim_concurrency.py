"""Race-safety proof for rule 4.3 (Section 10 requires this test): fire many
simultaneous claims at one posted booking and assert EXACTLY one succeeds, one
credit is burned, and the link is used once.

Uses real committed rows and one DB connection per thread (the savepoint
rollback fixture cannot express real concurrency), and cleans up after itself.
"""

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

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
    MembershipStatus,
    RideType,
    VerificationStatus,
)
from app.security import hash_password
from app.services.claim import claim_booking

N_DRIVERS = 12
START_CREDITS = 5
PIN = "1234"


def _now():
    return datetime.now(timezone.utc)


def test_exactly_one_concurrent_claim_wins(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # --- committed setup ---
    setup = Session()
    area = Area(name="RaceArea", center_lat=Decimal("13.0"),
                center_lng=Decimal("-16.0"), radius_meters=5000)
    setup.add(area)
    rider = Rider(name="Race Rider", phone="+220RACE0000")
    setup.add(rider)
    setup.flush()
    booking = Booking(rider_id=rider.id, area_id=area.id, ride_type=RideType.ride,
                      status=BookingStatus.posted, posted_at=_now(),
                      pickup_address_text="pickup", destination_text="dest")
    setup.add(booking)
    setup.flush()
    token = "race_token_xyz"
    setup.add(ClaimLink(booking_id=booking.id, token=token,
                        expires_at=_now() + timedelta(hours=2)))
    driver_ids, driver_phones = [], []
    for i in range(N_DRIVERS):
        d = Driver(name=f"Racer{i}", phone=f"+220RACER{i:04d}",
                   verification_status=VerificationStatus.verified,
                   credit_balance=START_CREDITS, pin_hash=hash_password(PIN))
        setup.add(d)
        setup.flush()
        setup.add(Membership(driver_id=d.id, status=MembershipStatus.active,
                             period_start=_now() - timedelta(days=1),
                             period_end=_now() + timedelta(days=30),
                             amount_paid=Decimal("200.00")))
        driver_ids.append(d.id)
        driver_phones.append(d.phone)
    booking_id = booking.id
    setup.commit()
    setup.close()

    # --- fire all claims simultaneously ---
    results: list[str] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(N_DRIVERS)

    def worker(phone: str):
        sess = Session()
        try:
            barrier.wait()  # release all threads at once
            outcome = claim_booking(sess, token, phone, PIN)
            with results_lock:
                results.append(outcome.status)
        finally:
            sess.close()

    threads = [threading.Thread(target=worker, args=(p,)) for p in driver_phones]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # --- assertions ---
        assert results.count("claimed") == 1, results
        assert results.count("already_claimed") == N_DRIVERS - 1, results

        verify = Session()
        try:
            b = verify.get(Booking, booking_id)
            assert b.status == BookingStatus.claimed
            assert b.assigned_driver_id in driver_ids

            burns = (
                verify.query(CreditLedger)
                .filter_by(booking_id=booking_id)
                .all()
            )
            assert len(burns) == 1, f"expected 1 burn, got {len(burns)}"

            link = verify.query(ClaimLink).filter_by(token=token).one()
            assert link.used_at is not None
            assert link.used_by_driver_id == b.assigned_driver_id

            # winner lost exactly one credit; everyone else untouched
            for did in driver_ids:
                d = verify.get(Driver, did)
                expected = START_CREDITS - (1 if did == b.assigned_driver_id else 0)
                assert d.credit_balance == expected, (did, d.credit_balance)
        finally:
            verify.close()
    finally:
        _cleanup(Session, booking_id, driver_ids, area.id, rider.id, token)


def _cleanup(Session, booking_id, driver_ids, area_id, rider_id, token):
    s = Session()
    try:
        s.execute(delete(CreditLedger).where(CreditLedger.booking_id == booking_id))
        s.execute(delete(ClaimLink).where(ClaimLink.token == token))
        s.execute(delete(Booking).where(Booking.id == booking_id))
        s.execute(delete(Membership).where(Membership.driver_id.in_(driver_ids)))
        s.execute(delete(Driver).where(Driver.id.in_(driver_ids)))
        s.execute(delete(Rider).where(Rider.id == rider_id))
        s.execute(delete(Area).where(Area.id == area_id))
        s.commit()
    finally:
        s.close()
