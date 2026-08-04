from __future__ import annotations

import asyncio
from concurrent.futures import Future
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from helomi.app import ApplicationRuntime, ProgressSnapshot

from .state import DesktopMode, DesktopSnapshot


class DesktopRuntime:
    """Owns the asyncio loop behind the AppKit main thread."""

    def __init__(self) -> None:
        self._updates: Queue[DesktopSnapshot] = Queue(maxsize=1)
        self._queue_lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = Event()
        self._terminated = Event()
        self._thread: Thread | None = None
        self._command_active = False
        self._selected_profile_id: str | None = None
        self._profile_name = "Helomi"
        self._runtime: ApplicationRuntime | None = None
        self._shutdown_signal: asyncio.Event | None = None
        self._shutting_down = False
        self._watch_task: asyncio.Task[None] | None = None

    @property
    def terminated(self) -> bool:
        return self._terminated.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Desktop runtime is already started")
        self._thread = Thread(target=self._run, name="helomi-desktop-runtime")
        self._thread.start()
        self._loop_ready.wait()

    def retry(self) -> Future[None] | None:
        if self._command_active or self._loop is None:
            return None
        profile_id = self._selected_profile_id
        if profile_id is None:
            return None
        self._command_active = True
        self._publish(
            DesktopSnapshot(
                DesktopMode.RETRYING,
                self._profile_name,
                profile_id,
            )
        )
        return asyncio.run_coroutine_threadsafe(
            self._start_profile(profile_id), self._loop
        )

    def shutdown(self) -> Future[None] | None:
        if self._loop is None or self._terminated.is_set():
            return None
        if self._shutting_down:
            return None
        self._command_active = True
        self._shutting_down = True
        self._publish(
            DesktopSnapshot(
                DesktopMode.SHUTTING_DOWN,
                self._profile_name,
                self._selected_profile_id,
            )
        )
        return asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)

    def drain(self) -> DesktopSnapshot | None:
        latest: DesktopSnapshot | None = None
        while True:
            try:
                latest = self._updates.get_nowait()
            except Empty:
                return latest

    def join(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.join()

    def _run(self) -> None:
        try:
            asyncio.run(self._run_async())
        finally:
            self._terminated.set()

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop_ready.set()
        shutdown = asyncio.Event()
        self._shutdown_signal = shutdown
        try:
            async with ApplicationRuntime() as runtime:
                unsubscribe = runtime.progress.subscribe(
                    lambda progress: self._progress_changed(progress)
                )
                profile = runtime.startup_profile
                self._selected_profile_id = profile.id
                self._profile_name = profile.name
                self._publish(
                    DesktopSnapshot(
                        DesktopMode.STARTING,
                        self._profile_name,
                        profile.id,
                    )
                )
                self._runtime = runtime
                await self._start_profile(profile.id)
                await shutdown.wait()
                unsubscribe()
        except Exception as error:
            self._publish(DesktopSnapshot(DesktopMode.FAILED, detail=str(error)))
            await shutdown.wait()

    async def _start_profile(self, profile_id: str) -> None:
        runtime = self._runtime
        if runtime is None:
            self._command_active = False
            return
        try:
            await runtime.start(profile_id)
        except BaseException as error:
            self._command_active = False
            if self._shutting_down:
                return
            self._publish(
                DesktopSnapshot(
                    DesktopMode.FAILED,
                    self._profile_name,
                    profile_id,
                    str(error),
                )
            )
            return
        self._command_active = False
        self._publish(
            DesktopSnapshot(
                DesktopMode.RUNNING,
                self._profile_name,
                profile_id,
            )
        )
        self._watch_task = asyncio.create_task(
            self._watch_runtime(profile_id), name="helomi-desktop-watch"
        )

    async def _watch_runtime(self, profile_id: str) -> None:
        try:
            runtime = self._runtime
            if runtime is None:
                return
            await runtime.wait()
        except BaseException as error:
            if self._shutting_down:
                return
            self._publish(
                DesktopSnapshot(
                    DesktopMode.FAILED,
                    self._profile_name,
                    profile_id,
                    str(error),
                )
            )
        else:
            if self._shutting_down:
                return
            self._publish(
                DesktopSnapshot(
                    DesktopMode.FAILED,
                    self._profile_name,
                    profile_id,
                    "Helomi runtime stopped",
                )
            )

    async def _shutdown(self) -> None:
        try:
            if self._runtime is not None:
                await self._runtime.shutdown()
        finally:
            if self._shutdown_signal is not None:
                self._shutdown_signal.set()

    def _progress_changed(self, progress: ProgressSnapshot) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._publish_progress, progress)

    def _publish_progress(self, progress: ProgressSnapshot) -> None:
        self._publish(
            DesktopSnapshot(
                self._progress_mode(),
                self._profile_name,
                self._selected_profile_id,
                progress=progress,
            )
        )

    def _publish(self, snapshot: DesktopSnapshot) -> None:
        with self._queue_lock:
            try:
                self._updates.put_nowait(snapshot)
            except Full:
                self._updates.get_nowait()
                self._updates.put_nowait(snapshot)

    def _progress_mode(self) -> DesktopMode:
        if self._shutting_down:
            return DesktopMode.SHUTTING_DOWN
        if self._command_active:
            return DesktopMode.STARTING
        if self._selected_profile_id:
            return DesktopMode.RUNNING
        return DesktopMode.READY
