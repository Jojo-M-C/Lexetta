from app.lib.translator import Translator
from app.lib.translators.stub import StubTranslator


def get_translator() -> Translator:
    """Return the active translator. For now: always stub."""
    return StubTranslator()