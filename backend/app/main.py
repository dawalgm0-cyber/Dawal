"""FastAPI entrypoint."""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import scheduler
from app.config import settings

from app.routers import (
    admin_analytics,
    admin_auth,
    admin_bookings,
    admin_captains,
    admin_compliance,
    admin_credits,
    admin_drivers,
    admin_reports,
    admin_riders,
    admin_settings,
    areas,
    bookings,
    claim,
    disputes,
    drivers,
)

# Ensure our app loggers (e.g. the mock SMS sender that prints OTPs in local dev)
# actually emit at INFO; uvicorn otherwise leaves the root logger at WARNING.
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
_dawal_log = logging.getLogger("dawal")
_dawal_log.setLevel(logging.INFO)
_dawal_log.addHandler(_handler)
_dawal_log.propagate = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title="DAWAL API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bookings.router)
app.include_router(areas.router)
app.include_router(claim.router)
app.include_router(drivers.router)
app.include_router(admin_auth.router)
app.include_router(admin_drivers.router)
app.include_router(admin_credits.router)
app.include_router(admin_bookings.router)
app.include_router(admin_reports.router)
app.include_router(admin_riders.router)
app.include_router(admin_analytics.router)
app.include_router(admin_compliance.router)
app.include_router(admin_settings.router)
app.include_router(admin_captains.router)
app.include_router(disputes.driver_router)
app.include_router(disputes.admin_router)

# Serve uploaded license docs (local disk MVP).
_upload_root = os.environ.get("UPLOAD_ROOT", "/app/uploads")
os.makedirs(_upload_root, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_root), name="uploads")


@app.get("/health")
def health():
    return {"status": "ok", "service": "dawal-api"}
