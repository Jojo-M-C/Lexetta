"""add mode to read_words

Revision ID: c4e8a2f60b17
Revises: b3d7f1a29c04
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a2f60b17'
down_revision: Union[str, Sequence[str], None] = 'b3d7f1a29c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('read_words', sa.Column('mode', sa.String(length=8), nullable=True))
    # Backfill the mode of existing highlighted rows from the highlight they link to.
    # Rows never highlighted stay NULL (no model flagged them and the active mode
    # at read time wasn't recorded before this column existed).
    op.execute(
        """
        UPDATE read_words r
        SET mode = h.mode
        FROM highlighted_words h
        WHERE r.highlighted_word_id = h.id
          AND r.mode IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('read_words', 'mode')
