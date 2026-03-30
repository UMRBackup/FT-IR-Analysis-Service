from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import task_runner


def test_wait_for_shared_file_ready_retries_missing_then_success(monkeypatch, tmp_path):
    target = tmp_path / "delayed.csv"

    monkeypatch.setattr(task_runner.settings, "shared_file_retry_timeout_sec", 2.0)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_initial_delay_sec", 0.01)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_max_delay_sec", 0.01)
    monkeypatch.setattr(task_runner, "resolve_shared_path", lambda _: target)

    sleep_calls = {"count": 0}

    def fake_sleep(_: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] == 1:
            target.write_text("ready", encoding="utf-8")

    monkeypatch.setattr(task_runner.time, "sleep", fake_sleep)

    resolved = task_runner._wait_for_shared_file_ready(
        "tasks/1/output.csv",
        require_nonempty=True,
        context="RPA input CSV not ready",
    )

    assert resolved == target
    assert sleep_calls["count"] >= 1


def test_wait_for_shared_file_ready_retries_empty_then_success(monkeypatch, tmp_path):
    target = tmp_path / "empty_then_ready.csv"
    target.write_text("", encoding="utf-8")

    monkeypatch.setattr(task_runner.settings, "shared_file_retry_timeout_sec", 2.0)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_initial_delay_sec", 0.01)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_max_delay_sec", 0.01)
    monkeypatch.setattr(task_runner, "resolve_shared_path", lambda _: target)

    sleep_calls = {"count": 0}

    def fake_sleep(_: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] == 1:
            target.write_text("data", encoding="utf-8")

    monkeypatch.setattr(task_runner.time, "sleep", fake_sleep)

    resolved = task_runner._wait_for_shared_file_ready(
        "tasks/1/output.csv",
        require_nonempty=True,
        context="RPA input CSV not ready",
    )

    assert resolved == target
    assert sleep_calls["count"] >= 1


def test_wait_for_shared_file_ready_no_retry_on_resolve_error(monkeypatch):
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_timeout_sec", 2.0)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_initial_delay_sec", 0.01)
    monkeypatch.setattr(task_runner.settings, "shared_file_retry_max_delay_sec", 0.01)

    def fake_resolve(_: str) -> Path:
        raise RuntimeError("storage path resolve failed")

    sleep_calls = {"count": 0}

    def fake_sleep(_: float) -> None:
        sleep_calls["count"] += 1

    monkeypatch.setattr(task_runner, "resolve_shared_path", fake_resolve)
    monkeypatch.setattr(task_runner.time, "sleep", fake_sleep)

    try:
        task_runner._wait_for_shared_file_ready(
            "tasks/1/output.csv",
            require_nonempty=True,
            context="RPA input CSV not ready",
        )
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "storage path resolve failed" in str(exc)

    assert sleep_calls["count"] == 0
