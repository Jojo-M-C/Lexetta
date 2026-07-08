from wordfreq import zipf_frequency
from sqlalchemy.orm import Session

from app.lib.lcp_modal import APP_NAME as LCP_APP_NAME
from app.lib.lemmatize import lemmatize_many
from app.models import (
    CalibrationItem,
    CalibrationResponse,
    ClickedWord,
    HighlightedWord,
    User,
    WordCefrLevel,
)

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
BASIC_WORD_THRESHOLD = 6 # only do ml predictions for words with lower than threshold frequency. all other words are instantly marked as simple (complexity 0) to safe compute



def is_frequent_word(word: str, threshold: float) -> bool:
    """
    Return True if `word`'s Zipf frequency is strictly higher than `threshold`.

    Frequency comes from the `wordfreq` package, whose English wordlist is
    built from SUBTLEX (among other sources). The Zipf scale runs ~1–7 on a
    log scale: ~3 is rare, ~6 is very common (e.g. "the" ≈ 7.7). Unknown words
    score 0.0.
    """
    return zipf_frequency(word.lower(), "en") > threshold


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

ML_DIFFICULTY_THRESHOLD = 0.5

_LCP_MODAL = None  # cached handle to the deployed Modal class


def _lcp_predictor():
    """
    Return an instance of the deployed Modal ``LCPModel`` class.

    The model lives on a Modal GPU container (see app/lib/lcp_modal.py); we only
    hold a lightweight remote handle here. Looking it up by name requires the app
    to have been deployed (``modal deploy app/lib/lcp_modal.py``) and Modal
    credentials to be configured on this host.
    """
    global _LCP_MODAL
    if _LCP_MODAL is None:
        import modal

        _LCP_MODAL = modal.Cls.from_name(LCP_APP_NAME, "LCPModel")
    return _LCP_MODAL()


def _get_user_history(user: User, db: Session) -> list[dict]:
    highlighted_not_clicked = (
        db.query(HighlightedWord.word)
        .filter(
            HighlightedWord.user_id == user.id,
            HighlightedWord.was_clicked.is_(False),
        )
        .all()
    )
    clicked = (
        db.query(ClickedWord.word)
        .filter(ClickedWord.user_id == user.id)
        .all()
    )
    # Explicit difficulty ratings from the onboarding calibration sequence.
    # difficulty_rating is 1–5; map it onto the same 0–1 complexity scale.
    calibration = (
        db.query(CalibrationItem.word, CalibrationResponse.difficulty_rating)
        .join(CalibrationResponse, CalibrationResponse.item_id == CalibrationItem.id)
        .filter(CalibrationResponse.user_id == user.id)
        .all()
    )
    return [
        {"token": row.word, "complexity": 0.25} for row in highlighted_not_clicked
    ] + [
        {"token": row.word, "complexity": 0.75} for row in clicked
    ] + [
        {"token": row.word, "complexity": (row.difficulty_rating - 1) / 4}
        for row in calibration
    ]


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

    # only run the ML model on rare words; frequent words are instantly "easy"
    ml_indices = [i for i, t in enumerate(tokens) if not is_frequent_word(t, BASIC_WORD_THRESHOLD)]

    # do ml prediction for the remaining words, keyed by their original token index
    ml_words = [tokens[i] for i in ml_indices]
    ml_sentences = [sentences[i] for i in ml_indices]

    ml_preds = {}
    if ml_words:
        # The history is the same for every token, so send it once and let the
        # Modal container fan it out (see LCPModel.predict).
        history = _get_user_history(user, db)
        preds_list = _lcp_predictor().predict.remote(ml_sentences, ml_words, history)
        ml_preds = dict(zip(ml_indices, preds_list))

    # the result list contains the prediction for each input token. if there is no ml prediction
    # the word was basic and therefore is assigned a complexity of 0
    scores = [ml_preds.get(i, 0) for i in range(len(tokens))]

    # TODO: it is better to return the scores as they are because the same token can be complex in a different context
    res = {tokens[i]
        for i, s in enumerate(scores)
        if s >= ML_DIFFICULTY_THRESHOLD
    }
    return res
