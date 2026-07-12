"""replace clicked_words with read_words

Revision ID: b3d7f1a29c04
Revises: f2a3b4c5d6e7
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d7f1a29c04'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # highlighted_words.clicked_word_id FK'd into clicked_words; drop it before
    # the table it references. was_clicked already records the click relationship,
    # and read_words.highlighted_word_id gives the reverse link.
    op.drop_constraint('highlighted_words_clicked_word_id_fkey', 'highlighted_words', type_='foreignkey')
    op.drop_column('highlighted_words', 'clicked_word_id')

    op.drop_table('clicked_words')

    op.create_table(
        'read_words',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('paragraph_id', sa.Integer(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('word', sa.String(length=128), nullable=False),
        sa.Column('context', sa.Text(), nullable=False),
        sa.Column('was_clicked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('was_highlighted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('highlighted_word_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paragraph_id'], ['paragraphs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['highlighted_word_id'], ['highlighted_words.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'document_id', 'page_number', 'word', name='uq_read_user_doc_page_word'),
    )
    op.create_index(op.f('ix_read_words_document_id'), 'read_words', ['document_id'], unique=False)
    op.create_index(op.f('ix_read_words_user_id'), 'read_words', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_read_words_user_id'), table_name='read_words')
    op.drop_index(op.f('ix_read_words_document_id'), table_name='read_words')
    op.drop_table('read_words')

    op.create_table(
        'clicked_words',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('paragraph_id', sa.Integer(), nullable=True),
        sa.Column('word', sa.String(length=128), nullable=False),
        sa.Column('context', sa.Text(), nullable=False),
        sa.Column('was_highlighted', sa.Boolean(), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paragraph_id'], ['paragraphs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_clicked_words_document_id'), 'clicked_words', ['document_id'], unique=False)
    op.create_index(op.f('ix_clicked_words_user_id'), 'clicked_words', ['user_id'], unique=False)

    op.add_column('highlighted_words', sa.Column('clicked_word_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'highlighted_words_clicked_word_id_fkey', 'highlighted_words', 'clicked_words',
        ['clicked_word_id'], ['id'], ondelete='SET NULL',
    )
