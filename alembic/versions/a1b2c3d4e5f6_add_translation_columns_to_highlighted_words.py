"""add translation columns to highlighted_words

Revision ID: a1b2c3d4e5f6
Revises: f10f35d4e2bd
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f10f35d4e2bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('highlighted_words', sa.Column('translation_target', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('highlighted_words', 'translation_target')