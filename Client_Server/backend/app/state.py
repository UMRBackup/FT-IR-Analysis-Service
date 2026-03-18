from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import settings
from .schemas import TaskStatus

@dataclass
class UserRecord:
    id: int
    username: str
    password_hash: str
    is_admin: bool

@dataclass
class TaskRecord:
    task_id: str
    input_filename: str
    input_path: str
    output_dir: str
    user_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    status: TaskStatus = TaskStatus.queued
    message: str = "Task created"
    progress: int = 0
    result: dict[str, Any] = field(default_factory=dict)


class Base(DeclarativeBase):
    pass

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TaskModel(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)
    input_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    output_dir: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class TaskLogModel(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class MySQLTaskStore:
    def __init__(self) -> None:
        self._engine = create_engine(settings.database_url, pool_pre_ping=True)
        Base.metadata.create_all(self._engine)
        # Handle existing DBs that don't have user_id
        with Session(self._engine) as session:
            try:
                session.execute(text("ALTER TABLE tasks ADD COLUMN user_id INTEGER;"))
                session.commit()
            except Exception:
                session.rollback()

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> UserRecord:
        with Session(self._engine) as session:
            row = UserModel(username=username, password_hash=password_hash, is_admin=is_admin)
            session.add(row)
            session.commit()
            session.refresh(row)
            return UserRecord(id=row.id, username=row.username, password_hash=row.password_hash, is_admin=row.is_admin)

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with Session(self._engine) as session:
            stmt = select(UserModel).where(UserModel.username == username)
            row = session.execute(stmt).scalar_one_or_none()
            if not row:
                return None
            return UserRecord(id=row.id, username=row.username, password_hash=row.password_hash, is_admin=row.is_admin)

    def get_user_by_id(self, user_id: int) -> UserRecord | None:
        with Session(self._engine) as session:
            row = session.get(UserModel, user_id)
            if not row:
                return None
            return UserRecord(id=row.id, username=row.username, password_hash=row.password_hash, is_admin=row.is_admin)

    def update_password(self, user_id: int, new_password_hash: str) -> None:
        with Session(self._engine) as session:
            row = session.get(UserModel, user_id)
            if row:
                row.password_hash = new_password_hash
                session.commit()

    @staticmethod
    def _to_record(row: TaskModel) -> TaskRecord:
        return TaskRecord(
            task_id=row.task_id,
            input_filename=row.input_filename,
            input_path=row.input_path,
            output_dir=row.output_dir,
            user_id=row.user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            status=TaskStatus(row.status),
            message=row.message,
            progress=row.progress,
            result=json.loads(row.result_json or "{}"),
        )

    def create(self, record: TaskRecord) -> None:
        with Session(self._engine) as session:
            row = TaskModel(
                task_id=record.task_id,
                user_id=record.user_id,
                input_filename=record.input_filename,
                input_path=record.input_path,
                output_dir=record.output_dir,
                created_at=record.created_at,
                updated_at=record.updated_at,
                status=record.status.value,
                message=record.message,
                progress=record.progress,
                result_json=json.dumps(record.result, ensure_ascii=False),
            )
            session.add(row)
            session.commit()

    def get(self, task_id: str) -> TaskRecord | None:
        with Session(self._engine) as session:
            row = session.get(TaskModel, task_id)
            if not row:
                return None
            return self._to_record(row)

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        message: str | None = None,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> TaskRecord | None:
        with Session(self._engine) as session:
            row = session.get(TaskModel, task_id)
            if not row:
                return None
            if status is not None:
                row.status = status.value
            if message is not None:
                row.message = message
            if progress is not None:
                row.progress = progress
            if result is not None:
                row.result_json = json.dumps(result, ensure_ascii=False)
            row.updated_at = datetime.utcnow()
            session.commit()
            return self._to_record(row)

    def append_log(self, task_id: str, payload: dict[str, Any]) -> None:
        with Session(self._engine) as session:
            session.add(
                TaskLogModel(
                    task_id=task_id,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()

    def get_logs(self, task_id: str, start: int = 0) -> list[dict[str, Any]]:
        with Session(self._engine) as session:
            stmt = (
                select(TaskLogModel)
                .where(TaskLogModel.task_id == task_id)
                .order_by(TaskLogModel.id.asc())
                .offset(max(start, 0))
            )
            rows = session.execute(stmt).scalars().all()
            return [json.loads(row.payload_json) for row in rows]

    def get_all(self, user_id: Optional[int] = None) -> list[TaskRecord]:
        with Session(self._engine) as session:
            stmt = select(TaskModel)
            if user_id is not None:
                stmt = stmt.where(TaskModel.user_id == user_id)
            stmt = stmt.order_by(TaskModel.created_at.desc())
            rows = session.execute(stmt).scalars().all()
            return [self._to_record(row) for row in rows]

    def delete(self, task_id: str) -> bool:
        with Session(self._engine) as session:
            row = session.get(TaskModel, task_id)
            if not row:
                return False
            # Also delete logs
            session.query(TaskLogModel).filter(TaskLogModel.task_id == task_id).delete()
            session.delete(row)
            session.commit()
            return True


store = MySQLTaskStore()
