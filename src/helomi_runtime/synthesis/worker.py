import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial

from helomi_foundation import ThreadedComponent, on_mount, on_unmount

from .domain import SynthesisChunk, SynthesisRequest
from .ports import SynthesisAdapter


class SynthesisWorker(ThreadedComponent):
    def __init__(self, adapter: SynthesisAdapter):
        super().__init__()
        self._adapter = adapter
        self._synthesis_lock = asyncio.Lock()

    async def synthesize(
        self, request: SynthesisRequest
    ) -> AsyncGenerator[SynthesisChunk]:
        # Model caches are mutable across generation steps, so an entire
        # request owns the adapter until its iterator has been closed.
        async with self._synthesis_lock:
            async with aclosing(
                self._iterate_in_executor(partial(self._adapter.synthesize, request))
            ) as stream:
                async for result in stream:
                    match result:
                        case StopIteration():
                            return
                        case Exception() as error:
                            raise error
                        case chunk:
                            yield chunk

    @on_mount()
    async def _start_adapter(self):
        await self._run_in_executor(self._adapter.mount)

    @on_unmount()
    async def _stop_adapter(self):
        await self._run_in_executor(self._adapter.unmount)
