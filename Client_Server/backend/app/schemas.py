from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool

class TaskStatus(str, Enum):
    queued = "queued"
    preprocessing = "preprocessing"
    rpa_pending = "rpa_pending"
    rpa_running = "rpa_running"
    postprocessing = "postprocessing"
    done = "done"
    failed = "failed"


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus


class TaskStatusResponse(BaseModel):
    task_id: str
    user_id: Optional[int] = None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    message: str = ""
    progress: int = 0
    result: dict[str, Any] = Field(default_factory=dict)


class LogEvent(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int
    message: str
    created_at: datetime
