"""Checkpoint 11 load / race-condition pass. Goes beyond the single-booking
claim race: many simultaneous claim races, a driver's credit cap under
concurrency, and concurrent top-up approvals. Real committed rows + one DB
connection per thread; self-cleans.
"""

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func
from sqlalchemy.orm import sessionmaker

from app.models import (
    AdminUser,
    Area,
    Booking,
    ClaimLink,
    CreditLedger,
    CreditTopupRequest,
    Driver,
    Membership,
    Rider,
)
from app.models.enums import (
    AdminRole,
    BookingStatus,
    CreditTxnType,
    MembershipStatus,
    PaymentMethod,
    RideType,
    TopupStatus,
    VerificationStatus,
)
from app.security import hash_password
from app.services import credit
from app.services.claim import claim_booking

PIN = "1234"


def _now():
    return datetime.now(timezone.utc)


def _driver(s, phone, credits):
    d = Driver(name="LoadDrv", phone=phone, verification_status=VerificationStatus.verified,
               credit_balance=credits, pin_hash=hash_password(PIN))
    s.add(d)
    s.flush()
    s.add(Membership(driver_id=d.id, status=MembershipStatus.active,
                     period_start=_now() - timedelta(days=1),
                     period_end=_now() + timedelta(days=30), amount_paid=Decimal("200")))
    return d


def _posted_booking(s, area_id, tag):
    r = Rider(name="LoadRider", phone=f"+220LR{tag}")
    s.add(r)
    s.flush()
    b = Booking(rider_id=r.id, area_id=area_id, ride_type=RideType.ride,
                status=BookingStatus.posted, posted_at=_now())
    s.add(b)
    s.flush()
    token = f"loadtok_{tag}"
    s.add(ClaimLink(booking_id=b.id, token=token, expires_at=_now() + timedelta(hours=2)))
    return b, token, r.id


def _cleanup(Session, area_id, rider_ids, booking_ids, driver_ids):
    s = Session()
    try:
        s.execute(delete(CreditLedger).where(CreditLedger.driver_id.in_(driver_ids)))
        s.execute(delete(CreditTopupRequest).where(CreditTopupRequest.driver_id.in_(driver_ids)))
        s.execute(delete(ClaimLink).where(ClaimLink.booking_id.in_(booking_ids)))
        s.execute(delete(Booking).where(Booking.id.in_(booking_ids)))
        s.execute(delete(Membership).where(Membership.driver_id.in_(driver_ids)))
        s.execute(delete(Driver).where(Driver.id.in_(driver_ids)))
        s.execute(delete(Rider).where(Rider.id.in_(rider_ids)))
        s.execute(delete(Area).where(Area.id == area_id))
        s.commit()
    finally:
        s.close()


# --- 1. many concurrent claim races across K bookings --------------------

def test_many_concurrent_claim_races(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    K, N, START = 6, 5, 5  # 6 bookings, 5 drivers each racing all of them
    s = Session()
    area = Area(name="LoadArea", center_lat=Decimal("13.0"), center_lng=Decimal("-16.0"),
                radius_meters=5000)
    s.add(area)
    s.flush()
    drivers = [_driver(s, f"+220LD{i:03d}", START) for i in range(N)]
    s.flush()
    tokens, booking_ids, rider_ids = {}, [], []
    for k in range(K):
        b, tok, rid = _posted_booking(s, area.id, str(k))
        tokens[b.id] = tok
        booking_ids.append(b.id)
        rider_ids.append(rid)
    driver_ids = [d.id for d in drivers]
    driver_phones = [d.phone for d in drivers]
    s.commit()
    s.close()

    tasks = [(bid, phone) for bid in booking_ids for phone in driver_phones]  # K*N
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(tasks))

    def worker(bid, phone):
        sess = Session()
        try:
            barrier.wait()
            o = claim_booking(sess, tokens[bid], phone, PIN)
            with lock:
                results.append((bid, o.status))
        finally:
            sess.close()

    threads = [threading.Thread(target=worker, args=t) for t in tasks]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        v = Session()
        try:
            # every booking claimed exactly once
            for bid in booking_ids:
                assert v.get(Booking, bid).status == BookingStatus.claimed, bid
            assert sum(1 for _, st in results if st == "claimed") == K, "exactly K wins"
            # exactly K burns total; each booking has exactly one burn
            burns = v.query(func.count(CreditLedger.id)).filter(
                CreditLedger.booking_id.in_(booking_ids),
                CreditLedger.transaction_type == CreditTxnType.burn).scalar()
            assert burns == K, f"expected {K} burns, got {burns}"
            # no negative balances; total credits spent == K (one per booking)
            spent = 0
            for did in driver_ids:
                bal = v.get(Driver, did).credit_balance
                assert bal >= 0, f"driver {did} negative"
                spent += START - bal
            assert spent == K, f"expected {K} spent, got {spent}"
        finally:
            v.close()
    finally:
        _cleanup(Session, area.id, rider_ids, booking_ids, driver_ids)


# --- 2. a driver cannot overspend under concurrency ----------------------

def test_driver_credit_cap_under_race(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    CAP, M = 2, 6  # 2 credits, races for 6 different bookings at once
    s = Session()
    area = Area(name="CapArea", center_lat=Decimal("13.0"), center_lng=Decimal("-16.0"),
                radius_meters=5000)
    s.add(area)
    s.flush()
    d = _driver(s, "+220CAP001", CAP)
    s.flush()
    tokens, booking_ids, rider_ids = [], [], []
    for k in range(M):
        b, tok, rid = _posted_booking(s, area.id, f"cap{k}")
        tokens.append(tok)
        booking_ids.append(b.id)
        rider_ids.append(rid)
    did = d.id
    s.commit()
    s.close()

    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(M)

    def worker(tok):
        sess = Session()
        try:
            barrier.wait()
            o = claim_booking(sess, tok, "+220CAP001", PIN)
            with lock:
                results.append(o.status)
        finally:
            sess.close()

    threads = [threading.Thread(target=worker, args=(t,)) for t in tokens]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        v = Session()
        try:
            wins = sum(1 for st in results if st == "claimed")
            assert wins == CAP, f"driver should win exactly {CAP}, won {wins}"
            assert v.get(Driver, did).credit_balance == 0, "balance must be 0, never negative"
            burns = v.query(func.count(CreditLedger.id)).filter_by(
                driver_id=did, transaction_type=CreditTxnType.burn).scalar()
            assert burns == CAP
            claimed = v.query(func.count(Booking.id)).filter(
                Booking.id.in_(booking_ids), Booking.status == BookingStatus.claimed).scalar()
            assert claimed == CAP, "only CAP bookings claimed; rest stay posted"
        finally:
            v.close()
    finally:
        _cleanup(Session, area.id, rider_ids, booking_ids, [did])


# --- 3. concurrent top-up approvals must credit exactly once -------------

def test_concurrent_topup_approvals_credit_once(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    admin = AdminUser(name="LoadAdmin", email="loadadmin@dawal", password_hash="x",
                      role=AdminRole.super_admin)
    s.add(admin)
    d = _driver(s, "+220TOP001", 0)
    s.flush()
    req = CreditTopupRequest(driver_id=d.id, amount_credits=10, amount_gmd=Decimal("190"),
                             payment_method=PaymentMethod.wave, status=TopupStatus.pending)
    s.add(req)
    s.flush()
    did, rid, admin_id = d.id, req.id, admin.id
    s.commit()
    s.close()

    results = []
    lock = threading.Lock()
    n = 5
    barrier = threading.Barrier(n)

    def worker():
        sess = Session()
        try:
            barrier.wait()
            r = sess.get(CreditTopupRequest, rid)
            try:
                credit.approve_topup(sess, r, admin_id=admin_id)
                sess.commit()
                with lock:
                    results.append("approved")
            except ValueError:
                sess.rollback()
                with lock:
                    results.append("rejected")
        except Exception as e:  # e.g. DB serialization error -> treated as not-credited
            sess.rollback()
            with lock:
                results.append("error:" + type(e).__name__)
        finally:
            sess.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        v = Session()
        try:
            bal = v.get(Driver, did).credit_balance
            purchases = v.query(func.count(CreditLedger.id)).filter_by(
                driver_id=did, transaction_type=CreditTxnType.purchase).scalar()
            assert bal == 10, f"must credit exactly once (10), got {bal}  [{results}]"
            assert purchases == 1, f"must be exactly one purchase ledger row, got {purchases}"
            assert results.count("approved") == 1, f"exactly one approval should win: {results}"
        finally:
            v.close()
    finally:
        s = Session()
        s.execute(delete(CreditLedger).where(CreditLedger.driver_id == did))
        s.execute(delete(CreditTopupRequest).where(CreditTopupRequest.driver_id == did))
        s.execute(delete(Membership).where(Membership.driver_id == did))
        s.execute(delete(Driver).where(Driver.id == did))
        s.execute(delete(AdminUser).where(AdminUser.id == admin_id))
        s.commit()
        s.close()
