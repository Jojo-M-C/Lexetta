"""The set of target languages a user can pick for translations.

Single source of truth: the dropdown on the language-selection screen is fed
from here (via GET /languages), and the translator looks up the English name
to build its prompt. Keep codes ISO 639-1 so they read naturally as a label.
"""

# code -> English name (used in the translation prompt and the dropdown label)
TARGET_LANGUAGES: dict[str, str] = {
    "ar": "Arabic",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "et": "Estonian",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "hu": "Hungarian",
    "it": "Italian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "es": "Spanish",
    "sv": "Swedish",
    "tr": "Turkish",
    "uk": "Ukrainian",
}

DEFAULT_LANGUAGE = "de"


def language_name(code: str) -> str:
    """English name for a language code, falling back to the default's name."""
    return TARGET_LANGUAGES.get(code, TARGET_LANGUAGES[DEFAULT_LANGUAGE])