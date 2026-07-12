import re
import spacy

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    return _nlp


def _letters(s: str) -> str:
    """Lowercase, letters only. Lets matching survive punctuation and the
    inconsistent word spacing that PDF text extraction sometimes produces."""
    return re.sub(r"[^a-z]", "", s.lower())


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences, dropping blanks. Used to build the parallel
    sentence/token lists the per-token ML complexity model expects."""
    doc = _get_nlp()(text)
    return [s for sent in doc.sents if (s := sent.text.strip())]


def split_sentences_many(texts: list[str]) -> list[list[str]]:
    """Sentence-split several texts at once, one result list per input.

    spaCy's `pipe` batches the work, which matters on the difficulty path where
    a whole page's worth of blocks is segmented per request.
    """
    if not texts:
        return []
    return [
        [s for sent in doc.sents if (s := sent.text.strip())]
        for doc in _get_nlp().pipe(texts)
    ]


def map_words_to_sentences(text: str, words: list[str]) -> dict[str, str]:
    """For each word in `words`, return the first sentence of `text` that contains
    it (letters-only match, like `find_sentence`), falling back to the word itself.

    Segments `text` once and scans it per word, so a whole page's worth of words
    can be given a sentence context without re-segmenting on every lookup — used by
    the page-read commit for pdf pages, which have no paragraph rows.
    """
    sentences = split_sentences(text)
    letters_by_sentence = [(s, _letters(s)) for s in sentences]
    result: dict[str, str] = {}
    for word in words:
        target = _letters(word)
        match = word.strip()
        if target:
            for sentence, letters in letters_by_sentence:
                if target in letters:
                    match = sentence
                    break
        result[word] = match
    return result


def find_sentence(text: str, word: str) -> str:
    """
    Return the sentence within `text` that contains `word`.

    If the word can't be located we deliberately return just the word, never the
    whole text: a clicked word should only ever pull its own sentence into a
    vocabulary card. (PDF page text is the entire page, so the old "return the
    full text" fallback dumped the whole page.)
    """
    word_lower = word.lower()
    target = _letters(word)
    if not target:
        return word.strip()

    nlp = _get_nlp()
    doc = nlp(text)

    fuzzy_match: str | None = None
    for sent in doc.sents:
        # Precise: an exact token match (well-tokenised text, e.g. the txt reader).
        if any(tok.text.lower() == word_lower for tok in sent):
            return sent.text.strip()
        # Fallback: a letters-only substring match handles punctuation and the
        # spacing quirks of PDF text where the word isn't its own token. Keep the
        # first such sentence, but an exact match anywhere still wins over it.
        if fuzzy_match is None and target in _letters(sent.text):
            fuzzy_match = sent.text.strip()

    if fuzzy_match is not None:
        return fuzzy_match

    # Word not found at all — add the word only, never the whole text.
    return word.strip()