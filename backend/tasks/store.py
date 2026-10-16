"""Task domain model, validation, and JSON-file persistence.

This module deliberately has no third-party imports so the task logic can be
imported and tested without installing the web framework.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_DONE = "done"
TASK_STATUSES: tuple[str, ...] = (
    TASK_STATUS_PENDING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_DONE,
)

TASK_SOURCE_MANUAL = "manual"
TASK_SOURCE_CHAT = "chat"
TASK_SOURCE_AGENT = "agent"
TASK_SOURCES: tuple[str, ...] = (
    TASK_SOURCE_MANUAL,
    TASK_SOURCE_CHAT,
    TASK_SOURCE_AGENT,
)

DEFAULT_STATUS = TASK_STATUS_PENDING
DEFAULT_SOURCE = TASK_SOURCE_MANUAL

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000

# Mirrors knowledge/chroma_store.py, which stores its data under <repo>/data.
DEFAULT_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "tasks.json"

UPDATABLE_FIELDS = frozenset({"title", "description", "due_date", "status", "source"})

REQUIRED_RECORD_FIELDS = frozenset(
    {"id", "title", "status", "source", "created_at", "updated_at"}
)


class TaskNotFoundError(RuntimeError):
    """Raised when a task id does not exist."""


class TaskStorageError(RuntimeError):
    """Raised when the task store file cannot be read or written."""


@dataclass(frozen=True)
class Task:
    """A single task record."""

    id: str
    title: str
    description: str
    due_date: str | None
    status: str
    source: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of this task."""
        return asdict(self)


class TaskStore:
    """Persist tasks in a JSON file guarded by an in-process lock."""

    def __init__(
        self,
        path: str | Path = DEFAULT_STORE_PATH,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.path = Path(path)
        self._clock = _utc_now_iso if clock is None else clock
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._load()

    def __len__(self) -> int:
        with self._lock:
            return len(self._tasks)

    def get(self, task_id: str) -> Task:
        """Return one task or raise ``TaskNotFoundError``."""
        key = _validate_task_id(task_id)

        with self._lock:
            task = self._tasks.get(key)

        if task is None:
            raise TaskNotFoundError(f"task not found: {key}")

        return task

    def list(self, status: str | None = None) -> list[Task]:
        """Return tasks, newest first, optionally filtered by ``status``."""
        wanted = None if status is None else _validate_status(status)

        with self._lock:
            tasks = list(self._tasks.values())

        if wanted is not None:
            tasks = [task for task in tasks if task.status == wanted]

        tasks.sort(key=lambda task: (task.created_at, task.id), reverse=True)
        return tasks

    def create(
        self,
        title: str,
        description: str = "",
        due_date: str | None = None,
        status: str = DEFAULT_STATUS,
        source: str = DEFAULT_SOURCE,
    ) -> Task:
        """Validate input, persist a new task, and return it."""
        validated_title = _validate_title(title)
        validated_description = _validate_description(description)
        validated_due_date = _validate_due_date(due_date)
        validated_status = _validate_status(status)
        validated_source = _validate_source(source)

        now = self._clock()
        task = Task(
            id=uuid4().hex,
            title=validated_title,
            description=validated_description,
            due_date=validated_due_date,
            status=validated_status,
            source=validated_source,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._tasks[task.id] = task
            try:
                self._save()
            except Exception:
                del self._tasks[task.id]
                raise

        return task

    def update(self, task_id: str, **changes: Any) -> Task:
        """Apply a partial update and return the stored task."""
        key = _validate_task_id(task_id)

        if not changes:
            raise ValueError("at least one field must be provided")

        unknown = sorted(set(changes) - UPDATABLE_FIELDS)
        if unknown:
            raise ValueError("unknown fields: " + ", ".join(unknown))

        validated: dict[str, Any] = {}
        if "title" in changes:
            validated["title"] = _validate_title(changes["title"])
        if "description" in changes:
            validated["description"] = _validate_description(changes["description"])
        if "due_date" in changes:
            validated["due_date"] = _validate_due_date(changes["due_date"])
        if "status" in changes:
            validated["status"] = _validate_status(changes["status"])
        if "source" in changes:
            validated["source"] = _validate_source(changes["source"])

        with self._lock:
            current = self._tasks.get(key)
            if current is None:
                raise TaskNotFoundError(f"task not found: {key}")

            updated = replace(current, updated_at=self._clock(), **validated)
            self._tasks[key] = updated
            try:
                self._save()
            except Exception:
                self._tasks[key] = current
                raise

        return updated

    def delete(self, task_id: str) -> None:
        """Remove one task or raise ``TaskNotFoundError``."""
        key = _validate_task_id(task_id)

        with self._lock:
            current = self._tasks.pop(key, None)
            if current is None:
                raise TaskNotFoundError(f"task not found: {key}")

            try:
                self._save()
            except Exception:
                self._tasks[key] = current
                raise

    def _load(self) -> None:
        """Read the JSON file into memory, failing loudly on corrupt data."""
        if not self.path.exists():
            return

        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TaskStorageError(f"cannot read task store: {self.path}") from exc

        if not raw.strip():
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TaskStorageError(
                f"task store is not valid JSON: {self.path}"
            ) from exc

        if not isinstance(payload, list):
            raise TaskStorageError("task store must contain a JSON array")

        tasks: dict[str, Task] = {}
        for index, record in enumerate(payload):
            task = _task_from_record(record, index)
            tasks[task.id] = task

        self._tasks = tasks

    def _save(self) -> None:
        """Write every task atomically so a crash cannot truncate the file."""
        payload = [task.to_dict() for task in self._ordered_tasks()]
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temp_path = self.path.with_name(self.path.name + ".tmp")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(text, encoding="utf-8")
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise TaskStorageError(f"cannot write task store: {self.path}") from exc

    def _ordered_tasks(self) -> list[Task]:
        return sorted(
            self._tasks.values(),
            key=lambda task: (task.created_at, task.id),
        )


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _validate_title(title: Any) -> str:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    stripped = title.strip()
    if not stripped:
        raise ValueError("title must be a non-empty string")
    if len(stripped) > MAX_TITLE_LENGTH:
        raise ValueError(f"title must be at most {MAX_TITLE_LENGTH} characters")

    return stripped


def _validate_description(description: Any) -> str:
    if not isinstance(description, str):
        raise TypeError("description must be a string")

    stripped = description.strip()
    if len(stripped) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f"description must be at most {MAX_DESCRIPTION_LENGTH} characters"
        )

    return stripped


def _validate_due_date(due_date: Any) -> str | None:
    if due_date is None:
        return None
    if not isinstance(due_date, str):
        raise TypeError("due_date must be a string or None")

    candidate = due_date.strip()
    if not candidate:
        raise ValueError("due_date must not be blank")

    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        raise ValueError("due_date must be in YYYY-MM-DD format") from None

    if parsed.isoformat() != candidate:
        raise ValueError("due_date must be in YYYY-MM-DD format")

    return candidate


def _validate_status(status: Any) -> str:
    if not isinstance(status, str):
        raise TypeError("status must be a string")

    normalized = status.strip()
    if normalized not in TASK_STATUSES:
        raise ValueError("status must be one of: " + ", ".join(TASK_STATUSES))

    return normalized


def _validate_source(source: Any) -> str:
    if not isinstance(source, str):
        raise TypeError("source must be a string")

    normalized = source.strip()
    if normalized not in TASK_SOURCES:
        raise ValueError("source must be one of: " + ", ".join(TASK_SOURCES))

    return normalized


def _validate_task_id(task_id: Any) -> str:
    if not isinstance(task_id, str):
        raise TypeError("task_id must be a string")
    if not task_id.strip():
        raise ValueError("task_id must be a non-empty string")

    return task_id


def _validate_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")

    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from None

    return value


def _task_from_record(record: Any, index: int) -> Task:
    if not isinstance(record, dict):
        raise TaskStorageError(f"task record #{index} must be an object")

    missing = sorted(REQUIRED_RECORD_FIELDS - set(record))
    if missing:
        raise TaskStorageError(
            f"task record #{index} is missing: " + ", ".join(missing)
        )

    try:
        return Task(
            id=_validate_task_id(record["id"]),
            title=_validate_title(record["title"]),
            description=_validate_description(record.get("description", "")),
            due_date=_validate_due_date(record.get("due_date")),
            status=_validate_status(record["status"]),
            source=_validate_source(record["source"]),
            created_at=_validate_timestamp(record["created_at"], "created_at"),
            updated_at=_validate_timestamp(record["updated_at"], "updated_at"),
        )
    except (TypeError, ValueError) as exc:
        raise TaskStorageError(f"task record #{index} is invalid: {exc}") from exc


__all__ = [
    "DEFAULT_SOURCE",
    "DEFAULT_STATUS",
    "DEFAULT_STORE_PATH",
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "TASK_SOURCES",
    "TASK_SOURCE_AGENT",
    "TASK_SOURCE_CHAT",
    "TASK_SOURCE_MANUAL",
    "TASK_STATUSES",
    "TASK_STATUS_DONE",
    "TASK_STATUS_IN_PROGRESS",
    "TASK_STATUS_PENDING",
    "Task",
    "TaskNotFoundError",
    "TaskStorageError",
    "TaskStore",
    "UPDATABLE_FIELDS",
]