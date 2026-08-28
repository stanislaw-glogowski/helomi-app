import asyncio

import pytest

from helomi_common.task.manager import TaskManager


@pytest.mark.asyncio
async def test_task_manager_lifecycle():
    """Verify task manager can schedule and complete coroutines."""
    executed = []

    async def sample_task(val: int):
        await asyncio.sleep(0.01)
        executed.append(val)

    async with TaskManager() as tm:
        tm.add_task(sample_task(1), sample_task(2))
        await asyncio.sleep(0.05)

    assert 1 in executed
    assert 2 in executed


@pytest.mark.asyncio
async def test_task_manager_not_ready_error():
    """Verify adding task before opening raises RuntimeError."""
    tm = TaskManager()

    async def dummy():
        pass

    coro = dummy()
    with pytest.raises(RuntimeError, match="Task manager is not ready"):
        tm.add_task(coro)
    coro.close()


@pytest.mark.asyncio
async def test_task_manager_cancels_running_tasks_on_close():
    """Verify long-running tasks are properly cancelled and cleaned up upon exit."""
    cancelled = False

    async def endless_task():
        nonlocal cancelled
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            cancelled = True
            raise

    tm = TaskManager()
    await tm.open()
    tm.add_task(endless_task())
    await asyncio.sleep(0.02)
    await tm.close()

    assert cancelled
    assert len(tm._tasks) == 0
