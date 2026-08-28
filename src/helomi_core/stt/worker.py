from collections.abc import AsyncIterator

from helomi_common import AbstractWorker

from .config import STTProfile
from .domain import STTChunk, STTRequest, STTResponse
from .ports import STTAdapter


class STTWorker(AbstractWorker):
    def __init__(self, adapter: STTAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    async def transcribe(
        self,
        request: STTRequest,
        profile: STTProfile,
    ) -> AsyncIterator[STTChunk | STTResponse]:
        iterator = await self._run_sync(
            self._adapter.transcribe,
            request,
            profile.extract_adapter(),
        )

        chunks: list[STTChunk] = []

        while not self._exit_signal.is_set():
            match await self._run_sync(next, iterator):
                case StopIteration():
                    if response := STTResponse.from_chunks(chunks):
                        yield response
                    return
                case Exception() as err:
                    raise err
                case chunk:
                    chunks.append(chunk)
                    yield chunk

    def _do_open_sync(self) -> None:
        self._exit_stack.enter_context(self._adapter)
