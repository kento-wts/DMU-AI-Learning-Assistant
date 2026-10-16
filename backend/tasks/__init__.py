"""Standalone task management module.

Layering rule: ``backend.tasks.store`` is the domain layer and has no
third-party imports, so it can be imported and tested without the web
framework. The HTTP layer lives in ``backend.tasks.router`` and is registered
by ``backend.main``; it is intentionally not re-exported here.
"""

from .store import (
    DEFAULT_SOURCE,
    DEFAULT_STATUS,
    DEFAULT_STORE_PATH,
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    TASK_SOURCES,
    TASK_SOURCE_AGENT,
    TASK_SOURCE_CHAT,
    TASK_SOURCE_MANUAL,
    TASK_STATUSES,
    TASK_STATUS_DONE,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    Task,
    TaskNotFoundError,
    TaskStorageError,
    TaskStore,
)

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
]