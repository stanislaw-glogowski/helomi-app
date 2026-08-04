from pathlib import Path
from typing import Any

import yaml


def load_mapping(path: Path, *, label: str) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a mapping: {path}")
    return data


def merge_mappings(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = merge_mappings(existing, value)
        else:
            merged[key] = value
    return merged
