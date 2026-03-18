from __future__ import annotations

from pathlib import Path

from .config import settings


def shared_root() -> Path:
    return settings.shared_storage_root.resolve()


def resolve_shared_path(path_or_rel: str) -> Path:
    candidate = Path(path_or_rel)
    if candidate.is_absolute():
        return candidate
    return (shared_root() / candidate).resolve()


def to_shared_rel_path(path_or_abs: str | Path) -> str:
    absolute = Path(path_or_abs).resolve()
    root = shared_root()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        # Fallback keeps compatibility if a path is outside the shared root.
        return str(absolute)
