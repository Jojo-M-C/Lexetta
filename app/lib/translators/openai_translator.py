import json

from openai import OpenAI

from app.lib.translator import Translation, Translator


SYSTEM_PROMPT = """You are a translation assistant for English-to-German learners.

Given an English word and the sentence/paragraph it appears in, return ONE accurate German translation that fits the specific context.

Rules:
- Return only the most accurate single German translation for the word in this context.
- If the word is part of a fixed phrase (e.g. "Tower of London"), translate the phrase as a unit only if it makes sense; otherwise translate just the word.
- Use the most common, natural German equivalent. Avoid overly formal or archaic terms unless they fit the register.
- Return your answer as JSON with exactly this shape:

{"target": "<german translation>"}

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
                {"role": "system", "content": SYSTEM_PROMPT},
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