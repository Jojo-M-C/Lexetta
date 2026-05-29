"""seed_calibration_items

Revision ID: c8ffc9118f9b
Revises: 2d5794db0de0
Create Date: 2026-05-29 11:43:59.825794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8ffc9118f9b'
down_revision: Union[str, Sequence[str], None] = '2d5794db0de0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ITEMS = [
    # A1
    ("book",    "She left her book on the kitchen table.",                                          "A1"),
    ("walk",    "We went for a walk in the park after dinner.",                                     "A1"),
    ("happy",   "The children were happy to see the snow outside.",                                 "A1"),
    # A2
    ("decide",  "She had to decide which path to take at the crossroads.",                          "A2"),
    ("explain", "Can you explain what you mean by that?",                                           "A2"),
    ("improve", "He practised every day because he wanted to improve his skills.",                  "A2"),
    # B1
    ("enormous","The enormous building cast a long shadow over the street below.",                  "B1"),
    ("struggle","She had to struggle to keep her balance on the icy pavement.",                     "B1"),
    ("encourage","His friends encouraged him to apply for the job even though he was nervous.",     "B1"),
    # B2
    ("ambiguous","The wording of the contract was ambiguous and open to more than one interpretation.", "B2"),
    ("persist", "Despite the setbacks, she decided to persist with her research.",                  "B2"),
    ("subtle",  "There was a subtle change in his tone that suggested he was not entirely honest.", "B2"),
    # C1
    ("eloquent","The professor gave an eloquent speech about the nature of justice.",               "C1"),
    ("volatile","The political situation in the region remained volatile throughout the year.",     "C1"),
    ("pragmatic","A pragmatic approach was needed to resolve the long-standing dispute.",           "C1"),
    # C2
    ("ephemeral","The artist was drawn to ephemeral forms such as sand sculptures and ice carvings.", "C2"),
    ("obfuscate","The dense legal language seemed designed to obfuscate rather than clarify the terms.", "C2"),
    ("recalcitrant","The recalcitrant student refused to follow any of the classroom rules.",       "C2"),
]


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "calibration_items",
            sa.column("word",       sa.String),
            sa.column("sentence",   sa.Text),
            sa.column("cefr_level", sa.String),
        ),
        [{"word": w, "sentence": s, "cefr_level": l} for w, s, l in ITEMS],
    )


def downgrade() -> None:
    op.execute("DELETE FROM calibration_items")