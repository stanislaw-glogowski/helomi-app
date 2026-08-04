import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Helomi in the menu bar.")
    parser.add_argument("--language")
    parser.add_argument("--profile")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    from .menu import MenuBarApp

    arguments = build_parser().parse_args(argv)
    MenuBarApp(
        language=arguments.language,
        selected_profile=arguments.profile,
    ).run()
