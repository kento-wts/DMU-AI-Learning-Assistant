"""Interface tests for the task management HTTP endpoints.

The router is mounted on a throwaway FastAPI app so these tests never import
``backend.main`` and therefore need no API key, Chroma store, or network.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tasks.models import TaskSource, TaskStatus
from backend.tasks.router import DEFAULT_PAGE_SIZE, get_task_store, router
from backend.tasks.store import (
    TASK_SOURCES,
    TASK_STATUSES,
    TASK_STATUS_DONE,
    TASK_STATUS_IN_PROGRESS,
    TaskStore,
)

BASE_URL = "/api/tasks"
UNICODE_TITLE = "\u4e2d\u6587\u4efb\u52a1"

EXPECTED_TASK_FIELDS = sorted(
    [
        "id",
        "title",
        "description",
        "due_date",
        "status",
        "source",
        "created_at",
        "updated_at",
    ]
)


class AutoClock:
    """Return strictly increasing ISO 8601 timestamps."""

    def __init__(self) -> None:
        self._base = datetime(2026, 10, 16, 8, 0, 0, tzinfo=timezone.utc)
        self._step = 0

    def __call__(self) -> str:
        stamp = self._base + timedelta(seconds=self._step)
        self._step += 1
        return stamp.isoformat()


class TaskRouterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "tasks.json"
        self.store = TaskStore(path=self.path, clock=AutoClock())

        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_task_store] = lambda: self.store

        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self._tmp.cleanup()

    def post_task(self, **overrides: object):
        payload: dict[str, object] = {"title": "Write lab report"}
        payload.update(overrides)
        return self.client.post(BASE_URL, json=payload)

    def create_task(self, **overrides: object) -> dict:
        response = self.post_task(**overrides)
        self.assertEqual(response.status_code, 201)
        return response.json()


class TaskCreateEndpointTests(TaskRouterTestCase):
    def test_create_returns_201_and_defaults(self) -> None:
        response = self.post_task()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(sorted(body), EXPECTED_TASK_FIELDS)
        self.assertEqual(body["title"], "Write lab report")
        self.assertEqual(body["description"], "")
        self.assertIsNone(body["due_date"])
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["source"], "manual")
        self.assertTrue(body["id"])
        self.assertEqual(body["created_at"], body["updated_at"])

    def test_create_persists_every_field(self) -> None:
        body = self.create_task(
            title="Prepare slides",
            description="Ten pages",
            due_date="2026-11-01",
            status="in_progress",
            source="chat",
        )

        self.assertEqual(body["description"], "Ten pages")
        self.assertEqual(body["due_date"], "2026-11-01")
        self.assertEqual(body["status"], "in_progress")
        self.assertEqual(body["source"], "chat")

    def test_create_writes_to_the_store(self) -> None:
        body = self.create_task()

        stored = self.store.get(body["id"])
        self.assertEqual(stored.title, "Write lab report")

    def test_create_round_trips_unicode_title(self) -> None:
        body = self.create_task(title=UNICODE_TITLE)

        self.assertEqual(body["title"], UNICODE_TITLE)
        self.assertEqual(self.store.get(body["id"]).title, UNICODE_TITLE)

    def test_create_rejects_missing_title(self) -> None:
        response = self.client.post(BASE_URL, json={})

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_blank_title(self) -> None:
        response = self.post_task(title="   ")

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_overlong_title(self) -> None:
        response = self.post_task(title="x" * 201)

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_unknown_field(self) -> None:
        response = self.post_task(colour="red")

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_unknown_status(self) -> None:
        response = self.post_task(status="doing")

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_unknown_source(self) -> None:
        response = self.post_task(source="email")

        self.assertEqual(response.status_code, 422)

    def test_create_rejects_loosely_formatted_due_date(self) -> None:
        for candidate in ("2026-1-1", "20260101", "not-a-date"):
            with self.subTest(candidate=candidate):
                response = self.post_task(due_date=candidate)
                self.assertEqual(response.status_code, 422)

    def test_create_rejects_impossible_calendar_date(self) -> None:
        response = self.post_task(due_date="2026-02-30")

        self.assertEqual(response.status_code, 422)

    def test_create_accepts_explicit_null_due_date(self) -> None:
        response = self.post_task(due_date=None)

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["due_date"])


class TaskListEndpointTests(TaskRouterTestCase):
    def test_list_is_empty_initially(self) -> None:
        response = self.client.get(BASE_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["limit"], DEFAULT_PAGE_SIZE)
        self.assertEqual(response.json()["offset"], 0)

    def test_list_returns_newest_first(self) -> None:
        first = self.create_task(title="first")
        second = self.create_task(title="second")

        items = self.client.get(BASE_URL).json()["items"]

        self.assertEqual([item["id"] for item in items], [second["id"], first["id"]])

    def test_list_filters_by_status(self) -> None:
        pending = self.create_task(title="pending")
        done = self.create_task(title="done", status=TASK_STATUS_DONE)

        items = self.client.get(BASE_URL, params={"status": TASK_STATUS_DONE}).json()

        self.assertEqual(items["total"], 1)
        self.assertEqual([item["id"] for item in items["items"]], [done["id"]])
        self.assertNotEqual(items["items"][0]["id"], pending["id"])

    def test_list_filters_by_in_progress(self) -> None:
        self.create_task(title="pending")
        moving = self.create_task(title="moving", status=TASK_STATUS_IN_PROGRESS)

        items = self.client.get(
            BASE_URL, params={"status": TASK_STATUS_IN_PROGRESS}
        ).json()

        self.assertEqual([item["id"] for item in items["items"]], [moving["id"]])

    def test_list_paginates(self) -> None:
        created = [self.create_task(title=f"task {index}") for index in range(3)]

        first_page = self.client.get(BASE_URL, params={"limit": 2}).json()
        second_page = self.client.get(BASE_URL, params={"limit": 2, "offset": 2}).json()

        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["items"]), 2)
        self.assertEqual(first_page["limit"], 2)
        self.assertEqual(len(second_page["items"]), 1)
        self.assertEqual(second_page["offset"], 2)

        seen = {item["id"] for item in first_page["items"] + second_page["items"]}
        self.assertEqual(seen, {task["id"] for task in created})

    def test_list_rejects_unknown_status(self) -> None:
        response = self.client.get(BASE_URL, params={"status": "archived"})

        self.assertEqual(response.status_code, 422)

    def test_list_rejects_limit_above_maximum(self) -> None:
        response = self.client.get(BASE_URL, params={"limit": 5000})

        self.assertEqual(response.status_code, 422)

    def test_list_rejects_zero_limit(self) -> None:
        response = self.client.get(BASE_URL, params={"limit": 0})

        self.assertEqual(response.status_code, 422)

    def test_list_rejects_negative_offset(self) -> None:
        response = self.client.get(BASE_URL, params={"offset": -1})

        self.assertEqual(response.status_code, 422)


class TaskGetEndpointTests(TaskRouterTestCase):
    def test_get_returns_task(self) -> None:
        created = self.create_task(title="find me")

        response = self.client.get(f"{BASE_URL}/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created)

    def test_get_unknown_id_returns_404(self) -> None:
        response = self.client.get(f"{BASE_URL}/does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())


class TaskUpdateEndpointTests(TaskRouterTestCase):
    def test_update_changes_title(self) -> None:
        created = self.create_task(title="old")

        response = self.client.patch(f"{BASE_URL}/{created['id']}", json={"title": "new"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "new")
        self.assertEqual(body["created_at"], created["created_at"])
        self.assertGreater(body["updated_at"], created["updated_at"])

    def test_update_sets_status_to_done(self) -> None:
        created = self.create_task()

        response = self.client.patch(
            f"{BASE_URL}/{created['id']}", json={"status": TASK_STATUS_DONE}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], TASK_STATUS_DONE)

    def test_update_applies_only_supplied_fields(self) -> None:
        created = self.create_task(title="keep me", description="keep this too")

        body = self.client.patch(
            f"{BASE_URL}/{created['id']}", json={"status": TASK_STATUS_IN_PROGRESS}
        ).json()

        self.assertEqual(body["title"], "keep me")
        self.assertEqual(body["description"], "keep this too")

    def test_update_clears_due_date_with_null(self) -> None:
        created = self.create_task(due_date="2026-11-01")

        body = self.client.patch(
            f"{BASE_URL}/{created['id']}", json={"due_date": None}
        ).json()

        self.assertIsNone(body["due_date"])

    def test_update_without_fields_returns_400(self) -> None:
        created = self.create_task()

        response = self.client.patch(f"{BASE_URL}/{created['id']}", json={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_update_rejects_unknown_field(self) -> None:
        created = self.create_task()

        response = self.client.patch(f"{BASE_URL}/{created['id']}", json={"colour": "red"})

        self.assertEqual(response.status_code, 422)

    def test_update_rejects_blank_title(self) -> None:
        created = self.create_task()

        response = self.client.patch(f"{BASE_URL}/{created['id']}", json={"title": "  "})

        self.assertEqual(response.status_code, 422)

    def test_update_rejects_unknown_status(self) -> None:
        created = self.create_task()

        response = self.client.patch(f"{BASE_URL}/{created['id']}", json={"status": "doing"})

        self.assertEqual(response.status_code, 422)

    def test_update_unknown_id_returns_404(self) -> None:
        response = self.client.patch(f"{BASE_URL}/missing", json={"title": "new"})

        self.assertEqual(response.status_code, 404)


class TaskDeleteEndpointTests(TaskRouterTestCase):
    def test_delete_returns_204_and_removes_task(self) -> None:
        created = self.create_task()

        response = self.client.delete(f"{BASE_URL}/{created['id']}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get(f"{BASE_URL}/{created['id']}").status_code, 404)

    def test_delete_unknown_id_returns_404(self) -> None:
        response = self.client.delete(f"{BASE_URL}/missing")

        self.assertEqual(response.status_code, 404)


class TaskSchemaConsistencyTests(unittest.TestCase):
    def test_status_literals_match_domain_constants(self) -> None:
        self.assertEqual(set(get_args(TaskStatus)), set(TASK_STATUSES))

    def test_source_literals_match_domain_constants(self) -> None:
        self.assertEqual(set(get_args(TaskSource)), set(TASK_SOURCES))


if __name__ == "__main__":
    unittest.main()