from collections.abc import AsyncIterator

from helomi_common import AbstractWorker

from .config import TTSProfile
from .domain import TTSChunk, TTSRequest
from .ports import TTSAdapter


class TTSWorker(AbstractWorker):
    def __init__(self, adapter: TTSAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    async def synthesize(
        self,
        request: TTSRequest,
        profile: TTSProfile,
    ) -> AsyncIterator[TTSChunk]:
        iterator = await self._run_sync(
            self._adapter.synthesize,
            request,
            profile.extract_adapter(),
        )

        while not self._exit_signal.is_set():
            match await self._run_sync(next, iterator):
                case StopIteration():
                    return
                case Exception() as err:
                    raise err
                case chunk:
                    yield chunk

    def _do_open_sync(self) -> None:
        self._exit_stack.enter_context(self._adapter)
