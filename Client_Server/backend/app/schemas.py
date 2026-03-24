import re
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,8}$")
PASSWORD_VISIBLE_NO_SPACE_PATTERN = re.compile(r"^\S{6,16}$")


def _validate_username(value: str) -> str:
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Username must be 3-8 chars and use only letters, digits, underscore(_), hyphen(-), no spaces"
        )
    return value


def _validate_password(value: str) -> str:
    if not PASSWORD_VISIBLE_NO_SPACE_PATTERN.fullmatch(value):
        raise ValueError("Password must be 6-16 chars and contain no spaces")
    if re.search(r"[A-Za-z]", value) is None or re.search(r"\d", value) is None:
        raise ValueError("Password must include at least one letter and one digit")
    return value


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return _validate_username(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)

class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password(value)


class JwtRotateRequest(BaseModel):
    new_secret_key: str
    new_key_id: Optional[str] = None


class JwtKeyInfoResponse(BaseModel):
    current_kid: str
    previous_kid: Optional[str] = None
    updated_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool


class AuthResponse(BaseModel):
    token: Token
    user: UserResponse

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
