from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import shared_paths


def test_shared_root_uses_local_storage_root_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(shared_paths.settings, "storage_root", tmp_path)

    resolved = shared_paths.shared_root()

    assert resolved == tmp_path
    assert resolved.is_absolute()


def test_resolve_shared_path_joins_storage_root_for_relative_path(monkeypatch, tmp_path):
    monkeypatch.setattr(shared_paths.settings, "storage_root", tmp_path)

    resolved = shared_paths.resolve_shared_path("tasks/1/output.csv")

    assert resolved == (tmp_path / "tasks" / "1" / "output.csv").resolve()


def test_to_shared_rel_path_returns_relative_when_inside_storage_root(monkeypatch, tmp_path):
    monkeypatch.setattr(shared_paths.settings, "storage_root", tmp_path)

    target = (tmp_path / "tasks" / "2" / "output" / "result.pdf").resolve()

    rel = shared_paths.to_shared_rel_path(target)

    assert rel == "tasks/2/output/result.pdf"