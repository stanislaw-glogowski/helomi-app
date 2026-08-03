import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from helomi.conversation.profile import ConversationProfile
from helomi.resources import LocalStore

from .core import load_cases, run_benchmark, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Helomi conversation models")
    parser.add_argument("--profile")
    parser.add_argument(
        "--model-id",
        help="Override every conversation model role for a candidate run",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("benchmarks/conversation/suites/pl-core.yml"),
    )
    parser.add_argument("--output", type=Path)
    return parser


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def report_root() -> Path:
    return repository_root() / "benchmarks" / "conversation" / "report"


async def run(args: argparse.Namespace) -> tuple[Path, Path]:
    store = LocalStore()
    profile = (
        store.load_profile(args.profile)
        if args.profile is not None
        else store.load_default_profile()
    )
    settings = store.load_settings().conversation
    cases = load_cases(args.suite)
    conversation = override_model_id(profile.conversation, args.model_id)
    results = await run_benchmark(conversation, settings, cases)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or report_root() / (
        f"{profile.id}-{settings.language_model.adapter}-{timestamp}"
    )
    return write_report(output, results)


def override_model_id(
    profile: ConversationProfile,
    model_id: str | None,
) -> ConversationProfile:
    if model_id is None:
        return profile
    models = {
        role: {**options, "model_id": model_id}
        for role, options in profile.models.items()
    }
    return profile.model_copy(update={"models": models})


def main(argv: list[str] | None = None) -> int:
    json_path, markdown_path = asyncio.run(run(build_parser().parse_args(argv)))
    print(f"Raw results: {json_path}")
    print(f"Report: {markdown_path}")
    return 0
