from ..extension import PipelineExtension
from ..messages import SayTextCmd, TranscriptionReadyEvent


class ParrotExtension(PipelineExtension):
    async def _do_open(self):
        self._tasks.add_task(self._pipeline_loop())

    async def _pipeline_loop(self):
        async for event in self._subscribe_event():
            match event:
                case TranscriptionReadyEvent(text=text, profile_id=profile_id) if (
                    text and text.strip()
                ):
                    await self._execute_command(
                        SayTextCmd(
                            text=text,
                            profile_id=profile_id,
                        )
                    )
