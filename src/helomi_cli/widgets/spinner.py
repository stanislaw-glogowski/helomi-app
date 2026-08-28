import asyncio
import sys


class Spinner:
    def __init__(self, disabled=False):
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._disabled = disabled

    async def start(self, msg: str = "Please wait...") -> None:
        if self._disabled:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._spin(msg))

    async def _spin(self, msg: str) -> None:
        idx = 0
        try:
            while not self._stop_event.is_set():
                frame = self._frames[idx % len(self._frames)]
                sys.stdout.write(f"\r\033[K\033[36m{frame}\033[0m {msg}")
                sys.stdout.flush()
                idx += 1
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass

    async def stop(self, msg: str | None = None) -> None:
        if self._task is None:
            return

        self._stop_event.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

        if msg:
            sys.stdout.write(f"\r\033[K\033[32m✔\033[0m {msg}\n")
        else:
            sys.stdout.write("\r\033[K")
        sys.stdout.flush()
