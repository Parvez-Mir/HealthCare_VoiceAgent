"""Small, thread-safe-file-friendly helpers for the JSON-backed data store."""

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as data_file:
        return json.load(data_file)


def save_json(path: Path, value: Any) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as data_file:
        json.dump(value, data_file, indent=2)
        data_file.write("\n")
    os.replace(temporary_path, path)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key] = value
    return values


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0]
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line)
    output.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    temporary_path = path.with_suffix(".env.tmp")
    temporary_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)
