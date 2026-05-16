import threading
import torch
from lexetta_lcp.CompLexPerAnnotator.model import load_trained
from sqlalchemy.orm import Session

from app.config import settings
from app.lib.lemmatize import lemmatize_many
from app.models import User, WordCefrLevel

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
_load_lock = threading.Lock()
_LCP_MODEL = None # stores (model, tokenizer)


def difficult_words(words: list[str], user: User, db: Session) -> set[str]:
    """
    Given a list of words and a user, return the set of words that are
    difficult for that user (lowercased surface forms).

    A word is difficult if its CEFR level is at or above the user's
    reading level. Words not in the dataset are treated as easy by default.
    Users without a reading level get an empty result (nothing highlighted).
    """
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
            continue  # not in dataset → treat as easy
        if LEVEL_ORDER[level] >= user_level:
            difficult.update(surfaces)

    return difficult

ML_DIFFICULTY_THRESHOLD = 0.5


def _load_lcp_model():
    global _LCP_MODEL
    with _load_lock:
        if _LCP_MODEL is not None:
            return _LCP_MODEL

        model, tokenizer = load_trained(settings.lcp_model_dir)
        if torch.cuda.is_available():
            model = model.to("cuda")
        _LCP_MODEL = model, tokenizer
        return _LCP_MODEL


def _get_user_history(user: User, db: Session) -> list[dict]:
    # TODO: build the user's history from their lookup / vocabulary events.
    return []


def difficult_words_ml(
    sentences: list[str],
    tokens: list[str],
    user: User,
    db: Session,
) -> set[str]:
    """
    ML-based variant of difficult_words. Predicts per-token complexity with the
    per-annotator LCP model and returns tokens scoring at or above the threshold.

    `sentences` and `tokens` must be parallel: each token is scored in the
    context of the sentence at the same index.
    """
    if len(sentences) != len(tokens):
        raise ValueError(
            f"sentences and tokens must have the same length "
            f"(got {len(sentences)} and {len(tokens)})"
        )
    if not tokens:
        return set()

    from lexetta_lcp.CompLexPerAnnotator.model import predict_batch

    model, tokenizer = _load_lcp_model()
    histories = [_get_user_history(user, db)] * len(tokens)

    preds = predict_batch(model, tokenizer, sentences, tokens, histories)

    return {
        token.lower()
        for token, score in zip(tokens, preds)
        if score >= ML_DIFFICULTY_THRESHOLD
    }
