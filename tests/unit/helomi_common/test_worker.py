import threading

import pytest

from helomi_common.foundation.worker import AbstractWorker


class ConcreteWorker(AbstractWorker):
    """Concrete worker implementation for testing."""

    def __init__(self, max_workers: int = 2) -> None:
        super().__init__(max_workers=max_workers)
        self.sync_opened = False
        self.sync_closed = False

    def _do_open_sync(self) -> None:
        self.sync_opened = True

    def _do_close_sync(self) -> None:
        self.sync_closed = True

    def blocking_add(self, a: int, b: int) -> int:
        return a + b

    def get_thread_name(self) -> str:
        return threading.current_thread().name


@pytest.mark.asyncio
async def test_worker_lifecycle_and_execution():
    """Verify ThreadPoolExecutor is initialized on open and executes sync functions."""
    worker = ConcreteWorker(max_workers=2)

    with pytest.raises(RuntimeError, match="ConcreteWorker executor is not ready"):
        await worker._run_sync(worker.blocking_add, 1, 2)

    async with worker:
        assert worker.sync_opened
        assert worker._executor is not None

        # Execute task in thread pool
        result = await worker._run_sync(worker.blocking_add, 10, 20)
        assert result == 30

        thread_name = await worker._run_sync(worker.get_thread_name)
        assert worker.__label__ in thread_name

    assert worker.sync_closed
    assert worker._executor is None


@pytest.mark.asyncio
async def test_worker_post_close_idempotency():
    """Verify multiple post_close calls handle already cleared executor safely."""
    worker = ConcreteWorker()
    await worker.open()
    await worker.close()
    assert worker._executor is None
    # Calling close again should not raise
    await worker.close()
