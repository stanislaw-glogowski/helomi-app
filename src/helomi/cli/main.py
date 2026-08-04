import asyncio
import os
import signal

from loguru import logger

from helomi.app import ApplicationRuntime
from helomi.common.events import EventBus, ShutdownEvent

from .events import UiEventBridge, run_event_logger
from .logs import LogBuffer, configure_ui_logger
from .ui import TerminalApp

os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


def configure_shutdown(event_bus: EventBus) -> None:
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, event_bus.publish, ShutdownEvent())
    loop.add_signal_handler(signal.SIGTERM, event_bus.publish, ShutdownEvent())


async def run() -> None:
    logs = LogBuffer()
    configure_ui_logger(logs)
    bridge = UiEventBridge()

    async with ApplicationRuntime() as runtime:
        configure_shutdown(runtime.event_bus)
        app = TerminalApp(
            runtime.profiles,
            bridge,
            logs,
            runtime.progress,
            runtime.default_profile_id,
            runtime.settings.selected_profile,
        )
        app_task = asyncio.create_task(app.run_async(), name="helomi-ui")
        bridge_task = asyncio.create_task(
            bridge.run(runtime.event_bus), name="helomi-ui-events"
        )
        logger_task = asyncio.create_task(
            run_event_logger(runtime.event_bus), name="helomi-logs"
        )
        backend: asyncio.Task[None] | None = None

        try:
            await asyncio.gather(app.wait_mounted(), bridge.wait_ready())
            if runtime.settings.selected_profile:
                profile = runtime.selected_profile
            else:
                profile = await app.select_profile()
            if profile is None:
                return
            app.configure_runtime(profile, runtime.settings)

            while True:
                await app.show_startup()
                try:
                    await runtime.start(profile.id)
                except BaseExceptionGroup as error:
                    logger.exception("Helomi startup failed")
                    if not await app.wait_startup_retry(error):
                        return
                except Exception as error:
                    logger.exception("Helomi startup failed")
                    if not await app.wait_startup_retry(error):
                        return
                else:
                    await app.finish_startup()
                    backend = asyncio.create_task(runtime.wait(), name="helomi-runtime")
                    break

            quit_task = asyncio.create_task(
                app.wait_quit_requested(), name="helomi-ui-quit"
            )
            done, _ = await asyncio.wait(
                (backend, app_task, quit_task), return_when=asyncio.FIRST_COMPLETED
            )
            if quit_task in done or app_task in done:
                await runtime.shutdown()
            if backend in done:
                await backend
        finally:
            await runtime.shutdown()
            app.exit()
            await asyncio.gather(
                app_task, bridge_task, logger_task, return_exceptions=True
            )


def main() -> None:
    asyncio.run(run())
