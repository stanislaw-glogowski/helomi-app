NATIVE_AUDIO := src/helomi/speech/audio/adapters/avfaudio/bin/audio
NATIVE_AUDIO_INPUTS := \
	native/macos/audio/Package.swift \
	$(shell find native/macos/audio/Sources -type f -name '*.swift') \
	$(shell find native/macos/audio/Sources -type d)

.PHONY: init run verify

run-cli: $(NATIVE_AUDIO)
	uv run helomi-cli

init: $(NATIVE_AUDIO)
	uv sync
	uv run python -m tools.install

verify:
	UV_CACHE_DIR=/private/tmp/uv-cache uv run ruff check hatch_build.py src tests tools
	UV_CACHE_DIR=/private/tmp/uv-cache uv run ruff format --check hatch_build.py src tests tools pyproject.toml
	UV_CACHE_DIR=/private/tmp/uv-cache uv run pyrefly check
	UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q
	UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall -q hatch_build.py src tests tools
	swift format lint --recursive native/macos/audio
	swift test --package-path native/macos/audio
	UV_CACHE_DIR=/private/tmp/uv-cache uv build
