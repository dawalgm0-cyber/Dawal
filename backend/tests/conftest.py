"""Test harness. Runs against a dedicated `dawal_test` Postgres database (real
enums/JSONB behaviour, same as prod). Each test runs inside a transaction that
is rolled back, so tests are isolated and order-independent even though the
endpoints call commit().
"""

import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Base, MessageTemplate, PricingConfig
from app.seed import MESSAGE_TEMPLATES, PRICING_DEFAULTS
from app.services.sms import _mock_singleton

# Tests always use the mock SMS provider (deterministic, reads OTP from outbox),
# regardless of what .env selects for the running app.
settings.SMS_PROVIDER = "mock"

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://dawal:dawal@localhost:5432/dawal_test",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = Session()
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    _seed_config(session)
    yield session

    session.close()
    trans.rollback()
    connection.close()


def _seed_config(session):
    for key, value, value_type in PRICING_DEFAULTS:
        session.add(PricingConfig(key=key, value=value, value_type=value_type))
    for key, text in MESSAGE_TEMPLATES.items():
        session.add(MessageTemplate(key=key, template_text=text))
    session.flush()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    _mock_singleton.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(client, db_session):
    from app.models import AdminUser
    from app.models.enums import AdminRole
    from app.security import hash_password

    db_session.add(AdminUser(name="Admin", email="admin@test.dawal",
                             password_hash=hash_password("pw123456"),
                             role=AdminRole.super_admin))
    db_session.flush()
    r = client.post("/api/admin/login",
                    json={"email": "admin@test.dawal", "password": "pw123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def last_otp_code():
    """Extract the OTP code from the most recent mock SMS."""

    def _get() -> str:
        assert _mock_singleton.outbox, "no SMS was sent"
        body = _mock_singleton.outbox[-1].body
        m = re.search(r"code is (\d+)", body)
        assert m, f"no code in SMS body: {body!r}"
        return m.group(1)

    return _get
