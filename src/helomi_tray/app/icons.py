from enum import StrEnum
from typing import ClassVar


class AppIcon(StrEnum):
    class Start:
        STATES: ClassVar[list[str]] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        def __init__(self, state: int = 0):
            self.state = state

        def __iter__(self):
            return self

        def __next__(self) -> str:
            icon = self.STATES[self.state]
            self.state = (self.state + 1) % len(self.STATES)
            return icon

        def __str__(self) -> str:
            return next(self)

    LISTEN = "◉"
    IDLE = "○"
    MUSIC = "♫"
    PARROT = "🦜"
    PROFILE = "👤"
    TTS = "🗣️"
    QUITING = "☾"


Icon = AppIcon
