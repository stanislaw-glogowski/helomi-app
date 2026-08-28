from abc import ABC

from .component import AbstractComponent


class AbstractAdapter[TConfig](AbstractComponent, ABC):
    def __init__(self, config: TConfig) -> None:
        super().__init__()
        self._config = config
