from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Area
from app.schemas.booking import AreaOut

router = APIRouter(prefix="/api/areas", tags=["areas"])


@router.get("", response_model=list[AreaOut])
def list_areas(db: Session = Depends(get_db)):
    return db.query(Area).order_by(Area.name).all()
