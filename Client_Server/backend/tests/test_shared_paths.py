from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import shared_paths


def test_shared_root_uses_local_storage_root_by_default(monkeypatch, tmp_path):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(shared_paths.settings, "storage_backend", "local")
    monkeypatch.setattr(shared_paths.settings, "storage_root", tmp_path)

    def fake_resolve(self: Path) -> Path:
        calls.append(("resolve", str(self)))
        return self

    def fail_unc(_: Path) -> None:
        raise AssertionError("UNC precheck should not run in local mode")

    monkeypatch.setattr(shared_paths, "_ensure_windows_unc_access", fail_unc)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    resolved = shared_paths.shared_root()

    assert resolved == tmp_path
    assert calls == [("resolve", str(tmp_path))]


def test_shared_root_authenticates_before_resolve(monkeypatch):
    configured_root = Path(r"\\192.168.1.77\zhaozhixuan\shared_storage")
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(shared_paths.settings, "storage_backend", "shared")
    monkeypatch.setattr(shared_paths.settings, "shared_storage_root", configured_root)

    def fake_ensure(path: Path) -> None:
        calls.append(("ensure", str(path)))

    def fake_resolve(self: Path) -> Path:
        calls.append(("resolve", str(self)))
        return self

    monkeypatch.setattr(shared_paths, "_ensure_windows_unc_access", fake_ensure)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    resolved = shared_paths.shared_root()

    assert resolved == configured_root
    assert calls == [
        ("ensure", str(configured_root)),
        ("resolve", str(configured_root)),
    ]


def test_path_exists_swallows_unc_oserror(monkeypatch):
    def fake_exists(self: Path) -> bool:
        raise OSError(1326, "用户名或密码不正确。")

    monkeypatch.setattr(Path, "exists", fake_exists)

    assert shared_paths._path_exists(Path(r"\\192.168.1.77\zhaozhixuan\shared_storage")) is False


def test_unc_check_uses_share_root_not_target_file(monkeypatch):
    target = Path(
        r"\\192.168.1.77\zhaozhixuan\shared_storage\tasks\id\output\work_dir\8022_omnic.pdf"
    )
    share = Path(r"\\192.168.1.77\zhaozhixuan")

    monkeypatch.setattr(shared_paths.settings, "storage_backend", "shared")
    monkeypatch.setattr(shared_paths.os, "name", "nt")
    monkeypatch.setattr(shared_paths, "_UNC_AUTH_CACHE", set())

    def fake_exists(path: Path) -> bool:
        return str(path) == str(share)

    connect_calls: list[tuple[str, str, str]] = []

    def fake_connect(share_root: str, username: str, password: str) -> None:
        connect_calls.append((share_root, username, password))

    monkeypatch.setattr(shared_paths, "_path_exists", fake_exists)
    monkeypatch.setattr(shared_paths, "_connect_unc_share", fake_connect)

    shared_paths._ensure_windows_unc_access(target)

    assert connect_calls == []


def test_oos_backend_is_reserved(monkeypatch):
    monkeypatch.setattr(shared_paths.settings, "storage_backend", "oos")

    try:
        shared_paths.shared_root()
        assert False, "Expected NotImplementedError"
    except NotImplementedError as exc:
        assert "STORAGE_BACKEND=oos" in str(exc)