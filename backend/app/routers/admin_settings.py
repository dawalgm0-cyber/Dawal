"""Admin settings: pricing config editor, message-template editor, and admin
user management (super_admin only for mutations)."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin, require_super_admin
from app.db import get_db
from app.models import AdminUser, MessageTemplate, PricingConfig
from app.models.enums import PricingValueType
from app.schemas.admin_pages import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserPatch,
    MessageTemplateOut,
    MessageTemplatePatch,
    PricingConfigOut,
    PricingConfigPatch,
)
from app.security import hash_password
from app.services import audit

router = APIRouter(
    prefix="/api/admin", tags=["admin-settings"],
    dependencies=[Depends(get_current_admin)],
)


def _validate_value(value: str, vtype: PricingValueType) -> None:
    try:
        if vtype == PricingValueType.int:
            int(value)
        elif vtype == PricingValueType.decimal:
            Decimal(value)
        elif vtype == PricingValueType.bool:
            if value.strip().lower() not in ("true", "false", "1", "0", "yes", "no"):
                raise ValueError
    except (ValueError, InvalidOperation):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Value '{value}' is not a valid {vtype.value}.")


@router.get("/pricing-config", response_model=list[PricingConfigOut])
def get_pricing(db: Session = Depends(get_db)):
    return db.query(PricingConfig).order_by(PricingConfig.key).all()


@router.patch("/pricing-config", response_model=list[PricingConfigOut])
def patch_pricing(payload: PricingConfigPatch, db: Session = Depends(get_db),
                  admin: AdminUser = Depends(get_current_admin)):
    for key, value in payload.updates.items():
        row = db.query(PricingConfig).filter_by(key=key).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown config key: {key}")
        _validate_value(value, row.value_type)
        row.value = value
        row.updated_by_admin_id = admin.id
        row.updated_at = datetime.now(timezone.utc)
    audit.log_action(db, admin.id, "pricing_config.update", "pricing_config", None,
                     {"keys": list(payload.updates.keys())})
    db.commit()
    return db.query(PricingConfig).order_by(PricingConfig.key).all()


@router.get("/message-templates", response_model=list[MessageTemplateOut])
def get_templates(db: Session = Depends(get_db)):
    return db.query(MessageTemplate).order_by(MessageTemplate.key).all()


@router.patch("/message-templates/{key}", response_model=MessageTemplateOut)
def patch_template(key: str, payload: MessageTemplatePatch, db: Session = Depends(get_db),
                   admin: AdminUser = Depends(get_current_admin)):
    row = db.query(MessageTemplate).filter_by(key=key).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown template key: {key}")
    row.template_text = payload.template_text
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(timezone.utc)
    audit.log_action(db, admin.id, "message_template.update", "message_template", key)
    db.commit()
    return row


# --- admin users (super_admin only for create/update) --------------------

@router.get("/users", response_model=list[AdminUserOut])
def list_admins(db: Session = Depends(get_db)):
    return db.query(AdminUser).order_by(AdminUser.created_at).all()


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_admin(payload: AdminUserCreate, db: Session = Depends(get_db),
                 admin: AdminUser = Depends(require_super_admin)):
    email = payload.email.lower().strip()
    if db.query(AdminUser).filter_by(email=email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An admin with this email exists.")
    user = AdminUser(name=payload.name, email=email,
                     password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    audit.log_action(db, admin.id, "admin_user.create", "admin_user", None,
                     {"email": email, "role": payload.role.value})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_admin(user_id: int, payload: AdminUserPatch, db: Session = Depends(get_db),
                 admin: AdminUser = Depends(require_super_admin)):
    user = db.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin user not found.")
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    audit.log_action(db, admin.id, "admin_user.update", "admin_user", user_id)
    db.commit()
    return user
