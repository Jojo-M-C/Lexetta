"""seed test users

Revision ID: 66d82e07ba17
Revises: 52cfc1bf26de
Create Date: 2026-04-29 10:15:20.398032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66d82e07ba17'
down_revision: Union[str, Sequence[str], None] = '52cfc1bf26de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(
        sa.table(
            "users",
            sa.column("username", sa.String),
            sa.column("reading_level", sa.String),
            sa.column("use_ml_predictions", sa.Boolean),
        ),
        [
            {"username": "learner_a1", "reading_level": "A1", "use_ml_predictions": False},
            {"username": "learner_a2", "reading_level": "A2", "use_ml_predictions": False},
            {"username": "learner_b1", "reading_level": "B1", "use_ml_predictions": False},
            {"username": "learner_b2", "reading_level": "B2", "use_ml_predictions": False},
            {"username": "learner_c1", "reading_level": "C1", "use_ml_predictions": False},
            {"username": "learner_c2", "reading_level": "C2", "use_ml_predictions": False},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM users WHERE username LIKE 'learner_%'")
