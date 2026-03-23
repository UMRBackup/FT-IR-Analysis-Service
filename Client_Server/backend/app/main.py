from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import chain
import shutil

from .celery_app import celery_app
from .config import settings
from .schemas import LogEvent, TaskCreateResponse, TaskStatus, TaskStatusResponse
from .shared_paths import ensure_shared_root_ready, resolve_shared_path, shared_root, to_shared_rel_path
from .state import TaskRecord, store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = ensure_shared_root_ready("api-startup")
    logger.info("Shared root precheck passed: %s", root)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _task_to_response(record: TaskRecord) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        message=record.message,
        progress=record.progress,
        result=record.result,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.post(f"{settings.api_prefix}/tasks", response_model=TaskCreateResponse)
async def create_task(file: UploadFile = File(...)) -> TaskCreateResponse:
    task_id = str(uuid.uuid4())
    task_root = shared_root() / "tasks" / task_id
    input_dir = task_root / "input"
    output_dir = task_root / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "input.dat"
    input_path = input_dir / filename
    content = await file.read()
    input_path.write_bytes(content)

    record = TaskRecord(
        task_id=task_id,
        input_filename=filename,
        input_path=to_shared_rel_path(input_path),
        output_dir=to_shared_rel_path(output_dir),
    )
    store.create(record)

    return TaskCreateResponse(task_id=task_id, status=TaskStatus.queued)


@app.post(f"{settings.api_prefix}/tasks/{{task_id}}/run", response_model=TaskStatusResponse)
async def run_task(task_id: str) -> TaskStatusResponse:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    # Use signatures bound to our configured celery_app to avoid falling back
    # to Celery's default app/broker (e.g. pyamqp://guest@localhost).
    flow = chain(
        celery_app.signature("app.tasks.preprocess_task", args=(task_id,)),
        celery_app.signature("app.tasks.rpa_task"),
        celery_app.signature("app.tasks.postprocess_task"),
    )

    try:
        async_result: Any = flow.apply_async()
    except Exception as exc:
        failed = store.update(
            task_id,
            status=TaskStatus.failed,
            message=f"Celery dispatch failed: {exc}",
            progress=100,
        )
        if failed:
            store.append_log(
                task_id,
                LogEvent(
                    task_id=task_id,
                    status=TaskStatus.failed,
                    progress=100,
                    message=failed.message,
                    created_at=failed.updated_at,
                ).model_dump(mode="json"),
            )
        raise HTTPException(status_code=503, detail="Task dispatch failed") from exc

    updated = store.update(task_id, status=TaskStatus.queued, message="Task enqueued", progress=1)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    celery_task_id = str(getattr(async_result, "id", ""))

    store.append_log(
        task_id,
        LogEvent(
            task_id=task_id,
            status=TaskStatus.queued,
            progress=1,
            message=f"Celery task accepted: {celery_task_id}",
            created_at=updated.updated_at,
        ).model_dump(mode="json"),
    )
    store.update(
        task_id,
        result={**updated.result, "celery_task_id": celery_task_id},
    )
    latest = store.get(task_id)
    if not latest:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(latest)


@app.get(f"{settings.api_prefix}/tasks", response_model=list[TaskStatusResponse])
def get_all_tasks() -> list[TaskStatusResponse]:
    records = store.get_all()
    return [_task_to_response(r) for r in records]

@app.delete(f"{settings.api_prefix}/tasks/{{task_id}}")
def delete_task(task_id: str) -> dict:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Remove from DB
    deleted = store.delete(task_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete task from database")
        
    # Remove from disk
    task_root = shared_root() / "tasks" / task_id
    if task_root.exists():
        try:
            shutil.rmtree(task_root)
        except Exception as e:
            # We can print or log the error, but the task is deleted from DB.
            pass
            
    return {"status": "success", "task_id": task_id}

@app.get(f"{settings.api_prefix}/tasks/{{task_id}}/download")
def download_report(task_id: str):
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    pdf_ref = record.result.get("pdf", "")
    pdf = resolve_shared_path(str(pdf_ref))
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="Report not ready")
        
    # Return the file as a downloadable attachment
    return FileResponse(path=pdf, filename=pdf.name, media_type='application/pdf')

@app.get(f"{settings.api_prefix}/tasks/{{task_id}}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(record)


@app.get(f"{settings.api_prefix}/tasks/{{task_id}}/report")
def get_report_path(task_id: str) -> dict:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    pdf_ref = record.result.get("pdf", "")
    pdf = resolve_shared_path(str(pdf_ref))
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="Report not ready")
    return {
        "pdf": str(pdf),
        "pdf_relative": str(pdf_ref),
    }


@app.get(f"{settings.api_prefix}/tasks/{{task_id}}/logs")
def get_task_logs(task_id: str, start: int = 0) -> list[dict]:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return store.get_logs(task_id, start=start)


@app.websocket(f"{settings.api_prefix}/tasks/{{task_id}}/ws")
async def task_ws(task_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    cursor = 0
    try:
        while True:
            logs = store.get_logs(task_id, start=cursor)
            for item in logs:
                await websocket.send_json(item)
            cursor += len(logs)
            await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return
