"""Pydantic schemas for the task management HTTP API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import (
    DEFAULT_SOURCE,
    DEFAULT_STATUS,
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    Task,
)

TaskStatus = Literal["pending", "in_progress", "done"]
TaskSource = Literal["manual", "chat", "agent"]

_DUE_DATE_MESSAGE = "due_date must be in YYYY-MM-DD format"


class CreateTaskRequest(BaseModel):
    """Request body for creating a task."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    due_date: str | None = None
    status: TaskStatus = DEFAULT_STATUS
    source: TaskSource = DEFAULT_SOURCE

    @field_validator("title", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def _reject_blank_title(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("due_date")
    @classmethod
    def _validate_due_date(cls, value: str | None) -> str | None:
        return _normalise_due_date(value)


class UpdateTaskRequest(BaseModel):
    """Request body for a partial task update.

    Only the fields explicitly present in the request body are applied, which
    is why the router uses ``model_dump(exclude_unset=True)``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    due_date: str | None = None
    status: TaskStatus | None = None
    source: TaskSource | None = None

    @field_validator("title", "description")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def _reject_blank_title(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("due_date")
    @classmethod
    def _validate_due_date(cls, value: str | None) -> str | None:
        return _normalise_due_date(value)


class TaskResponse(BaseModel):
    """One task as returned by the API."""

    id: str
    title: str
    description: str
    due_date: str | None
    status: str
    source: str
    created_at: str
    updated_at: str

    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        return cls(**task.to_dict())


class TaskListResponse(BaseModel):
    """A page of tasks plus the total number of matching records."""

    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


def _normalise_due_date(value: str | None) -> str | None:
    """Accept only a real calendar date written as ``YYYY-MM-DD``."""
    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        raise ValueError(_DUE_DATE_MESSAGE) from None

    if parsed.isoformat() != candidate:
        raise ValueError(_DUE_DATE_MESSAGE)

    return candidate


__all__ = [
    "CreateTaskRequest",
    "TaskListResponse",
    "TaskResponse",
    "TaskSource",
    "TaskStatus",
    "UpdateTaskRequest",
]