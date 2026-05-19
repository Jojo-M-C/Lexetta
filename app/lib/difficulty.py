from sqlalchemy.orm import Session

from app.lib.lemmatize import lemmatize_many
from app.models import User, WordCefrLevel

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}

def difficult_words(words: list[str], user: User, db: Session) -> set[str]:
    if user.use_ml_predictions:
        result = difficult_words_ml(words, user, db)
        return result if result is not None else set()

    if not user.reading_level or user.reading_level not in LEVEL_ORDER:
        return set()
    user_level = LEVEL_ORDER[user.reading_level]

    if not words:
        return set()

    # Lemmatize once for the whole batch
    lemmas = lemmatize_many(words)
    surface_by_lemma: dict[str, list[str]] = {}
    for surface, lemma in zip(words, lemmas):
        surface_by_lemma.setdefault(lemma, []).append(surface.lower())

    unique_lemmas = list(surface_by_lemma.keys())

    # Single query for all lemmas
    rows = (
        db.query(WordCefrLevel)
        .filter(WordCefrLevel.word.in_(unique_lemmas))
        .all()
    )
    lemma_to_level = {row.word: row.cefr_level for row in rows}

    difficult: set[str] = set()
    for lemma, surfaces in surface_by_lemma.items():
        level = lemma_to_level.get(lemma)
        if level is None:
            continue
        if LEVEL_ORDER[level] >= user_level:
            difficult.update(surfaces)

    return difficult

# TODO future ML integration
def difficult_words_ml(words, user, db):
    return
