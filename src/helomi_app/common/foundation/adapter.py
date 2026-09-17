from abc import ABC

from .component import AbstractComponent


class AbstractAdapter[TSettings](AbstractComponent, ABC):
    def __init__(self, settings: TSettings):
        super().__init__()
        self._settings = settings
