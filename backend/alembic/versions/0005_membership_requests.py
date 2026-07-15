"""add membership_requests

Revision ID: 0005_membership_requests
Revises: 0004_rider_token
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_membership_requests"
down_revision: Union[str, None] = "0004_rider_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # topupstatus + paymentmethod enums already exist (created in 0001); reuse
    # them without re-creating the type.
    op.create_table(
        "membership_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("amount_gmd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("payment_method",
                  postgresql.ENUM(name="paymentmethod", create_type=False),
                  nullable=False),
        sa.Column("reference_number", sa.String(), nullable=True),
        sa.Column("proof_url", sa.String(), nullable=True),
        sa.Column("status",
                  postgresql.ENUM(name="topupstatus", create_type=False),
                  nullable=False),
        sa.Column("reviewed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"],
                                name=op.f("fk_membership_requests_driver_id_drivers")),
        sa.ForeignKeyConstraint(["reviewed_by_admin_id"], ["admin_users.id"],
                                name=op.f("fk_membership_requests_reviewed_by_admin_id_admin_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_requests")),
    )
    op.create_index(op.f("ix_membership_requests_status"), "membership_requests",
                    ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_membership_requests_status"), table_name="membership_requests")
    op.drop_table("membership_requests")
