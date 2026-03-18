from __future__ import annotations

from datetime import datetime

from .celery_app import celery_app
from .schemas import TaskStatus
from .state import store
from .task_runner import (
    run_postprocess_stage_with_stream,
    run_preprocess_stage_with_stream,
    run_rpa_stage_with_stream,
)


@celery_app.task(name="app.tasks.preprocess_task")
def preprocess_task(task_id: str) -> str:
    try:
        record = store.get(task_id)
        if not record:
            raise ValueError(f"Task not found: {task_id}")

        updated = store.update(
            task_id,
            status=TaskStatus.preprocessing,
            message="Preprocess stage started",
            progress=10,
        )
        if updated:
            store.append_log(
                task_id,
                {
                    "task_id": task_id,
                    "status": updated.status.value,
                    "progress": updated.progress,
                    "message": updated.message,
                    "created_at": updated.updated_at.isoformat(),
                },
            )

        def on_log(message: str, progress: int) -> None:
            latest = store.update(
                task_id,
                status=TaskStatus.preprocessing,
                message=message,
                progress=max(10, min(progress, 39)),
            )
            if latest:
                store.append_log(
                    task_id,
                    {
                        "task_id": task_id,
                        "status": latest.status.value,
                        "progress": latest.progress,
                        "message": latest.message,
                        "created_at": latest.updated_at.isoformat(),
                    },
                )

        preprocess_result = run_preprocess_stage_with_stream(
            image_path=record.input_path,
            output_dir=record.output_dir,
            on_log=on_log,
        )
        merged_result = {**record.result, **preprocess_result}
        store.update(
            task_id,
            status=TaskStatus.rpa_pending,
            message="Preprocess stage done",
            progress=40,
            result=merged_result,
        )
        store.append_log(
            task_id,
            {
                "task_id": task_id,
                "status": TaskStatus.rpa_pending.value,
                "progress": 40,
                "message": "Preprocess stage done",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        return task_id
    except Exception as exc:
        failed = store.update(
            task_id,
            status=TaskStatus.failed,
            message=f"Task failed: {exc}",
            progress=100,
        )
        if failed:
            store.append_log(
                task_id,
                {
                    "task_id": task_id,
                    "status": failed.status.value,
                    "progress": failed.progress,
                    "message": failed.message,
                    "created_at": failed.updated_at.isoformat(),
                },
            )
        raise


@celery_app.task(name="app.tasks.rpa_task")
def rpa_task(task_id: str) -> str:
    try:
        record = store.get(task_id)
        if not record:
            raise ValueError(f"Task not found: {task_id}")

        output_csv = str(record.result.get("output_csv", ""))
        omnic_pdf = str(record.result.get("omnic_pdf", ""))
        if not output_csv or not omnic_pdf:
            raise ValueError("Missing preprocess artifacts: output_csv or omnic_pdf")

        store.update(task_id, status=TaskStatus.rpa_pending, message="RPA stage pending", progress=40)

        def on_log(message: str, progress: int) -> None:
            updated = store.update(
                task_id,
                status=TaskStatus.rpa_running,
                message=message,
                progress=max(40, min(progress, 85)),
            )
            if updated:
                store.append_log(
                    task_id,
                    {
                        "task_id": task_id,
                        "status": updated.status.value,
                        "progress": updated.progress,
                        "message": updated.message,
                        "created_at": updated.updated_at.isoformat(),
                    },
                )

        stage_result = run_rpa_stage_with_stream(
            output_csv=output_csv,
            omnic_pdf=omnic_pdf,
            on_log=on_log,
        )
        merged_result = {**record.result, **stage_result}
        store.update(
            task_id,
            status=TaskStatus.postprocessing,
            result=merged_result,
            progress=86,
            message="RPA stage done",
        )
        store.append_log(
            task_id,
            {
                "task_id": task_id,
                "status": TaskStatus.postprocessing.value,
                "progress": 86,
                "message": "RPA stage done",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        return task_id
    except Exception as exc:
        failed = store.update(
            task_id,
            status=TaskStatus.failed,
            message=f"Task failed: {exc}",
            progress=100,
        )
        if failed:
            store.append_log(
                task_id,
                {
                    "task_id": task_id,
                    "status": failed.status.value,
                    "progress": failed.progress,
                    "message": failed.message,
                    "created_at": failed.updated_at.isoformat(),
                },
            )
        raise


@celery_app.task(name="app.tasks.postprocess_task")
def postprocess_task(task_id: str) -> dict:
    try:
        record = store.get(task_id)
        if not record:
            raise ValueError(f"Task not found: {task_id}")

        output_csv = str(record.result.get("output_csv", ""))
        omnic_pdf = str(record.result.get("omnic_pdf", ""))
        final_pdf = str(record.result.get("final_pdf", ""))
        if not output_csv or not omnic_pdf or not final_pdf:
            raise ValueError("Missing artifacts for postprocess stage")

        store.update(task_id, status=TaskStatus.postprocessing, message="Postprocess stage started", progress=86)
        store.append_log(
            task_id,
            {
                "task_id": task_id,
                "status": TaskStatus.postprocessing.value,
                "progress": 86,
                "message": "Postprocess stage started",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        def on_log(message: str, progress: int) -> None:
            latest = store.update(
                task_id,
                status=TaskStatus.postprocessing,
                message=message,
                progress=max(86, min(progress, 99)),
            )
            if latest:
                store.append_log(
                    task_id,
                    {
                        "task_id": task_id,
                        "status": latest.status.value,
                        "progress": latest.progress,
                        "message": latest.message,
                        "created_at": latest.updated_at.isoformat(),
                    },
                )

        stage_result = run_postprocess_stage_with_stream(
            output_csv=output_csv,
            omnic_pdf=omnic_pdf,
            final_pdf=final_pdf,
            on_log=on_log,
        )

        merged_result = {
            **record.result,
            **stage_result,
            "csv": record.result.get("output_csv", ""),
            "work_dir": record.result.get("work_dir", ""),
        }

        done = store.update(
            task_id,
            status=TaskStatus.done,
            message="Task completed",
            progress=100,
            result=merged_result,
        )
        if done:
            store.append_log(
                task_id,
                {
                    "task_id": task_id,
                    "status": done.status.value,
                    "progress": done.progress,
                    "message": done.message,
                    "created_at": done.updated_at.isoformat(),
                },
            )
            return done.result
        return {}
    except Exception as exc:
        failed = store.update(
            task_id,
            status=TaskStatus.failed,
            message=f"Task failed: {exc}",
            progress=100,
        )
        if failed:
            store.append_log(
                task_id,
                {
                    "task_id": task_id,
                    "status": failed.status.value,
                    "progress": failed.progress,
                    "message": failed.message,
                    "created_at": failed.updated_at.isoformat(),
                },
            )
        raise
