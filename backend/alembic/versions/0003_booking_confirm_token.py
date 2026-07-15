"""add bookings.confirm_token

Revision ID: 0003_confirm_token
Revises: 0002_driver_pin
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_confirm_token"
down_revision: Union[str, None] = "0002_driver_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("confirm_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "confirm_token")
