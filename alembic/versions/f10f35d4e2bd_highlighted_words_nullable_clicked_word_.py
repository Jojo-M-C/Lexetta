"""highlighted_words nullable clicked_word_id and add was_clicked bool

Revision ID: f10f35d4e2bd
Revises: d356ae19fb20
Create Date: 2026-05-19 14:15:40.268313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f10f35d4e2bd'
down_revision: Union[str, Sequence[str], None] = 'd356ae19fb20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('highlighted_words', 'clicked_word_id', nullable=True)
    op.add_column('highlighted_words', sa.Column('was_clicked', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('highlighted_words', 'was_clicked')
    op.alter_column('highlighted_words', 'clicked_word_id', nullable=False)
