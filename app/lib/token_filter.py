"""Filter out tokens that should never be sent to the difficulty predictors.

Names, URLs, emails and the like are not vocabulary a learner needs help with,
yet the ML model happily scores rare capitalised tokens as "difficult" and
highlights them. This module produces the word tokens worth predicting on, so the
CEFR rule and the ML model only ever see real vocabulary.

The heuristics are deliberately simple (no NER / sentence model, so the fast CEFR
path stays spaCy-free):
  * URLs, emails and bare domains are stripped from the text before tokenising,
    so their letter fragments ("https", "www", "com") never become tokens.
  * A capitalised token that is not at the start of its sentence is treated as a
    proper noun (person, place, brand, acronym) and dropped. Sentence-initial
    capitals are ordinary words and kept — the cost is that a name at the very
    start of a sentence slips through.
"""

import re
import regex

# URLs (with scheme or leading www.), emails, and bare domains ending in a common
# TLD. Matched greedily and replaced with a space before tokenising.
_URL_EMAIL_RE = re.compile(
    r"""(?:https?://|www\.)\S+                 # scheme:// or www. URLs
        | [^\s@]+@[^\s@]+\.[^\s@]+             # email addresses
        | \b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|edu|gov|io|co|uk|de|at|ch|info|dev)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Same token shape as app/lib/tokenize.word_tokenize: letter runs with internal
# apostrophes/hyphens.
_WORD_RE = regex.compile(r"[\p{L}]+(?:['’\-][\p{L}]+)*")

# Anything that ends a sentence, so the next word counts as sentence-initial.
_SENTENCE_END_RE = re.compile(r"[.!?…:;\n\r]")


def strip_urls(text: str) -> str:
    """Remove URLs, emails and bare domains so they can't become word tokens."""
    return _URL_EMAIL_RE.sub(" ", text)


def _looks_like_name(token: str, sentence_initial: bool) -> bool:
    """Capitalised away from a sentence start → treat as a proper noun."""
    return not sentence_initial and token[0].isupper()


def predictable_tokens(text: str) -> list[str]:
    """Word tokens of `text` worth sending to a difficulty predictor.

    URLs/emails removed and proper nouns dropped. Handles multi-sentence input
    (e.g. a whole paragraph): sentence starts are found by punctuation.
    """
    cleaned = strip_urls(text)
    tokens: list[str] = []
    sentence_initial = True
    last_end = 0
    for m in _WORD_RE.finditer(cleaned):
        # A sentence-ending mark since the previous token starts a new sentence.
        if _SENTENCE_END_RE.search(cleaned, last_end, m.start()):
            sentence_initial = True
        token = m.group(0)
        if not _looks_like_name(token, sentence_initial):
            tokens.append(token)
        sentence_initial = False
        last_end = m.end()
    return tokens
