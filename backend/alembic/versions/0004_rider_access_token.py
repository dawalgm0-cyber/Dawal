"""add bookings.rider_access_token

Revision ID: 0004_rider_token
Revises: 0003_confirm_token
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_rider_token"
down_revision: Union[str, None] = "0003_confirm_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("rider_access_token", sa.String(), nullable=True))
    op.create_index(op.f("ix_bookings_rider_access_token"), "bookings",
                    ["rider_access_token"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bookings_rider_access_token"), table_name="bookings")
    op.drop_column("bookings", "rider_access_token")
