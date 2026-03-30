from __future__ import annotations

import socket
from pathlib import Path

from .config import settings


def _resolve_local_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError as exc:
        raise RuntimeError(f"Local storage path resolve failed: {path}") from exc

def shared_root() -> Path:
    return _resolve_local_path(settings.storage_root)


def ensure_shared_root_ready(context: str = "startup") -> Path:
    root = shared_root()
    if not root.exists():
        raise FileNotFoundError(f"[{context}] Storage root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"[{context}] Storage root is not a directory: {root}")

    probe_name = f".probe_{context}_{socket.gethostname()}"
    probe_file = root / probe_name
    try:
        probe_file.write_text("ok", encoding="ascii")
        _ = probe_file.read_text(encoding="ascii")
    except Exception as exc:
        raise RuntimeError(f"[{context}] Storage root read/write check failed at {root}: {exc}") from exc
    finally:
        try:
            if probe_file.exists():
                probe_file.unlink()
        except Exception:
            # Keep startup resilient to probe cleanup issues.
            pass
    return root


def resolve_shared_path(path_or_rel: str) -> Path:
    candidate = Path(path_or_rel)
    if candidate.is_absolute():
        return _resolve_local_path(candidate)
    return _resolve_local_path(shared_root() / candidate)


def to_shared_rel_path(path_or_abs: str | Path) -> str:
    absolute = _resolve_local_path(Path(path_or_abs))
    root = shared_root()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        # Fallback keeps compatibility if a path is outside the configured storage root.
        return str(absolute)
