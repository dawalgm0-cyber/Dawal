"""add drivers.pin_hash

Revision ID: 0002_driver_pin
Revises: f0bd3a08dafd
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_driver_pin"
down_revision: Union[str, None] = "f0bd3a08dafd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drivers", sa.Column("pin_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("drivers", "pin_hash")
