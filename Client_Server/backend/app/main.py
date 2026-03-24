from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import chain
import shutil

from .auth import (
    create_access_token,
    get_auth_key_info,
    get_current_user,
    get_user_from_token,
    hash_password,
    rotate_auth_key,
    verify_password,
)
from .celery_app import celery_app
from .config import settings
from .schemas import (
    AuthResponse,
    JwtKeyInfoResponse,
    JwtRotateRequest,
    LogEvent,
    PasswordChangeRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from .shared_paths import ensure_shared_root_ready, resolve_shared_path, shared_root, to_shared_rel_path
from .state import TaskRecord, UserRecord, store

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


def _check_task_access(record: TaskRecord, user: UserRecord) -> None:
    if user.is_admin:
        return
    if record.user_id is None or record.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _require_admin(user: UserRecord) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.post(f"{settings.api_prefix}/auth/register", response_model=UserResponse)
def register(payload: UserCreate) -> UserResponse:
    username = payload.username

    existing = store.get_user_by_username(username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = store.create_user(
        username=username,
        password_hash=hash_password(payload.password),
        is_admin=False,
    )
    return UserResponse(id=user.id, username=user.username, is_admin=user.is_admin)


@app.post(f"{settings.api_prefix}/auth/login", response_model=AuthResponse)
def login(payload: UserLogin) -> AuthResponse:
    user = store.get_user_by_username(payload.username.strip())
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user=user)
    return AuthResponse(
        token=Token(access_token=token, token_type="bearer"),
        user=UserResponse(id=user.id, username=user.username, is_admin=user.is_admin),
    )


@app.post(f"{settings.api_prefix}/auth/logout")
def logout(_: UserRecord = Depends(get_current_user)) -> dict[str, str]:
    return {"status": "ok"}


@app.post(f"{settings.api_prefix}/auth/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, str]:
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    store.update_password(current_user.id, hash_password(payload.new_password))
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/auth/me", response_model=UserResponse)
def me(current_user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.id, username=current_user.username, is_admin=current_user.is_admin)


@app.get(f"{settings.api_prefix}/auth/key-info", response_model=JwtKeyInfoResponse)
def key_info(current_user: UserRecord = Depends(get_current_user)) -> JwtKeyInfoResponse:
    _require_admin(current_user)
    info = get_auth_key_info()
    return JwtKeyInfoResponse(
        current_kid=info.current_kid,
        previous_kid=info.previous_kid,
        updated_at=info.updated_at,
    )


@app.post(f"{settings.api_prefix}/auth/rotate-key", response_model=JwtKeyInfoResponse)
def rotate_key(
    payload: JwtRotateRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> JwtKeyInfoResponse:
    _require_admin(current_user)

    secret = payload.new_secret_key.strip()
    if len(secret) < 32:
        raise HTTPException(status_code=400, detail="new_secret_key must be at least 32 characters")

    new_kid = payload.new_key_id.strip() if payload.new_key_id else None
    if new_kid is not None and len(new_kid) == 0:
        new_kid = None

    rotated = rotate_auth_key(new_secret_key=secret, new_kid=new_kid)
    return JwtKeyInfoResponse(
        current_kid=rotated.current_kid,
        previous_kid=rotated.previous_kid,
        updated_at=rotated.updated_at,
    )


@app.post(f"{settings.api_prefix}/tasks", response_model=TaskCreateResponse)
async def create_task(
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(get_current_user),
) -> TaskCreateResponse:
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
        user_id=current_user.id,
        input_filename=filename,
        input_path=to_shared_rel_path(input_path),
        output_dir=to_shared_rel_path(output_dir),
    )
    store.create(record)

    return TaskCreateResponse(task_id=task_id, status=TaskStatus.queued)


@app.post(f"{settings.api_prefix}/tasks/{{task_id}}/run", response_model=TaskStatusResponse)
async def run_task(task_id: str, current_user: UserRecord = Depends(get_current_user)) -> TaskStatusResponse:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)

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
def get_all_tasks(current_user: UserRecord = Depends(get_current_user)) -> list[TaskStatusResponse]:
    records = store.get_all(user_id=None if current_user.is_admin else current_user.id)
    return [_task_to_response(r) for r in records]

@app.delete(f"{settings.api_prefix}/tasks/{{task_id}}")
def delete_task(task_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)
    
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
def download_report(task_id: str, current_user: UserRecord = Depends(get_current_user)):
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)

    pdf_ref = record.result.get("pdf", "")
    pdf = resolve_shared_path(str(pdf_ref))
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="Report not ready")
        
    # Return the file as a downloadable attachment
    return FileResponse(path=pdf, filename=pdf.name, media_type='application/pdf')

@app.get(f"{settings.api_prefix}/tasks/{{task_id}}", response_model=TaskStatusResponse)
def get_task(task_id: str, current_user: UserRecord = Depends(get_current_user)) -> TaskStatusResponse:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)
    return _task_to_response(record)


@app.get(f"{settings.api_prefix}/tasks/{{task_id}}/report")
def get_report_path(task_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)

    pdf_ref = record.result.get("pdf", "")
    pdf = resolve_shared_path(str(pdf_ref))
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="Report not ready")
    return {
        "pdf": str(pdf),
        "pdf_relative": str(pdf_ref),
    }


@app.get(f"{settings.api_prefix}/tasks/{{task_id}}/logs")
def get_task_logs(
    task_id: str,
    start: int = 0,
    current_user: UserRecord = Depends(get_current_user),
) -> list[dict]:
    record = store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_task_access(record, current_user)
    return store.get_logs(task_id, start=start)


@app.websocket(f"{settings.api_prefix}/tasks/{{task_id}}/ws")
async def task_ws(task_id: str, websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        user = get_user_from_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return

    record = store.get(task_id)
    if not record:
        await websocket.close(code=1008)
        return
    try:
        _check_task_access(record, user)
    except HTTPException:
        await websocket.close(code=1008)
        return

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
