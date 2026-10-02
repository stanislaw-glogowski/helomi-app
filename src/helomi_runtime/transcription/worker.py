from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial

from helomi_foundation import ThreadedComponent, on_mount, on_unmount

from .domain import TranscriptionChunk, TranscriptionRequest, TranscriptionResponse
from .ports import TranscriptionAdapter


class TranscriptionWorker(ThreadedComponent):
    def __init__(self, adapter: TranscriptionAdapter):
        super().__init__()
        self._adapter = adapter

    async def transcribe(
        self,
        request: TranscriptionRequest,
    ) -> AsyncGenerator[TranscriptionChunk | TranscriptionResponse]:
        chunks: list[TranscriptionChunk] = []
        async with aclosing(
            self._iterate_in_executor(partial(self._adapter.transcribe, request))
        ) as stream:
            async for result in stream:
                match result:
                    case StopIteration():
                        break
                    case Exception() as error:
                        raise error
                    case chunk:
                        chunks.append(chunk)
                        yield chunk
        if response := TranscriptionResponse.from_chunks(chunks):
            yield response

    @on_mount()
    async def _start_adapter(self):
        await self._run_in_executor(self._adapter.mount)

    @on_unmount()
    async def _stop_adapter(self):
        await self._run_in_executor(self._adapter.unmount)
