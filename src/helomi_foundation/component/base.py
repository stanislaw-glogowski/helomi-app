import loguru

from ..conversion import to_snake_case
from ..logger import Logger


class BaseComponent:
    """Provide a component-scoped logger and stable diagnostic name."""

    def __init__(self, logger: Logger | None = None):
        component = to_snake_case(self.__class__.__name__)

        self._logger = (
            logger
            if logger is not None
            else loguru.logger.bind(
                component=component,
                context=None,
            )
        )
        self._component_name = component
