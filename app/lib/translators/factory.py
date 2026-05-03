from app.config import settings
from app.lib.translator import Translator
from app.lib.translators.openai_translator import OpenAITranslator


def get_translator() -> Translator:
    """Return the active translator. Currently OpenAI only."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file."
        )
    return OpenAITranslator(api_key=settings.openai_api_key)