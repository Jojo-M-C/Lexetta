import regex

_WORD_REGEX = regex.compile(r"[\p{L}]+(?:[''\-][\p{L}]+)*")


def word_tokenize(text: str) -> list[str]:
    """
    Split `text` into word tokens.

    A token is a run of Unicode letters, optionally containing internal
    apostrophes (straight or curly) or hyphens between letter runs — e.g.
    "don't", "well-known", "Müller". Digits, punctuation, and whitespace
    are skipped, and leading/trailing apostrophes/hyphens are not included.

    Mirrors the frontend tokenizer in frontend/src/lib/tokenize.ts so the
    backend and UI agree on what counts as a word.
    """
    return [m.group(0) for m in _WORD_REGEX.finditer(text)]
