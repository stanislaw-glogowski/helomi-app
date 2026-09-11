from ..pipeline import PipelineExtension, SayTextCmd, TranscriptionReadyEvent


class ParrotExtension(PipelineExtension):
    async def _do_open(self) -> None:
        self._tasks.add_task(self._pipeline_loop())

    async def _pipeline_loop(self) -> None:
        async for event in self._subscribe_event():
            match event:
                case TranscriptionReadyEvent(text=text) if text and text.strip():
                    await self._execute_command(
                        SayTextCmd(
                            text=text,
                        )
                    )
