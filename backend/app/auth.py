"""Admin authentication: JWT issue/verify + FastAPI dependencies for
`/api/admin/*` (Section 10 requires valid JWT + role check)."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AdminUser, Driver
from app.models.enums import AdminRole

ALGORITHM = "HS256"
ADMIN_TOKEN_TTL_HOURS = 12
# Short-lived portal session: a valid token is required per request, but the
# driver re-enters their PIN at most once a day rather than every action.
DRIVER_TOKEN_TTL_HOURS = 24

# tokenUrl is where the interactive docs send credentials; the real login route
# lives in the admin_auth router.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")


def _encode(sub: int, typ: str, ttl_hours: int, **extra) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "typ": typ,  # 'admin' or 'driver' — a driver token can never pass as admin
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
        **extra,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_access_token(admin: AdminUser) -> str:
    return _encode(admin.id, "admin", ADMIN_TOKEN_TTL_HOURS, role=admin.role.value)


def create_driver_token(driver: Driver) -> str:
    return _encode(driver.id, "driver", DRIVER_TOKEN_TTL_HOURS)


_CREDS_EXC = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _decode(token: str, expected_typ: str) -> int:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("typ") != expected_typ:
            raise _CREDS_EXC
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _CREDS_EXC


def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> AdminUser:
    admin = db.get(AdminUser, _decode(token, "admin"))
    if admin is None:
        raise _CREDS_EXC
    return admin


def get_current_driver(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Driver:
    driver = db.get(Driver, _decode(token, "driver"))
    if driver is None:
        raise _CREDS_EXC
    return driver


def require_role(*roles: AdminRole):
    """Dependency factory: allow only admins whose role is in `roles`."""

    def _dep(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Insufficient permissions for this action."
            )
        return admin

    return _dep


# Convenience: any authenticated admin, vs. actions restricted to super_admin.
require_admin = get_current_admin
require_super_admin = require_role(AdminRole.super_admin)
