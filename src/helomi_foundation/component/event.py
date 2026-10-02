import asyncio
from collections.abc import AsyncIterator

from .decorators import on_unmount
from .managed import ManagedComponent


class EventSource[T](ManagedComponent):
    """Broadcast events to independent asynchronous subscribers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subscriptions: set[asyncio.Queue[T | None]] = set()

    async def subscribe_events(self) -> AsyncIterator[T]:
        subscription: asyncio.Queue[T | None] = asyncio.Queue()
        self._subscriptions.add(subscription)
        try:
            while True:
                event = await subscription.get()
                try:
                    if event is None:
                        return
                    yield event
                finally:
                    subscription.task_done()
        finally:
            self._subscriptions.discard(subscription)

    def _dispatch_event(self, event: T) -> None:
        for subscription in tuple(self._subscriptions):
            subscription.put_nowait(event)

    @on_unmount(order=10_000)
    def _close_subscriptions(self) -> None:
        for subscription in tuple(self._subscriptions):
            subscription.put_nowait(None)
        self._subscriptions.clear()
