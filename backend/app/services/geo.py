"""Area matching (rule 4.1). Assign a pickup point to the nearest area whose
radius contains it; if none contains it, return None so the caller flags the
booking unassigned rather than silently dropping it."""

import math
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Area

EARTH_RADIUS_M = 6_371_000  # mean Earth radius, metres


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def match_area(db: Session, lat: Decimal | None, lng: Decimal | None) -> Area | None:
    """Nearest area whose radius contains the point, or None.

    None inputs (address-only booking) cannot be matched -> None -> unassigned.
    """
    if lat is None or lng is None:
        return None

    lat_f, lng_f = float(lat), float(lng)
    best: Area | None = None
    best_dist = float("inf")
    for area in db.query(Area).all():
        dist = haversine_m(lat_f, lng_f, float(area.center_lat), float(area.center_lng))
        if dist <= area.radius_meters and dist < best_dist:
            best, best_dist = area, dist
    return best
