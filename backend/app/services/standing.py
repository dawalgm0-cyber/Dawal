"""Driver standing-tier recalculation (rule 4.8). Recomputed on every completed
or no-show booking so the tier is current when the next claim link is generated.
All thresholds come from pricing_config (never hardcoded)."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, Driver, Rating
from app.models.enums import BookingStatus, StandingTier
from app.services import config_service


def recalc(db: Session, driver_id: int) -> StandingTier:
    completed = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.assigned_driver_id == driver_id,
            Booking.status == BookingStatus.completed,
        )
        .scalar()
    )
    no_shows = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.assigned_driver_id == driver_id,
            Booking.status == BookingStatus.no_show,
        )
        .scalar()
    )
    avg_rating = (
        db.query(func.avg(Rating.rating_value))
        .filter(Rating.driver_id == driver_id)
        .scalar()
    )
    avg_rating = float(avg_rating) if avg_rating is not None else None

    gold_min_completed = config_service.get_int(db, "standing_gold_min_completed")
    gold_min_avg = float(config_service.get_decimal(db, "standing_gold_min_avg_rating"))
    gold_max_no_shows = config_service.get_int(db, "standing_gold_max_no_shows")
    standard_min_completed = config_service.get_int(db, "standing_standard_min_completed")

    if (
        completed >= gold_min_completed
        and no_shows <= gold_max_no_shows
        and avg_rating is not None
        and avg_rating >= gold_min_avg
    ):
        tier = StandingTier.gold
    elif completed >= standard_min_completed:
        tier = StandingTier.standard
    else:
        tier = StandingTier.new

    driver = db.get(Driver, driver_id)
    if driver is not None:
        driver.standing_tier = tier
    return tier
