import asyncio
from collections.abc import AsyncGenerator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from ..logger import Logger
from .decorators import on_mount
from .managed import ManagedComponent


class ThreadedComponent(ManagedComponent):
    """Run blocking adapter work on one affinity-preserving thread."""

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger)
        self._executor: ThreadPoolExecutor | None = None

    @on_mount(order=-1000)
    async def _bootstrap(self):
        if self._executor is not None:
            raise RuntimeError(f"{type(self).__name__} executor is already running")

        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"{self._component_name}/executor",
        )
        exit_stack = self._exit_stack
        if exit_stack is None:
            raise RuntimeError(f"{type(self).__name__} exit stack is not ready")
        exit_stack.push_async_callback(self._shutdown_executor)

    async def _shutdown_executor(self):
        executor = self._executor
        if executor is None:
            return

        self._executor = None
        await asyncio.to_thread(
            executor.shutdown,
            wait=True,
            cancel_futures=True,
        )

    async def _run_in_executor[*Args, Result](
        self,
        func: Callable[[*Args], Result],
        /,
        *args: *Args,
    ) -> Result:
        executor = self._executor
        if executor is None:
            raise RuntimeError(f"{type(self).__name__} executor is not ready")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            executor,
            func,
            *args,
        )

    async def _iterate_in_executor[T](
        self, factory: Callable[[], Iterator[T]]
    ) -> AsyncGenerator[T]:
        iterator = await self._run_in_executor(factory)
        end = object()
        try:
            while not self._exit_signal.is_set():
                # StopIteration cannot cross an asyncio Future boundary.
                result = await self._run_in_executor(next, iterator, end)
                if result is end:
                    return
                yield cast(T, result)
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                # A cancelled next() may still be running. The same executor
                # serializes close() behind it and preserves generator affinity.
                await asyncio.shield(self._run_in_executor(close))
