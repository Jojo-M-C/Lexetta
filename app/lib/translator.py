from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Translation:
    target: str  # the German translation
    source: str | None = None  # optional — original word as the model interpreted it


class Translator(ABC):
    """Abstract interface for translation backends.

    A translator returns a single best translation for a word in context,
    or None if no translation is available.
    """

    name: str

    @abstractmethod
    def translate(
            self,
            word: str,
            context: str,
            source_lang: str = "en",
            target_lang: str = "de",
    ) -> Translation | None:
        """Return one translation for the word in its context, or None."""
        ...