import asyncio
from abc import ABC
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
    suppress,
)
from types import TracebackType
from typing import ClassVar, Self, final

import loguru

from ..conversion import to_snake_case


class BaseComponent:
    __label__: ClassVar[str] = ""
    __component__: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        cls.__label__ = cls.__dict__.get("__label__") or to_snake_case(cls.__name__)
        cls.__component__ = cls.__name__

    def __init__(self):
        self._logger = loguru.logger.bind(
            component=self.__component__,
            context=None,
        )


class AbstractComponent(AbstractContextManager, BaseComponent, ABC):
    def __init__(self, is_quiet=False) -> None:
        super().__init__()
        self._is_open = False
        self._is_quiet = is_quiet

    @final
    def __enter__(self) -> Self:
        self.open()
        return self

    @final
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self.close()

    @final
    def open(self) -> None:
        if self._is_open:
            raise RuntimeError(f"{self.__component__} is already open")

        try:
            self._do_open()
            self._is_open = True
            if not self._is_quiet:
                self._logger.debug("OPENED")
        except BaseException as err:
            self.__close(True)
            raise err

    @final
    def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        self.__close()
        if not self._is_quiet:
            self._logger.debug("CLOSED")

    @final
    def __close(self, silent=False) -> None:
        try:
            self._do_close()
        except BaseException as err:
            if not silent:
                self._logger.warning("Error while closing: {}", err)

    def _require_open(self) -> None:
        if not self._is_open:
            raise RuntimeError(f"{self.__component__} is not open")

    def _do_open(self) -> None:
        pass

    def _do_close(self) -> None:
        pass


class AbstractAsyncComponent(AbstractAsyncContextManager, BaseComponent, ABC):
    def __init__(self, is_quiet=False) -> None:
        super().__init__()
        self._is_open = False
        self._is_quiet = is_quiet
        self._exit_signal = asyncio.Event()
        self._exit_stack = AsyncExitStack()
        self._lifecycle = asyncio.Lock()

    @final
    async def __aenter__(self) -> Self:
        await self.open()
        return self

    @final
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        await self.close()

    @final
    async def open(self) -> None:
        async with self._lifecycle:
            if self._is_open:
                raise RuntimeError(f"{self.__component__} is already open")

            self._exit_signal.clear()
            try:
                await self._pre_open()
                await self._do_open()
                await self._post_open()
            except BaseException as err:
                await self.__close(True)
                raise err

            self._is_open = True
            if not self._is_quiet:
                self._logger.debug("OPENED")

    @final
    async def close(self) -> None:
        async with self._lifecycle:
            if not self._is_open:
                return
            self._is_open = False
            await self.__close()
            if not self._is_quiet:
                self._logger.debug("CLOSED")

    @final
    async def __close(self, silent=False) -> None:
        self._exit_signal.set()
        errors: list[BaseException] = []

        for fn in (
            self._pre_close,
            self._do_close,
            self._post_close,
            self._exit_stack.aclose,
        ):
            try:
                with suppress(
                    asyncio.CancelledError,
                    asyncio.TimeoutError,
                ):
                    await fn()
            except BaseException as err:
                errors.append(err)

        self._exit_signal.clear()

        if not silent and errors:
            self._logger.warning("Error(s) while closing: {}", errors)

    def _require_open(self) -> None:
        if not self._is_open:
            raise RuntimeError(f"{self.__component__} is not open")

    async def _pre_open(self) -> None:
        pass

    async def _do_open(self) -> None:
        pass

    async def _post_open(self) -> None:
        pass

    async def _pre_close(self) -> None:
        pass

    async def _do_close(self) -> None:
        pass

    async def _post_close(self) -> None:
        pass
