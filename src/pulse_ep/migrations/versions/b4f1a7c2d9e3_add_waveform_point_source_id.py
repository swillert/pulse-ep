"""add waveforms.point_source_id

CARTO exports one signal window per acquired point, so a stored waveform has
a point it belongs to. EnSite X exports per segment and leaves it NULL.

Revision ID: b4f1a7c2d9e3
Revises: 0c2994f1da5b
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4f1a7c2d9e3"
down_revision: Union[str, Sequence[str], None] = "0c2994f1da5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("waveforms", sa.Column("point_source_id", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_waveforms_point_source_id"), "waveforms", ["point_source_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_waveforms_point_source_id"), table_name="waveforms")
    op.drop_column("waveforms", "point_source_id")
