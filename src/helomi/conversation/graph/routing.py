import re
from dataclasses import dataclass
from enum import StrEnum


class ResponseDepth(StrEnum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


class TurnIntent(StrEnum):
    RESPOND = "respond"
    CLARIFY = "clarify"
    CANCEL = "cancel"
    QUIT = "quit"
    NO_RESPONSE = "no_response"


class ReactionPolicy(StrEnum):
    NONE = "none"
    ACKNOWLEDGE = "acknowledge"
    WAIT = "wait"


@dataclass(frozen=True, slots=True)
class TurnPlan:
    intent: TurnIntent
    depth: ResponseDepth
    reaction: ReactionPolicy = ReactionPolicy.NONE


class TurnPlanner:
    """Plan a turn locally before consulting the classifier when needed."""

    CLASSIFICATION_PROMPT = (
        "Classify the user's conversational turn using the supplied context. Return "
        "exactly one label: NO_RESPONSE for a listener acknowledgement that needs no "
        "answer, CLARIFY when one concise clarification question is needed, BRIEF for "
        "a 1-2 sentence answer, STANDARD for a 2-4 sentence answer, or DETAILED for "
        "a comprehensive answer. Never return CANCEL."
    )
    _CANCEL_PHRASES = frozenset({"stop", "przestań", "anuluj", "nieważne"})
    _QUIT_REQUEST = re.compile(
        r"(?:(?:please|proszę|prosze) )?"
        r"(?:"
        r"(?:(?:can|could|would|will) you )?"
        r"(?:close|quit|exit)(?: (?:the )?(?:app|application|helomi|yourself))?"
        r"|shut down(?: (?:the )?(?:app|application|helomi))?"
        r"|(?:(?:czy )?(?:możesz|mozesz)(?: się| sie)? )?"
        r"(?:zamknij|zamknąć|zamknac|wyłącz|wylacz|wyłączyć|wylaczyc|"
        r"zakończ|zakoncz|zakończyć|zakonczyc)"
        r"(?: (?:aplikację|aplikacje|program|helomi|się|sie|działanie|dzialanie))?"
        r")"
        r"(?: (?:please|proszę|prosze))?"
    )
    _DETAIL_MARKERS = ("dokładnie", "szczegółowo", "krok po kroku", "pełny plan")
    _BRIEF_MARKERS = (
        "jednym zdaniu",
        "jednym słowem",
        "krótko",
        "w dwóch zdaniach",
        "zwięźle",
    )
    _QUESTION_WORDS = frozenset(
        {
            "co",
            "czego",
            "czemu",
            "czy",
            "dlaczego",
            "dokąd",
            "gdzie",
            "ile",
            "jak",
            "jaka",
            "jaki",
            "jakie",
            "jakiego",
            "jakiej",
            "kiedy",
            "kto",
            "która",
            "które",
            "którego",
            "której",
            "który",
            "skąd",
        }
    )
    _RESPONSE_REQUEST_WORDS = frozenset(
        {
            "napisz",
            "opowiedz",
            "podaj",
            "porównaj",
            "powiedz",
            "przygotuj",
            "streść",
            "wymień",
            "wyjaśnij",
        }
    )
    _CONTEXT_DEPENDENT_WORDS = frozenset({"dalej", "jeszcze", "tamto", "to", "więcej"})
    _WHITESPACE = re.compile(r"\s+")

    @classmethod
    def normalize(cls, text: str) -> str:
        return cls._WHITESPACE.sub(" ", text.strip().casefold().strip(".?!,;: "))

    def deterministic_plan(self, text: str) -> TurnPlan | None:
        normalized = self.normalize(text)
        if not normalized:
            return TurnPlan(TurnIntent.NO_RESPONSE, ResponseDepth.BRIEF)
        if normalized in self._CANCEL_PHRASES:
            return TurnPlan(TurnIntent.CANCEL, ResponseDepth.BRIEF)
        if self._QUIT_REQUEST.fullmatch(normalized):
            return TurnPlan(TurnIntent.QUIT, ResponseDepth.BRIEF)
        words = normalized.split()
        if words and words[0] in self._RESPONSE_REQUEST_WORDS:
            normalized_words = {word.strip(",") for word in words[1:]}
            if normalized_words & self._QUESTION_WORDS:
                return TurnPlan(TurnIntent.RESPOND, ResponseDepth.BRIEF)
            if normalized_words & self._CONTEXT_DEPENDENT_WORDS:
                return None
            depth = (
                ResponseDepth.DETAILED
                if text.count("?") > 1
                or any(marker in normalized for marker in self._DETAIL_MARKERS)
                else (
                    ResponseDepth.BRIEF
                    if any(marker in normalized for marker in self._BRIEF_MARKERS)
                    else ResponseDepth.STANDARD
                )
            )
            return TurnPlan(
                TurnIntent.RESPOND,
                depth,
                reaction=(
                    ReactionPolicy.ACKNOWLEDGE
                    if depth is not ResponseDepth.BRIEF
                    else ReactionPolicy.NONE
                ),
            )
        if text.count("?") > 1 or any(
            marker in normalized for marker in self._DETAIL_MARKERS
        ):
            return TurnPlan(
                TurnIntent.RESPOND, ResponseDepth.DETAILED, ReactionPolicy.WAIT
            )
        if text.rstrip().endswith("?") or (words and words[0] in self._QUESTION_WORDS):
            return TurnPlan(TurnIntent.RESPOND, ResponseDepth.BRIEF)
        return None

    def classified_plan(self, classification: str) -> TurnPlan:
        normalized = classification.strip().upper()
        label = normalized.split(maxsplit=1)[0] if normalized else ""
        plans = {
            "NO_RESPONSE": TurnPlan(TurnIntent.NO_RESPONSE, ResponseDepth.BRIEF),
            "CLARIFY": TurnPlan(TurnIntent.CLARIFY, ResponseDepth.BRIEF),
            "BRIEF": TurnPlan(TurnIntent.RESPOND, ResponseDepth.BRIEF),
            "STANDARD": TurnPlan(
                TurnIntent.RESPOND, ResponseDepth.STANDARD, ReactionPolicy.WAIT
            ),
            "DETAILED": TurnPlan(
                TurnIntent.RESPOND, ResponseDepth.DETAILED, ReactionPolicy.WAIT
            ),
        }
        return plans.get(
            label,
            TurnPlan(TurnIntent.RESPOND, ResponseDepth.STANDARD, ReactionPolicy.WAIT),
        )
