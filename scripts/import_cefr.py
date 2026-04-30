"""
One-off script to import CEFR-labeled words into the database.

Usage:
    python -m scripts.import_cefr data/cefr_words.csv

If a word appears multiple times at different levels, the easiest level wins.
Multi-form entries like "a.m./A.M./am/AM" are split into separate forms.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.lib.lemmatize import lemmatize_many
from app.models import WordCefrLevel

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}


def expand_forms(headword: str) -> list[str]:
    """Split multi-form entries: 'a.m./A.M./am/AM' -> ['a.m.', 'A.M.', 'am', 'AM']"""
    return [form.strip() for form in headword.split("/") if form.strip()]


def easier(level_a: str, level_b: str) -> str:
    """Return the easier of two CEFR levels."""
    return level_a if LEVEL_ORDER[level_a] <= LEVEL_ORDER[level_b] else level_b


def load_csv(path: Path) -> dict[str, str]:
    """
    Load CSV and return {surface_word: cefr_level}, applying:
      - multi-form expansion
      - level filtering (only A1-C2)
      - 'easier wins' on conflicts
    """
    word_to_level: dict[str, str] = {}

    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            headword = row["headword"].strip()
            level = row["CEFR"].strip().upper()

            if level not in LEVEL_ORDER:
                continue  # skip rows with unexpected levels

            for form in expand_forms(headword):
                if form in word_to_level:
                    word_to_level[form] = easier(word_to_level[form], level)
                else:
                    word_to_level[form] = level

    return word_to_level


def lemmatize_and_resolve(surface_to_level: dict[str, str]) -> dict[str, str]:
    """
    Lemmatize all surface words, collapsing multiple surface forms onto their lemma.
    On collision (different surface forms with the same lemma), keep the easier level.
    """
    surface_words = list(surface_to_level.keys())
    print(f"Lemmatizing {len(surface_words)} words...")

    # spaCy struggles with words containing slashes/dots. Lemmatize one at a time
    # to be safe. Slower but reliable for a one-off import.
    from app.lib.lemmatize import lemmatize as lemmatize_one

    lemma_to_level: dict[str, str] = {}
    for i, surface in enumerate(surface_words):
        if i % 1000 == 0 and i > 0:
            print(f"  ...{i}/{len(surface_words)}")
        lemma = lemmatize_one(surface)
        level = surface_to_level[surface]
        if lemma in lemma_to_level:
            lemma_to_level[lemma] = easier(lemma_to_level[lemma], level)
        else:
            lemma_to_level[lemma] = level

    return lemma_to_level


def import_into_db(lemma_to_level: dict[str, str]) -> int:
    """Bulk insert. Uses ON CONFLICT to handle existing rows (idempotent)."""
    rows = [
        {"word": lemma, "cefr_level": level}
        for lemma, level in lemma_to_level.items()
    ]

    db = SessionLocal()
    try:
        # Postgres ON CONFLICT (word) DO UPDATE — re-running the import overwrites
        stmt = insert(WordCefrLevel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["word"],
            set_={"cefr_level": stmt.excluded.cefr_level},
        )
        db.execute(stmt)
        db.commit()
        return len(rows)
    finally:
        db.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_cefr <path-to-csv>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Loading {path}...")
    surface_to_level = load_csv(path)
    print(f"Loaded {len(surface_to_level)} unique surface forms")

    lemma_to_level = lemmatize_and_resolve(surface_to_level)
    print(f"After lemmatization: {len(lemma_to_level)} unique lemmas")

    count = import_into_db(lemma_to_level)
    print(f"Imported {count} word entries.")

    # Summary by level
    from collections import Counter
    counts = Counter(lemma_to_level.values())
    for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        print(f"  {level}: {counts.get(level, 0)}")


if __name__ == "__main__":
    main()