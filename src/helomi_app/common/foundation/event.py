import asyncio
from abc import ABC
from collections.abc import AsyncIterator

from .component import AbstractAsyncComponent


class AbstractEventSource[TEvent](AbstractAsyncComponent, ABC):
    def __init__(self) -> None:
        super().__init__()
        self._subscriptions: set[asyncio.Queue[TEvent | None]] = set()

    async def subscribe_event(self) -> AsyncIterator[TEvent]:
        subscription = asyncio.Queue[TEvent | None]()
        self._subscriptions.add(subscription)
        try:
            while not self._exit_signal.is_set():
                event = await subscription.get()
                if event is None:
                    break
                yield event
                subscription.task_done()
        finally:
            self._subscriptions.discard(subscription)

    async def _pre_close(self) -> None:
        self._unsubscribe_all()

    def _unsubscribe_all(self) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(None)
        self._subscriptions.clear()

    def _dispatch_event(self, event: TEvent) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(event)
