"""rename lookup_events to clicked_words

Revision ID: c37ed3f0ce82
Revises: 3125cf7322bb
Create Date: 2026-05-19 13:33:37.142455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c37ed3f0ce82'
down_revision: Union[str, Sequence[str], None] = '3125cf7322bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('lookup_events', 'clicked_words')
    op.execute('ALTER INDEX ix_lookup_events_user_id RENAME TO ix_clicked_words_user_id')
    op.execute('ALTER INDEX ix_lookup_events_document_id RENAME TO ix_clicked_words_document_id')


def downgrade() -> None:
    op.rename_table('clicked_words', 'lookup_events')
    op.execute('ALTER INDEX ix_clicked_words_user_id RENAME TO ix_lookup_events_user_id')
    op.execute('ALTER INDEX ix_clicked_words_document_id RENAME TO ix_lookup_events_document_id')
