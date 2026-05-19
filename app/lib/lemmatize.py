import spacy

_nlp = None


def _get_nlp():
    """Lazy-load spaCy. Avoids loading on import (slow startup)."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
    return _nlp


def lemmatize(word: str) -> str:
    """Lemmatize a single word (lowercased)."""
    doc = _get_nlp()(word.lower())
    return doc[0].lemma_ if len(doc) > 0 else word.lower()


def lemmatize_many(words: list[str]) -> list[str]:
    """Lemmatize many words at once. More efficient than calling lemmatize() in a loop."""
    nlp = _get_nlp()
    # Process each word as its own document so hyphenated tokens (e.g. "one-bedroom")
    # don't expand into multiple spaCy tokens and misalign the zip in callers.
    return [
        doc[0].lemma_ if len(doc) > 0 else word.lower()
        for word, doc in zip(words, nlp.pipe(w.lower() for w in words))
    ]