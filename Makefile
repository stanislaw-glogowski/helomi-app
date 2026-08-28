ifeq (run-cli,$(firstword $(MAKECMDGOALS)))
  CLI_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(CLI_ARGS):;@:)
endif

.PHONY: init run-cli test lint format typecheck verify

init:
	uv sync

run-cli:
	uv run helomi-cli $(CLI_ARGS)

test:
	UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q

lint:
	UV_CACHE_DIR=/private/tmp/uv-cache uv run ruff check hatch_build.py src tests
	UV_CACHE_DIR=/private/tmp/uv-cache uv run ruff format --check hatch_build.py src tests pyproject.toml
	UV_CACHE_DIR=/private/tmp/uv-cache uv run pyrefly check
	swift format lint --recursive native/macos/avfaudio

format:
	UV_CACHE_DIR=/private/tmp/uv-cache uv run ruff format hatch_build.py src tests pyproject.toml
	swift format format --in-place --recursive native/macos/avfaudio

typecheck:
	UV_CACHE_DIR=/private/tmp/uv-cache uv run pyrefly check

verify: lint test
	UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall -q hatch_build.py src tests
	swift test --package-path native/macos/avfaudio
	UV_CACHE_DIR=/private/tmp/uv-cache uv build

