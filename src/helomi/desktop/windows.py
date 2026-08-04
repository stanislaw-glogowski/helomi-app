from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from .state import AssistantMessage, DesktopSnapshot, UserMessage


class DesktopWindows:
    """Small AppKit views retained by the menu-bar application."""

    def __init__(self) -> None:
        self._appkit = cast(Any, import_module("AppKit"))
        self._conversation_window, self._conversation_text = self._make_window(
            "Helomi Conversation History", 680, 560
        )
        self._system_window, self._system_text = self._make_window(
            "Helomi System Info", 620, 620
        )
        self._conversation_snapshot: DesktopSnapshot | None = None
        self._system_snapshot: DesktopSnapshot | None = None

    def update(self, snapshot: DesktopSnapshot) -> None:
        if snapshot != self._conversation_snapshot:
            self._update_conversation(snapshot)
            self._conversation_snapshot = snapshot
        if snapshot != self._system_snapshot:
            self._system_text.setString_(self._system_text_value(snapshot))
            self._system_snapshot = snapshot

    def show_conversation(self) -> None:
        self._show(self._conversation_window)

    def show_system_info(self) -> None:
        self._show(self._system_window)

    def _make_window(self, title: str, width: float, height: float):
        appkit = self._appkit
        frame = appkit.NSMakeRect(0, 0, width, height)
        style = (
            appkit.NSWindowStyleMaskTitled
            | appkit.NSWindowStyleMaskClosable
            | appkit.NSWindowStyleMaskMiniaturizable
            | appkit.NSWindowStyleMaskResizable
        )
        window = appkit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, appkit.NSBackingStoreBuffered, False
        )
        window.setTitle_(title)
        window.setReleasedWhenClosed_(False)
        scroll = appkit.NSScrollView.alloc().initWithFrame_(frame)
        scroll.setAutoresizingMask_(
            appkit.NSViewWidthSizable | appkit.NSViewHeightSizable
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(appkit.NSBezelBorder)
        text = appkit.NSTextView.alloc().initWithFrame_(frame)
        text.setEditable_(False)
        text.setSelectable_(True)
        text.setRichText_(False)
        text.setFont_(appkit.NSFont.userFixedPitchFontOfSize_(13))
        text.setAutoresizingMask_(appkit.NSViewWidthSizable)
        text.setTextContainerInset_(appkit.NSMakeSize(14, 14))
        scroll.setDocumentView_(text)
        window.setContentView_(scroll)
        return window, text

    def _show(self, window: Any) -> None:
        window.makeKeyAndOrderFront_(None)
        self._appkit.NSApp.activateIgnoringOtherApps_(True)

    def _update_conversation(self, snapshot: DesktopSnapshot) -> None:
        scroll = self._conversation_text.enclosingScrollView()
        content = scroll.contentView()
        visible = content.documentVisibleRect()
        document = self._conversation_text.bounds()
        follows_latest = (
            visible.origin.y + visible.size.height >= document.size.height - 2
        )
        self._conversation_text.setString_(self._conversation_text_value(snapshot))
        if follows_latest:
            self._conversation_text.scrollRangeToVisible_(
                self._appkit.NSMakeRange(len(self._conversation_text.string()), 0)
            )

    @staticmethod
    def _conversation_text_value(snapshot: DesktopSnapshot) -> str:
        if not snapshot.conversation.messages:
            if snapshot.waiting_for_wakeword:
                return f"Waiting for “{snapshot.system_info.wakeword_label}”…"
            return "Listening…"
        sections: list[str] = []
        for message in snapshot.conversation.messages:
            if isinstance(message, UserMessage):
                suffix = "  ● listening" if not message.committed else ""
                sections.append(f"YOU\n{message.text or 'Listening…'}{suffix}")
                continue
            assert isinstance(message, AssistantMessage)
            phrases = " ".join(
                f"[{phrase.state.name.lower()}] {phrase.text}"
                for phrase in message.phrases
            )
            draft = f"\n[drafting] {message.draft}" if message.draft else ""
            interrupted = "\n— REPLY INTERRUPTED —" if message.interrupted else ""
            body = phrases or ("Thinking…" if not draft else "")
            sections.append(f"{snapshot.profile_name}\n{body}{draft}{interrupted}")
        return "\n\n".join(sections)

    @staticmethod
    def _system_text_value(snapshot: DesktopSnapshot) -> str:
        info = snapshot.system_info
        vad_status = "DETECTED" if info.vad_detected else "idle"
        wakeword_status = "DETECTED" if info.wakeword_detected else "idle"
        vad = f"VAD                     {info.vad_score:.3f}  {vad_status}"
        wakeword = (
            f"WAKE WORD               {info.wakeword_score:.3f}  {wakeword_status}"
        )
        vad_config = f"VAD                     {info.vad_adapter} / "
        vad_config += f"{info.vad_threshold:.2f}"
        wake_config = f"WAKE                    {info.wakeword_model} / "
        wake_config += f"{info.wakeword_threshold:.2f}"
        stt = f"STT                     {info.stt_adapter}\n                        "
        stt += info.stt_model
        llm = f"LLM                     {info.llm_adapter}\n                        "
        llm += info.llm_model
        tts = f"TTS                     {info.tts_adapter}\n                        "
        tts += info.tts_model
        timings = (
            "\n".join(
                f"{stage.replace('_', ' ').upper():<24} {elapsed:,.0f} ms"
                for stage, elapsed in info.timings
            )
            or "NO INTERACTION YET"
        )
        return "\n".join(
            (
                "SIGNALS",
                vad,
                wakeword,
                f"CAPTURED                {info.captured_sample_count:,} samples",
                "",
                "RUNTIME",
                f"AUDIO                   {info.audio_driver}",
                f"INPUT                   {info.input_device}",
                f"OUTPUT                  {info.output_device}",
                vad_config,
                wake_config,
                stt,
                llm,
                tts,
                "",
                "LATENCY",
                timings,
            )
        )
