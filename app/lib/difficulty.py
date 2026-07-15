import time

from wordfreq import zipf_frequency
from sqlalchemy.orm import Session

from app.lib.lcp_modal import APP_NAME as LCP_APP_NAME
from app.lib.lemmatize import lemmatize_many
from app.models import (
    CalibrationItem,
    CalibrationResponse,
    ReadWord,
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
    """
    CEFR-rule difficulty: a word is difficult if its level is at or above the
    user's reading level. ML users never reach this function — the /difficulty
    endpoint routes them to difficult_words_ml instead.
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
            continue
        if LEVEL_ORDER[level] >= user_level:
            difficult.update(surfaces)

    return difficult

ML_DIFFICULTY_THRESHOLD = 0.5

class MLServiceUnavailable(Exception):
    """
    The Modal GPU service could not be reached or failed.

    Deliberately never falls back to the CEFR rule: mixing rule-based highlights
    into an ML session would pollute the logged research data. Callers surface an
    outage to the user instead.
    """


_LCP_MODAL = None  # cached instance handle for the deployed Modal class


def _lcp_predictor():
    """
    Return an instance of the deployed Modal ``LCPModel`` class.

    The model lives on a Modal GPU container (see app/lib/lcp_modal.py); we only
    hold a lightweight remote handle here. Looking it up by name requires the app
    to have been deployed (``modal deploy app/lib/lcp_modal.py``) and Modal
    credentials to be configured on this host.

    The instance is cached, not just the class: instantiating costs a hydration
    round-trip to Modal, and there is no per-call state to keep separate.
    """
    global _LCP_MODAL
    if _LCP_MODAL is None:
        import modal

        _LCP_MODAL = modal.Cls.from_name(LCP_APP_NAME, "LCPModel")()
    return _LCP_MODAL


# The per-annotator model receives the whole history alongside *every* scored
# token, so history length drives sequence length and therefore GPU time. Left
# uncapped it grows with every click and slows predictions down forever. Note
# this is also a modelling decision, not only a performance one: truncating the
# history changes what the model conditions on.
HISTORY_MAX_ENTRIES = 40


def _get_user_history(user: User, db: Session) -> list[dict]:
    """
    Build the user's difficulty history for the model, newest signals first and
    capped at HISTORY_MAX_ENTRIES.

    Calibration ratings are kept unconditionally: they are explicit ground truth
    the user gave us, and there are only ever 18 of them. The remaining budget is
    filled with the most recent behavioural signals, deduplicated by word.
    """
    # Explicit difficulty ratings from the onboarding calibration sequence.
    # difficulty_rating is 1–5; map it onto the same 0–1 complexity scale.
    calibration = (
        db.query(CalibrationItem.word, CalibrationResponse.difficulty_rating)
        .join(CalibrationResponse, CalibrationResponse.item_id == CalibrationItem.id)
        .filter(CalibrationResponse.user_id == user.id)
        .all()
    )
    history = [
        {"token": row.word, "complexity": (row.difficulty_rating - 1) / 4}
        for row in calibration
    ]
    seen = {entry["token"].lower() for entry in history}

    budget = HISTORY_MAX_ENTRIES - len(history)
    if budget <= 0:
        return history

    # Both signals come from read_words, so only words on a page the user
    # demonstrably read count. A word the user clicked is a stronger difficulty
    # signal (0.75) than one that was highlighted as difficult yet read and ignored
    # (0.25). Over-fetch to `budget` from each source, then interleave by recency
    # and take what fits.
    clicked = (
        db.query(ReadWord.word, ReadWord.created_at)
        .filter(ReadWord.user_id == user.id, ReadWord.was_clicked.is_(True))
        .order_by(ReadWord.created_at.desc())
        .limit(budget)
        .all()
    )
    highlighted_not_clicked = (
        db.query(ReadWord.word, ReadWord.created_at)
        .filter(
            ReadWord.user_id == user.id,
            ReadWord.was_clicked.is_(False),
            ReadWord.was_highlighted.is_(True),
        )
        .order_by(ReadWord.created_at.desc())
        .limit(budget)
        .all()
    )
    recent = sorted(
        [(row.created_at, row.word, 0.75) for row in clicked]
        + [(row.created_at, row.word, 0.25) for row in highlighted_not_clicked],
        key=lambda entry: entry[0],
        reverse=True,
    )

    for _, word, complexity in recent:
        if len(history) >= HISTORY_MAX_ENTRIES:
            break
        if word.lower() in seen:
            continue
        seen.add(word.lower())
        history.append({"token": word, "complexity": complexity})

    return history


def difficult_words_ml(
    sentences: list[str],
    tokens: list[str],
    history: list[dict],
) -> set[str]:
    """
    ML-based variant of difficult_words. Predicts per-token complexity with the
    per-annotator LCP model and returns tokens scoring at or above the threshold.

    `sentences` and `tokens` must be parallel: each token is scored in the
    context of the sentence at the same index.

    `history` (from `_get_user_history`) is passed in rather than read here, so the
    caller can release its database connection before this multi-second remote call.
    This function touches no database. See notes/multi_user_performance.md §3/§5.
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
        started = time.perf_counter()
        try:
            # Covers a missing/failed lookup (bad Modal credentials, app not
            # deployed) as well as the call itself timing out or erroring.
            preds_list = _lcp_predictor().predict.remote(ml_sentences, ml_words, history)
        except Exception as e:
            raise MLServiceUnavailable(str(e)) from e
        # Compare against the container-side "[lcp] predict" line: the difference
        # is cold start + queueing + network, not model time.
        print(
            f"[lcp] remote round-trip {time.perf_counter() - started:.2f}s  "
            f"gated={len(ml_words)}/{len(tokens)} tokens  history={len(history)}"
        )
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
