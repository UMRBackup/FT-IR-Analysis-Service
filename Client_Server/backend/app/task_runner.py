from __future__ import annotations

import io
import importlib
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable

from .config import settings
from .shared_paths import resolve_shared_path, to_shared_rel_path


def _ensure_code_root_importable() -> None:
    code_root = settings.code_root.resolve()
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))


def parse_progress(log_line: str) -> tuple[int, str]:
    # Parse pipeline log like [2/5] ... into rough progress percent.
    matched = re.search(r"\[(\d+)/(\d+)\]", log_line)
    if matched:
        current = int(matched.group(1))
        total = int(matched.group(2))
        if total <= 0:
            return 0, log_line
        return int(current / total * 100), log_line
    return 0, log_line


def _capture_stage_logs(callable_obj: Callable[[], object]) -> tuple[object, list[str]]:
    output_buffer = io.StringIO()
    with redirect_stdout(output_buffer):
        result = callable_obj()
    logs = output_buffer.getvalue().splitlines()
    return result, logs


def _emit_logs(
    logs: list[str],
    on_log: Callable[[str, int], None],
    *,
    floor: int,
    span: int,
) -> None:
    for line in logs:
        stage_progress, msg = parse_progress(line)
        mapped = floor + int(stage_progress * span / 100)
        on_log(msg, max(floor, min(mapped, floor + span)))


def _relativize_result_paths(result: dict[str, object]) -> dict[str, object]:
    path_keys = {
        "output_csv",
        "omnic_pdf",
        "final_pdf",
        "pipeline_root",
        "work_dir",
        "pdf",
        "csv",
    }
    converted: dict[str, object] = {}
    for key, value in result.items():
        if key in path_keys and isinstance(value, str):
            converted[key] = to_shared_rel_path(Path(value))
        else:
            converted[key] = value
    return converted


def run_preprocess_stage_with_stream(
    image_path: str,
    output_dir: str,
    on_log: Callable[[str, int], None],
) -> dict:
    _ensure_code_root_importable()

    resolved_image_path = resolve_shared_path(image_path)
    resolved_output_dir = resolve_shared_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_module = importlib.import_module("pipeline")
    run_preprocess_stage = getattr(pipeline_module, "run_preprocess_stage")

    result, logs = _capture_stage_logs(
        lambda: run_preprocess_stage(
            image_path=str(resolved_image_path),
            output_dir=str(resolved_output_dir),
        )
    )
    if not isinstance(result, dict):
        raise ValueError("run_preprocess_stage should return a dict")
    _emit_logs(logs, on_log, floor=10, span=25)
    return _relativize_result_paths(result)


def run_rpa_stage_with_stream(
    output_csv: str,
    omnic_pdf: str,
    on_log: Callable[[str, int], None],
) -> dict:
    _ensure_code_root_importable()

    resolved_csv_path = resolve_shared_path(output_csv)
    resolved_omnic_pdf = resolve_shared_path(omnic_pdf)
    resolved_omnic_pdf.parent.mkdir(parents=True, exist_ok=True)

    pipeline_module = importlib.import_module("pipeline")
    run_rpa_stage = getattr(pipeline_module, "run_rpa_stage")

    result, logs = _capture_stage_logs(
        lambda: run_rpa_stage(
            output_csv=str(resolved_csv_path),
            omnic_pdf=str(resolved_omnic_pdf),
        )
    )
    _emit_logs(logs, on_log, floor=40, span=45)

    if isinstance(result, str):
        return {"omnic_pdf": to_shared_rel_path(Path(result))}
    return {}


def run_postprocess_stage_with_stream(
    output_csv: str,
    omnic_pdf: str,
    final_pdf: str,
    on_log: Callable[[str, int], None],
) -> dict:
    _ensure_code_root_importable()

    resolved_csv_path = resolve_shared_path(output_csv)
    resolved_omnic_pdf = resolve_shared_path(omnic_pdf)
    resolved_final_pdf = resolve_shared_path(final_pdf)
    resolved_final_pdf.parent.mkdir(parents=True, exist_ok=True)

    pipeline_module = importlib.import_module("pipeline")
    run_postprocess_stage = getattr(pipeline_module, "run_postprocess_stage")

    result, logs = _capture_stage_logs(
        lambda: run_postprocess_stage(
            output_csv=str(resolved_csv_path),
            omnic_pdf=str(resolved_omnic_pdf),
            final_pdf=str(resolved_final_pdf),
        )
    )
    _emit_logs(logs, on_log, floor=86, span=13)

    if isinstance(result, str):
        return {"pdf": to_shared_rel_path(Path(result))}
    return {}


def run_pipeline_with_stream(
    image_path: str,
    output_dir: str,
    on_log: Callable[[str, int], None],
) -> dict:
    _ensure_code_root_importable()

    resolved_image_path = resolve_shared_path(image_path)
    resolved_output_dir = resolve_shared_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_module = importlib.import_module("pipeline")
    run_pipeline = getattr(pipeline_module, "run_pipeline")

    output_buffer = io.StringIO()
    count = 0
    with redirect_stdout(output_buffer):
        count = run_pipeline(image_path=str(resolved_image_path), output_dir=str(resolved_output_dir))

    logs = output_buffer.getvalue().splitlines()
    for line in logs:
        progress, msg = parse_progress(line)
        on_log(msg, progress)

    input_stem = resolved_image_path.stem
    csv_path = resolved_output_dir / f"{input_stem}.csv"
    pdf_path = resolved_output_dir / f"{input_stem}.pdf"
    work_dir = resolved_output_dir / "work_dir"

    return {
        "points_count": count,
        "csv": to_shared_rel_path(csv_path),
        "pdf": to_shared_rel_path(pdf_path),
        "work_dir": to_shared_rel_path(work_dir),
    }
