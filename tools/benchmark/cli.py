import argparse
import sys

from . import conversation
from .voice.cli import main as voice_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Helomi benchmarks by type.",
        add_help=False,
    )
    parser.add_argument("--type", choices=("conversation", "voice"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["--help"]:
        parser = build_parser()
        parser.print_help()
        return 0
    args, remaining = build_parser().parse_known_args(arguments)
    if args.type == "conversation":
        return conversation.main(remaining)
    return voice_main(remaining)
