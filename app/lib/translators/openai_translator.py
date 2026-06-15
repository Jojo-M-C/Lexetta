import json

from openai import OpenAI

from app.lib.languages import language_name
from app.lib.translator import Translation, Translator


def _build_system_prompt(target_name: str) -> str:
    return f"""You are a translation assistant for English-to-{target_name} learners.

Given an English word and the sentence/paragraph it appears in, return ONE accurate {target_name} translation that fits the specific context.

Rules:
- Return only the most accurate single {target_name} translation for the word in this context.
- If the word is part of a fixed phrase (e.g. "Tower of London"), translate the phrase as a unit only if it makes sense; otherwise translate just the word.
- Use the most common, natural {target_name} equivalent. Avoid overly formal or archaic terms unless they fit the register.
- Return your answer as JSON with exactly this shape:

{{"target": "<{target_name} translation>"}}

Do not include explanations, alternatives, or notes."""


class OpenAITranslator(Translator):
    """Context-aware translator using OpenAI's GPT-4o mini."""

    name = "openai-gpt4o-mini"
    MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def translate(
        self,
        word: str,
        context: str,
        source_lang: str = "en",
        target_lang: str = "de",
    ) -> Translation | None:
        user_prompt = f'Word: "{word}"\nContext: "{context}"'

        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": _build_system_prompt(language_name(target_lang))},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=50,
        )

        raw = response.choices[0].message.content
        if not raw:
            return None

        try:
            data = json.loads(raw)
            target = data.get("target", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return None

        if not target:
            return None

        return Translation(target=target, source=word)