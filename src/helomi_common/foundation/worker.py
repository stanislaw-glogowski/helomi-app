import asyncio
from abc import ABC
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import final

from .component import AbstractAsyncComponent


class AbstractWorker(AbstractAsyncComponent, ABC):
    def __init__(self, max_workers: int = 1) -> None:
        super().__init__()

        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    @final
    async def _pre_open(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix=f"{self.__component__}/executor",
        )

    @final
    async def _do_open(self) -> None:
        await self._run_sync(self._do_open_sync)

    @final
    async def _do_close(self) -> None:
        await self._run_sync(self._do_close_sync)

    @final
    async def _post_close(self) -> None:
        if self._executor is None:
            return

        try:
            await asyncio.to_thread(
                self._executor.shutdown,
                wait=True,
                cancel_futures=True,
            )
        finally:
            self._executor = None

    def _do_open_sync(self) -> None:
        pass

    def _do_close_sync(self) -> None:
        pass

    async def _run_sync[*Ts, R](self, func: Callable[[*Ts], R], *args: *Ts) -> R:
        executor = self._executor
        if executor is None:
            raise RuntimeError(f"{self.__component__} executor is not ready")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            executor,
            func,
            *args,
        )
