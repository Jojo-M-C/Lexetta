from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Translation:
    target: str  # German translation, e.g. "erkunden"
    source: str | None = None  # PONS sometimes returns "to explore" for "explore"
    pos: str | None = None  # part of speech: "verb", "noun", etc.
    sense_header: str | None = None  # PONS's "header" describing the sense


class Translator(ABC):
    """Abstract interface for translation backends.

    Implementations: StubTranslator (dev), PONSTranslator (real).
    Future: DeepLTranslator, LocalModelTranslator, etc.
    """

    name: str  # Provider identifier stored in the cache (e.g., "pons", "stub")

    @abstractmethod
    def translate(
            self,
            word: str,
            source_lang: str = "en",
            target_lang: str = "de",
    ) -> list[Translation]:
        """Return a list of translations. Empty list if no results."""
        ...