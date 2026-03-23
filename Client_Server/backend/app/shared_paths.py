from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

from .config import settings


_UNC_AUTH_CACHE: set[str] = set()


def _unc_connection_root(path_str: str) -> str:
    # Convert \\server\share\... -> \\server\share for net use.
    parts = path_str.lstrip("\\").split("\\")
    if len(parts) < 2:
        return ""
    return f"\\\\{parts[0]}\\{parts[1]}"


def _connect_unc_share(share_root: str, username: str, password: str) -> None:
    # Drop stale session first to avoid error 1219 (multiple credentials).
    subprocess.run(
        ["net", "use", share_root, "/delete", "/y"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    connect = subprocess.run(
        ["net", "use", share_root, password, f"/user:{username}", "/persistent:no"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if connect.returncode != 0:
        stderr = (connect.stderr or "").strip()
        stdout = (connect.stdout or "").strip()
        detail = stderr or stdout or f"exit_code={connect.returncode}"
        raise RuntimeError(f"UNC authentication failed for {share_root}: {detail}")


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _ensure_windows_unc_access(root: Path) -> None:
    if os.name != "nt":
        return

    root_str = str(root)
    if not root_str.startswith("\\\\"):
        return

    share_root = _unc_connection_root(root_str)
    if not share_root:
        return

    if share_root in _UNC_AUTH_CACHE and _path_exists(root):
        return

    if _path_exists(root):
        _UNC_AUTH_CACHE.add(share_root)
        return

    username = settings.unc_username or settings.nas_user
    password = settings.unc_password or settings.nas_pass
    if username and password:
        _connect_unc_share(share_root, username, password)
        if _path_exists(root):
            _UNC_AUTH_CACHE.add(share_root)
            return

    raise FileNotFoundError(
        "Shared UNC path is not accessible. "
        f"path={root}; share={share_root}. "
        "If this is a credential issue, set UNC_USERNAME/UNC_PASSWORD (or NAS_USER/NAS_PASS) "
        "in backend/.env and restart the Windows worker process."
    )


def _resolve_path_with_unc_access(path: Path) -> Path:
    _ensure_windows_unc_access(path)
    try:
        return path.resolve()
    except OSError as exc:
        raise RuntimeError(f"Shared path resolve failed after UNC precheck: {path}") from exc


def shared_root() -> Path:
    return _resolve_path_with_unc_access(settings.shared_storage_root)


def ensure_shared_root_ready(context: str = "startup") -> Path:
    root = shared_root()
    if not root.exists():
        raise FileNotFoundError(f"[{context}] Shared root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"[{context}] Shared root is not a directory: {root}")

    probe_name = f".probe_{context}_{socket.gethostname()}_{os.getpid()}"
    probe_file = root / probe_name
    try:
        probe_file.write_text("ok", encoding="ascii")
        _ = probe_file.read_text(encoding="ascii")
    except Exception as exc:
        raise RuntimeError(f"[{context}] Shared root read/write check failed at {root}: {exc}") from exc
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
        return _resolve_path_with_unc_access(candidate)
    return _resolve_path_with_unc_access(shared_root() / candidate)


def to_shared_rel_path(path_or_abs: str | Path) -> str:
    absolute = _resolve_path_with_unc_access(Path(path_or_abs))
    root = shared_root()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        # Fallback keeps compatibility if a path is outside the shared root.
        return str(absolute)
