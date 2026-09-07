"""add measurement_points.tags

A point can carry operator / system markers — CARTO's ``Location Only``,
``Scar`` or a study's own labels — which say what the point was meant for
rather than what it measured. Kept beside the open ``measurements`` map as
an open list of the vendor's tag names.

Revision ID: d7e2c4a9f1b6
Revises: b4f1a7c2d9e3
Create Date: 2026-09-07 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7e2c4a9f1b6"
down_revision: Union[str, Sequence[str], None] = "b4f1a7c2d9e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "measurement_points",
        sa.Column(
            "tags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("measurement_points", "tags")
