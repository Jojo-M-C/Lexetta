"""last_page_read zero means never opened

Revision ID: 5a97c1e5f1d1
Revises: 709119d226eb
Create Date: 2026-07-21 14:46:12.262485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a97c1e5f1d1'
down_revision: Union[str, Sequence[str], None] = '709119d226eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("documents", "last_page_read", server_default="0")

    # Existing rows sitting at 1 are ambiguous: the old default was 1, so they are
    # either never-opened or opened-on-page-1, and nothing distinguishes the two.
    # Reset them to 0 — understating progress by one page is harmless, whereas
    # leaving them would keep showing progress for documents nobody has opened.
    op.execute("UPDATE documents SET last_page_read = 0 WHERE last_page_read = 1")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE documents SET last_page_read = 1 WHERE last_page_read = 0")
    op.alter_column("documents", "last_page_read", server_default="1")
