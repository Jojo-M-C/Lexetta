import spacy

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        # Sentence boundaries don't need parser/NER — keep this fast
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])
        _nlp.add_pipe("sentencizer")
    return _nlp


def find_sentence(text: str, word: str) -> str:
    """
    Find the sentence within `text` that contains `word`.
    Returns the matching sentence, or the full text if no sentence found.
    """
    nlp = _get_nlp()
    doc = nlp(text)

    word_lower = word.lower()
    for sent in doc.sents:
        # Match against any token's lowercased form for case-insensitive matching
        if any(t.text.lower() == word_lower for t in sent):
            return sent.text.strip()

    # Fallback: return the full text. This shouldn't happen in practice but
    # protects against edge cases (word not found, segmentation issues).
    return text.strip()