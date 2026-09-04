from ..pipeline import PipelineExtension, SayText, TranscriptionReady


class ParrotExtension(PipelineExtension):
    async def _do_open(self) -> None:
        self._tasks.add_task(self._pipeline_loop())

    async def _pipeline_loop(self) -> None:
        async for event in self._subscribe():
            match event:
                case TranscriptionReady(text=text):
                    await self._pipeline.execute(
                        SayText(
                            text=text,
                        )
                    )
