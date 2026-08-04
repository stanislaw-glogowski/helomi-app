import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import yaml

from helomi.conversation.config import ConversationSettings
from helomi.conversation.graph import ResponseDepth, TurnIntent, TurnPlanner
from helomi.conversation.model import (
    ConversationMessage,
    ConversationRole,
    LanguageModelRequest,
    LanguageModelRole,
    LanguageModelService,
    get_language_model,
)
from helomi.conversation.profile import ConversationProfile
from helomi.conversation.reply import ReplySegmenter


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    id: str
    category: str
    text: str
    expected_intent: str
    expected_depth: str


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    id: str
    category: str
    run_kind: str
    expected_intent: str
    selected_intent: str
    expected_depth: str
    selected_depth: str
    planning_path: str
    planning_seconds: float
    classifier_seconds: float
    first_chunk_seconds: float
    first_response_chunk_seconds: float
    first_phrase_seconds: float
    total_seconds: float
    output_characters: int
    response: str


def load_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        BenchmarkCase(
            id=item["id"],
            category=item["category"],
            text=item["text"],
            expected_intent=item.get("expected_intent", "respond"),
            expected_depth=(
                item["expected_depth"]
                if "expected_depth" in item
                else {"fast": "brief", "detailed": "detailed"}[item["expected_mode"]]
            ),
        )
        for item in data["cases"]
    )


async def run_benchmark(
    profile: ConversationProfile,
    settings: ConversationSettings,
    cases: tuple[BenchmarkCase, ...],
) -> tuple[BenchmarkResult, ...]:
    planner = TurnPlanner()
    results: list[BenchmarkResult] = []
    adapter = get_language_model(
        profile,
        settings.language_model,
        require_classifier=True,
    )
    async with LanguageModelService(adapter) as service:
        for index, case in enumerate(cases):
            plan = planner.deterministic_plan(case.text)
            started = perf_counter()
            planning_path = "direct"
            classifier_seconds = 0.0
            if plan is None:
                planning_path = "classifier"
                classifier_started = perf_counter()
                classification = ""
                async for chunk in service.generate(
                    LanguageModelRequest(
                        LanguageModelRole.CLASSIFIER,
                        (
                            ConversationMessage(
                                ConversationRole.SYSTEM,
                                planner.CLASSIFICATION_PROMPT,
                            ),
                            ConversationMessage(ConversationRole.USER, case.text),
                        ),
                    )
                ):
                    classification += chunk.content
                plan = planner.classified_plan(classification)
                classifier_seconds = perf_counter() - classifier_started
            planning_seconds = perf_counter() - started
            if plan.intent in {TurnIntent.NO_RESPONSE, TurnIntent.CANCEL}:
                results.append(
                    BenchmarkResult(
                        id=case.id,
                        category=case.category,
                        run_kind="cold" if index == 0 else "warm",
                        expected_intent=case.expected_intent,
                        selected_intent=plan.intent.value,
                        expected_depth=case.expected_depth,
                        selected_depth=plan.depth.value,
                        planning_path=planning_path,
                        planning_seconds=planning_seconds,
                        classifier_seconds=classifier_seconds,
                        first_chunk_seconds=planning_seconds,
                        first_response_chunk_seconds=0.0,
                        first_phrase_seconds=0.0,
                        total_seconds=planning_seconds,
                        output_characters=0,
                        response="",
                    )
                )
                continue
            role = (
                LanguageModelRole.DETAILED
                if plan.depth is ResponseDepth.DETAILED
                else LanguageModelRole.FAST
            )
            request = LanguageModelRequest(
                role,
                (
                    ConversationMessage(
                        ConversationRole.SYSTEM,
                        profile.prompts.system.format(
                            conversation_summary="No previous conversation."
                        ),
                    ),
                    ConversationMessage(ConversationRole.USER, case.text),
                ),
                cache_prefix=profile.prompts.system.format(
                    conversation_summary="No previous conversation."
                ),
            )
            first_chunk_seconds: float | None = None
            first_response_chunk_seconds: float | None = None
            first_phrase_seconds: float | None = None
            response = ""
            segmenter = ReplySegmenter()
            generation_started = perf_counter()
            async for chunk in service.generate(request):
                if first_chunk_seconds is None:
                    first_chunk_seconds = perf_counter() - started
                    first_response_chunk_seconds = perf_counter() - generation_started
                response += chunk.content
                if first_phrase_seconds is None and segmenter.feed(chunk.content):
                    first_phrase_seconds = perf_counter() - started
            total_seconds = perf_counter() - started
            if first_phrase_seconds is None and segmenter.flush():
                first_phrase_seconds = total_seconds
            results.append(
                BenchmarkResult(
                    id=case.id,
                    category=case.category,
                    run_kind="cold" if index == 0 else "warm",
                    expected_intent=case.expected_intent,
                    selected_intent=plan.intent.value,
                    expected_depth=case.expected_depth,
                    selected_depth=plan.depth.value,
                    planning_path=planning_path,
                    planning_seconds=planning_seconds,
                    classifier_seconds=classifier_seconds,
                    first_chunk_seconds=first_chunk_seconds or total_seconds,
                    first_response_chunk_seconds=(
                        first_response_chunk_seconds or total_seconds
                    ),
                    first_phrase_seconds=first_phrase_seconds or total_seconds,
                    total_seconds=total_seconds,
                    output_characters=len(response),
                    response=response,
                )
            )
    return tuple(results)


def write_report(
    output_directory: Path,
    results: tuple[BenchmarkResult, ...],
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "results.json"
    markdown_path = output_directory / "report.md"
    json_path.write_text(
        json.dumps(
            [asdict(result) for result in results], ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    planning_accuracy = (
        sum(
            result.expected_intent == result.selected_intent
            and result.expected_depth == result.selected_depth
            for result in results
        )
        / len(results)
        if results
        else 0.0
    )
    lines = [
        "# Conversation benchmark report",
        "",
        f"- Cases: {len(results)}",
        f"- Planning accuracy: {planning_accuracy:.1%}",
        "",
        (
            "| Case | Run | Path | Plan | Classifier | Expected intent | "
            "Selected intent | Expected depth | Selected depth | First chunk | "
            "Response chunk | First phrase | Total | Characters |"
        ),
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: | "
        "---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {result.id} | {result.run_kind} | {result.planning_path} | "
        f"{result.planning_seconds:.3f} s | {result.classifier_seconds:.3f} s | "
        f"{result.expected_intent} | {result.selected_intent} | "
        f"{result.expected_depth} | {result.selected_depth} | "
        f"{result.first_chunk_seconds:.3f} s | "
        f"{result.first_response_chunk_seconds:.3f} s | "
        f"{result.first_phrase_seconds:.3f} s | {result.total_seconds:.3f} s | "
        f"{result.output_characters} |"
        for result in results
    )
    lines.extend(
        [
            "",
            "## Human review",
            "",
            "Score each spoken response from 1 to 5.",
            "",
            "| Case | Correctness | Naturalness | Brevity | Personality | Notes |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
            *(f"| {result.id} |  |  |  |  |  |" for result in results),
        ]
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
