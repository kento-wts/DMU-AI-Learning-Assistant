"""HTTP endpoints for the standalone task management module.

The router is registered by ``backend.main`` with two lines and does not touch
the existing chat flow.
"""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status

from .models import (
    CreateTaskRequest,
    TaskListResponse,
    TaskResponse,
    TaskStatus,
    UpdateTaskRequest,
)
from .store import TaskNotFoundError, TaskStore

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_store: TaskStore | None = None
_store_lock = threading.Lock()


def get_task_store() -> TaskStore:
    """Return the process-wide task store, creating it on first use.

    Tests override this dependency instead of touching the file system.
    """
    global _store

    if _store is None:
        with _store_lock:
            if _store is None:
                _store = TaskStore()

    return _store


TaskStoreDep = Annotated[TaskStore, Depends(get_task_store)]


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "",
    status_code=http_status.HTTP_201_CREATED,
    response_model=TaskResponse,
    summary="Create a task",
)
def create_task(payload: CreateTaskRequest, store: TaskStoreDep) -> TaskResponse:
    try:
        task = store.create(
            title=payload.title,
            description=payload.description,
            due_date=payload.due_date,
            status=payload.status,
            source=payload.source,
        )
    except (TypeError, ValueError) as exc:
        raise _bad_request(exc) from exc

    return TaskResponse.from_task(task)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
)
def list_tasks(
    store: TaskStoreDep,
    status: TaskStatus | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    try:
        tasks = store.list(status)
    except (TypeError, ValueError) as exc:
        raise _bad_request(exc) from exc

    page = tasks[offset : offset + limit]

    return TaskListResponse(
        items=[TaskResponse.from_task(task) for task in page],
        total=len(tasks),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get one task",
)
def get_task(task_id: str, store: TaskStoreDep) -> TaskResponse:
    try:
        task = store.get(task_id)
    except TaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except (TypeError, ValueError) as exc:
        raise _bad_request(exc) from exc

    return TaskResponse.from_task(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
)
def update_task(
    task_id: str,
    payload: UpdateTaskRequest,
    store: TaskStoreDep,
) -> TaskResponse:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise _bad_request(ValueError("at least one field must be provided"))

    try:
        task = store.update(task_id, **changes)
    except TaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except (TypeError, ValueError) as exc:
        raise _bad_request(exc) from exc

    return TaskResponse.from_task(task)


@router.delete(
    "/{task_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a task",
)
def delete_task(task_id: str, store: TaskStoreDep) -> Response:
    try:
        store.delete(task_id)
    except TaskNotFoundError as exc:
        raise _not_found(exc) from exc
    except (TypeError, ValueError) as exc:
        raise _bad_request(exc) from exc

    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "get_task_store",
    "router",
]