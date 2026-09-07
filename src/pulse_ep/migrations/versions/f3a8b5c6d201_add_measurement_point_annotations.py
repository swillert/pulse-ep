"""add measurement_points.annotations

Where a point's beat sits in the signal recorded for it — start of the window,
reference and mapping annotation, window of interest. The components the
activation time is derived from; they existed only in the CARTO-shaped legacy
table ``ep_map_points``, which the queue import path never writes.

Revision ID: f3a8b5c6d201
Revises: d7e2c4a9f1b6
Create Date: 2026-09-07 02:10:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a8b5c6d201"
down_revision: Union[str, Sequence[str], None] = "d7e2c4a9f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "measurement_points",
        sa.Column(
            "annotations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("measurement_points", "annotations")
