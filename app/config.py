from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
DEFAULT_DB_NAME = "library.db"


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
