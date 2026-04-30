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
    text = " ".join(w.lower() for w in words)
    doc = nlp(text)
    return [t.lemma_ for t in doc]