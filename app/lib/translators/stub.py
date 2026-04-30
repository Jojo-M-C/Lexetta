from app.lib.translator import Translation, Translator


class StubTranslator(Translator):
    """Returns fake translations. For development only."""

    name = "stub"

    def translate(
        self,
        word: str,
        source_lang: str = "en",
        target_lang: str = "de",
    ) -> list[Translation]:
        # Return 2-3 fake translations to mimic the shape of real responses
        return [
            Translation(
                target=f"[DE] {word}",
                source=word,
                pos="noun",
                sense_header="primary sense",
            ),
            Translation(
                target=f"[DE alt] {word}",
                source=word,
                pos="verb",
                sense_header="alternate sense",
            ),
        ]