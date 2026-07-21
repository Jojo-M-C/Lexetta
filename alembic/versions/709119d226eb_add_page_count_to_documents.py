"""add page_count to documents

Revision ID: 709119d226eb
Revises: c0e9eeac7d91
Create Date: 2026-07-21 14:41:15.628739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '709119d226eb'
down_revision: Union[str, Sequence[str], None] = 'c0e9eeac7d91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))

    # Backfill txt/epub from their page rows. PDFs have none, so they stay NULL
    # and are filled in below; anything still NULL simply shows no progress bar.
    op.execute(
        """
        UPDATE documents d
        SET page_count = (SELECT count(*) FROM pages p WHERE p.document_id = d.id)
        WHERE d.source_format IN ('txt', 'epub')
        """
    )

    # PDFs: the count only exists inside the file, so open each one. Best-effort —
    # a missing or unreadable file leaves page_count NULL rather than failing the
    # migration, since a progress bar is not worth blocking a deploy over.
    conn = op.get_bind()
    pdfs = conn.execute(
        sa.text("SELECT id, file_path FROM documents WHERE source_format = 'pdf'")
    ).fetchall()
    if pdfs:
        import pdfplumber

        for doc_id, file_path in pdfs:
            try:
                with pdfplumber.open(file_path) as pdf:
                    count = len(pdf.pages)
            except Exception:
                continue
            conn.execute(
                sa.text("UPDATE documents SET page_count = :c WHERE id = :i"),
                {"c": count, "i": doc_id},
            )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "page_count")
