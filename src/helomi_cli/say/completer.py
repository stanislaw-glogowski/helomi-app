from collections.abc import Iterable
from typing import ClassVar

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from helomi_core import Runtime


class SayCompleter(Completer):
    _REACTIONS: ClassVar[dict[str, str]] = {
        # Laughter & Humor
        "laughter": "Natural laughter / Chuckle",
        "laughing": "Laughing while speaking",
        "chuckle": "Gentle, suppressed laughter",
        "giggle": "Light, high-pitched giggle",
        "snicker": "Sly, sarcastic snicker",
        # Breathing & Pauses
        "breath": "Audible inhale / Breathy pause",
        "sigh": "Deep sigh (relief or fatigue)",
        "sighing": "Sighing tone",
        "gasp": "Sharp sudden intake of breath (shock)",
        "yawn": "Yawning / Drowsy vocal delivery",
        # Conversational & Fillers
        "uhm": "Natural vocal hesitation / Thinking pause",
        "um": "Short pause filler",
        "shh": "Hushing / Lowering volume",
        "throat-clearing": "Clearing throat before speaking",
        "cough": "Natural light cough",
        # Tone & Delivery Modulations
        "whisper": "Soft whisper delivery",
        "whispering": "Speaking entirely in a whisper",
        "groan": "Vocal groan (pain / frustration)",
        "sobbing": "Tearful / Breaking voice",
    }

    def __init__(self, runtime: Runtime | None = None) -> None:
        super().__init__()
        self._runtime = runtime

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        last_bracket_idx = text.rfind("[")
        if last_bracket_idx == -1:
            return

        query = text[last_bracket_idx + 1 :]

        if " " in query or "]" in query:
            return

        for name, meta in self._REACTIONS.items():
            if name.lower().startswith(query.lower()):
                yield Completion(
                    text=f"{name}]",
                    start_position=-len(query),
                    display=f"[{name}]",
                    display_meta=meta,
                )
