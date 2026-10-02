import asyncio
import inspect
from collections.abc import Coroutine
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
)
from types import TracebackType

from ..logger import Logger
from .base import BaseComponent
from .decorators import LifecycleHookKind, resolve_lifecycle_hooks


class ManagedComponent(BaseComponent, AbstractAsyncContextManager):
    """Manage reusable asynchronous lifecycle hooks and background tasks."""

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger)
        self._context_lock = asyncio.Lock()
        self._is_mounted = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._exit_signal = asyncio.Event()
        self._exit_stack: AsyncExitStack | None = None

    @property
    def is_mounted(self) -> bool:
        return self._is_mounted

    async def __aenter__(self):
        await self.mount()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ):
        try:
            await self.unmount()
        except BaseException as cleanup_error:
            if exc_value is None:
                raise
            raise BaseExceptionGroup(
                f"{type(self).__name__} context and cleanup failed",
                [exc_value, cleanup_error],
            ) from None
        return None

    async def mount(self):
        async with self._context_lock:
            await self._enter()

    async def unmount(self):
        async with self._context_lock:
            await self._exit()

    async def _enter(self):
        if self._is_mounted:
            return

        self._exit_signal.clear()
        self._exit_stack = AsyncExitStack()
        try:
            await self._mount()
            await self._start_background_tasks()
        except BaseException as mount_error:
            errors = [mount_error, *(await self._teardown())]
            if len(errors) == 1:
                raise
            raise BaseExceptionGroup(
                f"{type(self).__name__} mount and cleanup failed",
                errors,
            ) from None

        self._is_mounted = True

    async def _exit(self):
        if not self._is_mounted and self._exit_stack is None:
            return

        self._is_mounted = False
        errors = await self._teardown()
        if errors:
            raise BaseExceptionGroup(
                f"{type(self).__name__} cleanup failed",
                errors,
            )

    async def _teardown(self) -> list[BaseException]:
        # Stop producers before resources so tasks cannot use half-closed state.
        errors: list[BaseException] = []
        self._exit_signal.set()

        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors.extend(
                result
                for result in results
                if isinstance(result, BaseException)
                and not isinstance(result, asyncio.CancelledError)
            )

        errors.extend(await self._unmount())

        exit_stack = self._exit_stack
        if exit_stack is not None:
            try:
                await exit_stack.aclose()
            except BaseException as error:
                errors.append(error)

        self._tasks.clear()
        self._exit_stack = None
        self._exit_signal.clear()

        return errors

    async def _mount(self):
        await self._run_hooks(LifecycleHookKind.MOUNT)

    async def _unmount(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for decorator in reversed(
            resolve_lifecycle_hooks(self, LifecycleHookKind.UNMOUNT)
        ):
            try:
                await self._run_hook(decorator.name)
            except BaseException as error:
                errors.append(error)
        return errors

    async def _start_background_tasks(self):
        for decorator in resolve_lifecycle_hooks(self, LifecycleHookKind.RUN):
            callback = getattr(self, decorator.name)
            coro: Coroutine | None = callback()

            if not inspect.isawaitable(coro):
                raise RuntimeError(f"Hook {decorator.name} must be async")

            self._tasks.add(
                asyncio.create_task(
                    coro,
                    name=f"{self._component_name}:{decorator.name}",
                )
            )

    async def _run_hooks(self, kind: LifecycleHookKind) -> None:
        for decorator in resolve_lifecycle_hooks(self, kind):
            await self._run_hook(decorator.name)

    async def _run_hook(self, name: str) -> None:
        result = getattr(self, name)()
        if inspect.isawaitable(result):
            await result


class SyncManagedComponent(BaseComponent, AbstractContextManager):
    """Manage reusable synchronous lifecycle hooks."""

    def __init__(self, logger: Logger | None = None):
        super().__init__(logger)
        self._is_mounted = False

    @property
    def is_mounted(self) -> bool:
        return self._is_mounted

    def __enter__(self):
        self.mount()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ):
        try:
            self.unmount()
        except BaseException as cleanup_error:
            if exc_value is None:
                raise
            raise BaseExceptionGroup(
                f"{type(self).__name__} context and cleanup failed",
                [exc_value, cleanup_error],
            ) from None
        return None

    def mount(self):
        self._enter()

    def unmount(self):
        self._exit()

    def _enter(self):
        if self._is_mounted:
            return
        try:
            self._run_hooks(LifecycleHookKind.MOUNT)
        except BaseException as mount_error:
            errors = [mount_error, *self._unmount()]
            if len(errors) == 1:
                raise
            raise BaseExceptionGroup(
                f"{type(self).__name__} mount and cleanup failed",
                errors,
            ) from None
        self._is_mounted = True

    def _exit(self):
        if not self._is_mounted:
            return
        self._is_mounted = False
        errors = self._unmount()
        if errors:
            raise BaseExceptionGroup(
                f"{type(self).__name__} cleanup failed",
                errors,
            )

    def _unmount(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for decorator in reversed(
            resolve_lifecycle_hooks(self, LifecycleHookKind.UNMOUNT)
        ):
            try:
                self._run_hook(decorator.name)
            except BaseException as error:
                errors.append(error)
        return errors

    def _run_hooks(self, kind: LifecycleHookKind) -> None:
        for decorator in resolve_lifecycle_hooks(self, kind):
            self._run_hook(decorator.name)

    def _run_hook(self, name: str) -> None:
        result = getattr(self, name)()
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise RuntimeError("Cannot run async decorators in sync context")
