"""add waveforms.units

The unit of every channel, parallel to ``channels``. It could stay a
convention while the store held only electrograms, which are all millivolts.
It cannot once EnSite X's per-timepoint exports live here too: one
``Contact_Force_Computed`` file carries force in grams, angles in degrees and
cavity distances in millimetres, and a magnetic location export puts a
dimensionless quaternion beside a translation in mm.

Additive. Rows written before this read back as ``unknown`` per channel,
which is what they always meant — the value was simply not recorded.

Revision ID: a1c3e5f70b92
Revises: f3a8b5c6d201
Create Date: 2026-09-07 17:40:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c3e5f70b92"
down_revision: Union[str, Sequence[str], None] = "f3a8b5c6d201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "waveforms",
        sa.Column(
            "units",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("waveforms", "units")
