import asyncio
from collections.abc import Coroutine

from .foundation import AbstractAsyncComponent


class TaskManager(AbstractAsyncComponent):
    def __init__(self):
        super().__init__(True)
        self._group: asyncio.TaskGroup | None = None
        self._tasks: list[asyncio.Task] = []

    def add_task(self, *coro: Coroutine) -> None:
        group = self._require_group()
        for c in coro:
            self._tasks.append(group.create_task(c))

    def _require_group(self) -> asyncio.TaskGroup:
        if self._group is None:
            raise RuntimeError("Task manager is not ready")
        return self._group

    async def _do_open(self) -> None:
        self._group = await self._exit_stack.enter_async_context(asyncio.TaskGroup())

    async def _post_close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
