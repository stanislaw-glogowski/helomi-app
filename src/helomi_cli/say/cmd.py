import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from helomi_common import TaskManager
from helomi_core import Runtime
from helomi_speech import (
    ProfileActivated,
    ProfileDeactivated,
    SpeechPipeline,
    TranscriptionReady,
)

from ..widgets import Spinner
from .completer import SayCompleter

STYLE = Style.from_dict(
    {
        "profile": "#5f00d7",
        "arrow": "#00e676 bold",
        "completion-menu.completion": "bg:#263238 #ffffff",
        "completion-menu.completion.current": "bg:#0087af #ffffff bold",
        "completion-menu.meta": "italic #80cbc4",
    }
)


async def run_say_cmd(
    runtime: Runtime,
    spinner: Spinner,
    shutdown: asyncio.Event,
    profile_id: str | None = None,
):
    session = PromptSession(
        style=STYLE,
        completer=SayCompleter(runtime),
        complete_while_typing=True,
    )

    await spinner.start("Initializing speech pipeline & audio drivers...")

    async with TaskManager() as tasks:
        async with SpeechPipeline(runtime) as pipeline:
            await spinner.stop()

            if profile_id:
                await pipeline.activate_profile(profile_id)

            tasks.add_task(_input_loop(session, pipeline, shutdown))
            tasks.add_task(pipeline_loop(session, pipeline))

            await shutdown.wait()

            await spinner.start("Closing speech pipeline & audio drivers...")

    await spinner.stop()


async def _input_loop(
    session: PromptSession,
    pipeline: SpeechPipeline,
    shutdown: asyncio.Event,
) -> None:
    def render_badge() -> HTML:
        prefix = (
            f"<profile>{profile.name}</profile> "
            if (profile := pipeline.active_profile)
            else ""
        )

        return HTML(prefix + "Say <arrow>\u276f</arrow> ")

    with patch_stdout():
        while not shutdown.is_set():
            try:
                text = await session.prompt_async(
                    message=render_badge,
                )
                text = text.strip()

                if not text:
                    continue

                if text.lower() in ("exit", "quit", "q"):
                    shutdown.set()
                    break

                if text.lower() == "x":
                    await pipeline.deactivate_profile()
                    continue

                await pipeline.say_text(text)
            except EOFError, KeyboardInterrupt:
                shutdown.set()
                break


async def pipeline_loop(session: PromptSession, pipeline: SpeechPipeline) -> None:
    async for event in pipeline.subscribe():
        match event:
            case ProfileActivated() | ProfileDeactivated():
                session.app.invalidate()

            case TranscriptionReady(text=text):
                buff = session.app.current_buffer
                buff.text = text
                buff.cursor_position = len(text)
                session.app.invalidate()
