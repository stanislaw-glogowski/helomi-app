from pydantic import Field

from helomi.common.validation import ConfigModel

from .model.config import LanguageModelSettings, default_language_model_settings


class ConversationSettings(ConfigModel):
    language_model: LanguageModelSettings = default_language_model_settings()
    acknowledgement_delay: float = Field(default=0.8, ge=0.0)
