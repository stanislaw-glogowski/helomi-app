from dataclasses import dataclass, field, replace
from enum import Enum, auto
from pathlib import Path

from helomi.app import ProgressSnapshot
from helomi.resources import Profile, Settings
from helomi.speech.events import VoiceSessionMode
from helomi.speech.synthesis.config import MLXChatterboxSettings, PiperSettings


class DesktopMode(Enum):
    READY = "Ready"
    STARTING = "Starting"
    RETRYING = "Retrying"
    RUNNING = "Running"
    FAILED = "Failed"
    SHUTTING_DOWN = "Shutting down"


class PhraseState(Enum):
    QUEUED = auto()
    SPEAKING = auto()
    DELIVERED = auto()


@dataclass(frozen=True, slots=True)
class SystemInfo:
    profile_name: str = "Helomi"
    audio_driver: str = "—"
    input_device: str = "Waiting…"
    output_device: str = "Waiting…"
    vad_adapter: str = "—"
    vad_threshold: float = 0.0
    wakeword_label: str = "wake word"
    wakeword_model: str = "—"
    wakeword_threshold: float = 0.0
    stt_adapter: str = "—"
    stt_model: str = "—"
    llm_adapter: str = "—"
    llm_model: str = "—"
    tts_adapter: str = "—"
    tts_model: str = "—"
    captured_sample_count: int = 0
    vad_score: float = 0.0
    vad_detected: bool = False
    wakeword_score: float = 0.0
    wakeword_detected: bool = False
    timings: tuple[tuple[str, float], ...] = ()

    @classmethod
    def from_runtime(cls, profile: Profile, settings: Settings) -> SystemInfo:
        speech = settings.speech
        llm_adapter = settings.conversation.language_model.adapter
        models = (
            profile.conversation.models_mlx
            if llm_adapter == "mlx"
            else profile.conversation.models_langchain
        )
        model_ids = tuple(
            dict.fromkeys(
                model.model_id
                for model in (models.fast, models.detailed, models.classifier)
                if model is not None
            )
        )
        stt_adapter = speech.stt.adapter
        match stt_adapter:
            case "mlx:parakeet-tdt":
                stt_model = profile.stt_mlx_parakeet_tdt.model_id or speech.stt.model_id
            case "mlx:qwen3-asr":
                stt_model = profile.stt_mlx_qwen3_asr.model_id or speech.stt.model_id
            case "mlx:whisper":
                stt_model = profile.stt_mlx_whisper.model_id or speech.stt.model_id
            case _:
                stt_model = speech.stt.model_id
        match speech.tts:
            case PiperSettings() as tts_settings:
                piper = profile.tts_piper
                tts_model = (
                    f"{piper.repo_id or tts_settings.repo_id}/{piper.model_path}"
                )
            case MLXChatterboxSettings() as tts_settings:
                tts_model = profile.tts_mlx_chatterbox.model_id or tts_settings.model_id
            case _:
                tts_model = "—"
        return cls(
            profile_name=profile.name,
            audio_driver=speech.audio.driver,
            vad_adapter=speech.vad.adapter,
            vad_threshold=speech.vad.threshold,
            wakeword_label=(
                profile.wakeword.label if profile.wakeword else "Always listening"
            ),
            wakeword_model=(
                profile.wakeword.model_path if profile.wakeword else "Disabled"
            ),
            wakeword_threshold=(
                profile.wakeword.threshold if profile.wakeword else 0.0
            ),
            stt_adapter=stt_adapter,
            stt_model=stt_model,
            llm_adapter=llm_adapter,
            llm_model=" · ".join(model_ids),
            tts_adapter=speech.tts.adapter,
            tts_model=tts_model,
        )


@dataclass(frozen=True, slots=True)
class UserMessage:
    turn_id: int
    text: str
    committed: bool = False


@dataclass(frozen=True, slots=True)
class AssistantPhrase:
    phrase_id: int
    text: str
    state: PhraseState = PhraseState.QUEUED


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    reply_id: int
    phrases: tuple[AssistantPhrase, ...] = ()
    draft: str = ""
    interrupted: bool = False


type ConversationMessage = UserMessage | AssistantMessage


@dataclass(frozen=True, slots=True)
class ConversationState:
    messages: tuple[ConversationMessage, ...] = ()

    def update_transcription(self, turn_id: int, text: str) -> ConversationState:
        messages = list(self.messages)
        for index, message in enumerate(messages):
            if isinstance(message, UserMessage) and message.turn_id == turn_id:
                if not message.committed:
                    messages[index] = replace(message, text=text)
                return replace(self, messages=tuple(messages))
        messages = [
            item
            for item in messages
            if not isinstance(item, UserMessage) or item.committed
        ]
        messages.append(UserMessage(turn_id, text))
        return replace(self, messages=self._bounded(messages))

    def commit_user(self, turn_id: int, text: str) -> ConversationState:
        messages = list(self.messages)
        for index, message in enumerate(messages):
            if isinstance(message, UserMessage) and message.turn_id == turn_id:
                messages[index] = UserMessage(turn_id, text, committed=True)
                return replace(self, messages=tuple(messages))
        return replace(
            self, messages=self._bounded([*messages, UserMessage(turn_id, text, True)])
        )

    def start_reply(self, reply_id: int) -> ConversationState:
        message, _ = self._assistant(reply_id)
        return (
            self
            if message is not None
            else replace(
                self,
                messages=self._bounded([*self.messages, AssistantMessage(reply_id)]),
            )
        )

    def update_reply_draft(self, reply_id: int, text: str) -> ConversationState:
        message, index = self._assistant(reply_id)
        if message is None:
            return replace(
                self,
                messages=self._bounded(
                    [*self.messages, AssistantMessage(reply_id, draft=text)]
                ),
            )
        if message.interrupted:
            return self
        return self._replace(index, replace(message, draft=text))

    def queue_phrase(
        self, reply_id: int, phrase_id: int, text: str
    ) -> ConversationState:
        message, index = self._assistant(reply_id)
        if message is None:
            return self.start_reply(reply_id).queue_phrase(reply_id, phrase_id, text)
        if message.interrupted or any(
            item.phrase_id == phrase_id for item in message.phrases
        ):
            return self
        return self._replace(
            index,
            replace(
                message,
                phrases=(*message.phrases, AssistantPhrase(phrase_id, text)),
                draft="",
            ),
        )

    def transition_phrase(
        self, reply_id: int, phrase_id: int, target: PhraseState
    ) -> ConversationState:
        message, index = self._assistant(reply_id)
        if message is None or message.interrupted:
            return self
        order = {
            PhraseState.QUEUED: 0,
            PhraseState.SPEAKING: 1,
            PhraseState.DELIVERED: 2,
        }
        phrases = tuple(
            replace(item, state=target)
            if item.phrase_id == phrase_id and order[target] > order[item.state]
            else item
            for item in message.phrases
        )
        return self._replace(index, replace(message, phrases=phrases))

    def complete_reply(self, reply_id: int) -> ConversationState:
        message, index = self._assistant(reply_id)
        if message is None or message.interrupted:
            return self
        if not message.phrases:
            return self._remove(index)
        return self._replace(index, replace(message, draft=""))

    def interrupt_reply(self, reply_id: int | None) -> ConversationState:
        message, index = (
            self._assistant(reply_id)
            if reply_id is not None
            else self._last_assistant()
        )
        if message is None:
            return self
        if not message.phrases:
            return self._remove(index)
        return self._replace(index, replace(message, interrupted=True))

    def _assistant(self, reply_id: int) -> tuple[AssistantMessage | None, int]:
        for index, message in enumerate(self.messages):
            if isinstance(message, AssistantMessage) and message.reply_id == reply_id:
                return message, index
        return None, -1

    def _last_assistant(self) -> tuple[AssistantMessage | None, int]:
        for index in range(len(self.messages) - 1, -1, -1):
            message = self.messages[index]
            if isinstance(message, AssistantMessage):
                return message, index
        return None, -1

    def _replace(self, index: int, message: ConversationMessage) -> ConversationState:
        messages = list(self.messages)
        messages[index] = message
        return replace(self, messages=tuple(messages))

    def _remove(self, index: int) -> ConversationState:
        messages = list(self.messages)
        del messages[index]
        return replace(self, messages=tuple(messages))

    @staticmethod
    def _bounded(
        messages: list[ConversationMessage],
    ) -> tuple[ConversationMessage, ...]:
        return tuple(messages[-200:])


@dataclass(frozen=True, slots=True)
class DesktopSnapshot:
    mode: DesktopMode
    profile_name: str = "Helomi"
    selected_profile_id: str | None = None
    detail: str | None = None
    progress: ProgressSnapshot = field(default_factory=ProgressSnapshot)
    data_path: Path | None = None
    system_info: SystemInfo = field(default_factory=SystemInfo)
    conversation: ConversationState = field(default_factory=ConversationState)
    session_mode: VoiceSessionMode | None = None

    @property
    def retry_enabled(self) -> bool:
        return self.mode is DesktopMode.FAILED and self.selected_profile_id is not None

    @property
    def data_folder_enabled(self) -> bool:
        return self.data_path is not None and self.data_path.is_dir()

    @property
    def waiting_for_wakeword(self) -> bool:
        return self.session_mode is not VoiceSessionMode.ACTIVE

    @property
    def tray_title(self) -> str:
        match self.mode:
            case DesktopMode.RUNNING:
                return self.profile_name
            case DesktopMode.FAILED:
                return f"❌ {self.profile_name}"
            case _:
                return f"⏳ {self.profile_name}"
