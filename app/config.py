from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
DEFAULT_DB_NAME = "library.db"
DEFAULT_TAG_NAMESPACE_CONFIG = [
    {"tag_prefix": "Genre", "ui_label": "Genre"},
    {"tag_prefix": "Reader", "ui_label": "Reader"},
    {"tag_prefix": "Romance", "ui_label": "Romance"},
    {"tag_prefix": "Setting", "ui_label": "Setting"},
    {"tag_prefix": "Commitment", "ui_label": "Commitment"},
]
DEFAULT_INFERENCE_ORDER = ["description_clean", "tag_inference"]


@dataclass(frozen=True)
class ScanConfig:
    db_path: Path
    library_roots: list[Path]
    allowed_extensions: set[str]
    ignore_patterns: list[str]


def load_config(path: Path = CONFIG_PATH) -> ScanConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    db_name = raw.get("db_name") or DEFAULT_DB_NAME
    db_path = path.parent / db_name
    roots = [Path(p) for p in raw.get("library_roots", [])]
    allowed = {ext.lower() for ext in raw.get("allowed_extensions", [])}
    ignore = list(raw.get("ignore_patterns", []))
    return ScanConfig(
        db_path=db_path,
        library_roots=roots,
        allowed_extensions=allowed,
        ignore_patterns=ignore,
    )


def get_tag_namespace_config(path: Path = CONFIG_PATH) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    configured = raw.get("tag_namespace_config") or DEFAULT_TAG_NAMESPACE_CONFIG
    cleaned: list[dict[str, str]] = []
    for entry in configured:
        if not isinstance(entry, dict):
            continue
        tag_prefix = str(entry.get("tag_prefix") or "").strip()
        ui_label = str(entry.get("ui_label") or tag_prefix).strip()
        if not tag_prefix:
            continue
        cleaned.append(
            {
                "tag_prefix": tag_prefix,
                "ui_label": ui_label or tag_prefix,
            }
        )
    return cleaned or list(DEFAULT_TAG_NAMESPACE_CONFIG)


def get_tag_namespace_list(
    config: list[dict[str, str]] | None = None,
    path: Path = CONFIG_PATH,
) -> list[str]:
    if config is None:
        config = get_tag_namespace_config(path)
    return [entry["tag_prefix"] for entry in config]


def get_inference_order(path: Path = CONFIG_PATH) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    configured = raw.get("inference_order") or DEFAULT_INFERENCE_ORDER
    if not isinstance(configured, list):
        return list(DEFAULT_INFERENCE_ORDER)
    allowed = {"description_clean", "tag_inference"}
    cleaned = [str(entry).strip() for entry in configured if str(entry).strip() in allowed]
    return cleaned or list(DEFAULT_INFERENCE_ORDER)


def iter_files(roots: Iterable[Path], allowed_extensions: set[str], ignore_patterns: list[str]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            path_str = str(path)
            if any(pat in path_str for pat in ignore_patterns):
                continue
            if not path.is_file():
                continue
            if allowed_extensions and path.suffix.lower() not in allowed_extensions:
                continue
            yield path
