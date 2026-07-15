from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin
from app.db import get_db
from app.models import AdminUser
from app.schemas.admin import LoginRequest, TokenResponse
from app.security import verify_password

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter_by(email=payload.email.lower().strip()).one_or_none()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return TokenResponse(
        access_token=create_access_token(admin), role=admin.role.value, name=admin.name
    )


@router.post("/logout")
def logout(admin: AdminUser = Depends(get_current_admin)):
    # Stateless JWT: the client discards the token. Endpoint exists for symmetry
    # and to require a valid token to call it.
    return {"status": "ok"}
