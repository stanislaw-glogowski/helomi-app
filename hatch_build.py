import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Build and correctly tag Helomi's bundled Apple Silicon audio helper."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        native_root = root / "native" / "macos"
        native_audio = native_root / "avfaudio"
        executable = (
            root / "src" / "helomi_core" / "audio" / "avfaudio" / "bin" / "avfaudio"
        )
        sources = [
            native_audio / "Package.swift",
            *native_audio.glob("Sources/**/*.swift"),
        ]

        if not executable.exists() or any(
            source.stat().st_mtime > executable.stat().st_mtime for source in sources
        ):
            subprocess.run(
                [str(native_root / "build.sh")],
                cwd=root,
                check=True,
            )

        if self.target_name == "wheel":
            build_data["tag"] = "py3-none-macosx_14_0_arm64"
