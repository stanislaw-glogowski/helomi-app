import asyncio
import threading
from collections.abc import Iterator

import pytest

from helomi_foundation import (
    ManagedComponent,
    SyncManagedComponent,
    ThreadedComponent,
    on_mount,
    on_run,
    on_unmount,
)


class AsyncProbe(ManagedComponent):
    def __init__(self, events: list[str]):
        super().__init__()
        self.events = events

    @on_mount(order=10)
    async def mount_late(self):
        self.events.append("mount_late")
        assert self._exit_stack is not None
        self._exit_stack.callback(self.events.append, "stack")

    @on_mount(order=-10)
    def mount_early(self):
        self.events.append("mount_early")

    @on_run()
    async def run(self):
        self.events.append("run")
        try:
            await asyncio.Future()
        finally:
            self.events.append("cancelled")

    @on_unmount(order=10)
    async def unmount_late(self):
        self.events.append("unmount_late")

    @on_unmount(order=-10)
    def unmount_early(self):
        self.events.append("unmount_early")


async def test_managed_component_is_idempotent_and_reusable():
    events: list[str] = []
    component = AsyncProbe(events)

    await component.mount()
    await component.mount()
    await asyncio.sleep(0)
    await component.unmount()
    await component.unmount()

    assert events == [
        "mount_early",
        "mount_late",
        "run",
        "cancelled",
        "unmount_late",
        "unmount_early",
        "stack",
    ]
    assert not component.is_mounted

    await component.mount()
    await asyncio.sleep(0)
    await component.unmount()
    assert events.count("stack") == 2


async def test_managed_component_aggregates_background_and_cleanup_errors():
    class BrokenComponent(ManagedComponent):
        @on_run()
        async def fail_run(self):
            raise LookupError("run")

        @on_unmount(order=1)
        def fail_first_cleanup(self):
            raise RuntimeError("first")

        @on_unmount(order=2)
        def fail_second_cleanup(self):
            raise ValueError("second")

    component = BrokenComponent()
    await component.mount()
    await asyncio.sleep(0)

    with pytest.raises(BaseExceptionGroup) as raised:
        await component.unmount()

    assert {str(error) for error in raised.value.exceptions} == {
        "run",
        "first",
        "second",
    }


async def test_managed_component_cleans_up_after_mount_failure():
    events: list[str] = []

    class BrokenMount(ManagedComponent):
        @on_mount()
        async def fail_mount(self):
            events.append("mount")
            raise RuntimeError("mount failed")

        @on_unmount()
        async def record_unmount(self):
            events.append("unmount")

    component = BrokenMount()
    with pytest.raises(RuntimeError, match="mount failed"):
        await component.mount()

    assert events == ["mount", "unmount"]
    assert not component.is_mounted
    await component.unmount()


def test_sync_component_inherits_and_can_disable_a_hook():
    events: list[str] = []

    class Parent(SyncManagedComponent):
        @on_mount()
        def inherited(self):
            events.append("parent")

        @on_mount(order=10)
        def retained(self):
            events.append("retained")

        @on_unmount()
        def cleanup(self):
            events.append("cleanup")

    class Child(Parent):
        def inherited(self):
            events.append("disabled")

        @on_mount(order=-10)
        def child(self):
            events.append("child")

    component = Child()
    component.mount()
    component.mount()
    component.unmount()
    component.unmount()

    assert events == ["child", "retained", "cleanup"]


def test_sync_component_rejects_async_hook_without_leaking_coroutine():
    class InvalidComponent(SyncManagedComponent):
        @on_mount()
        async def invalid_mount_hook(self):
            pass

    with pytest.raises(RuntimeError, match="sync context"):
        InvalidComponent().mount()


async def test_threaded_component_preserves_iterator_thread_affinity():
    class Probe(ThreadedComponent):
        async def values(self) -> tuple[int, int]:
            iterator = await self._run_in_executor(self._iterator)
            first = await self._run_in_executor(next, iterator)
            second = await self._run_in_executor(next, iterator)
            return first, second

        @staticmethod
        def _iterator() -> Iterator[int]:
            owner = threading.get_ident()
            yield owner
            assert threading.get_ident() == owner
            yield threading.get_ident()

    component = Probe()
    async with component:
        first, second = await component.values()

    assert first == second
    with pytest.raises(RuntimeError, match="executor is not ready"):
        await component.values()


def test_duplicate_decorator_is_rejected():
    with pytest.raises(ValueError, match="already defined"):

        class InvalidComponent(SyncManagedComponent):
            @on_mount()
            @on_mount()
            def mount(self):
                pass
