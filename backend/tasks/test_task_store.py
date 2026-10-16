"""Tests for the task domain store.

These tests import only the standard library plus ``backend.tasks.store``, so
they run without installing FastAPI or any other third-party package.
"""

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.tasks.store import (
    DEFAULT_SOURCE,
    DEFAULT_STATUS,
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    TASK_SOURCE_AGENT,
    TASK_SOURCE_CHAT,
    TASK_STATUS_DONE,
    TASK_STATUS_IN_PROGRESS,
    Task,
    TaskNotFoundError,
    TaskStorageError,
    TaskStore,
)

UNICODE_TITLE = "\u4efb\u52a1\u6807\u9898"


class AutoClock:
    """Return strictly increasing ISO 8601 timestamps."""

    def __init__(self) -> None:
        self._base = datetime(2026, 10, 16, 8, 0, 0, tzinfo=timezone.utc)
        self._step = 0

    def __call__(self) -> str:
        stamp = self._base + timedelta(seconds=self._step)
        self._step += 1
        return stamp.isoformat()


class TaskStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "tasks.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_store(self, with_clock: bool = True) -> TaskStore:
        clock = AutoClock() if with_clock else None
        return TaskStore(path=self.path, clock=clock)


class TaskCreateTests(TaskStoreTestCase):
    def test_create_returns_task_with_defaults(self) -> None:
        store = self.make_store()

        task = store.create("Write lab report")

        self.assertIsInstance(task, Task)
        self.assertEqual(task.title, "Write lab report")
        self.assertEqual(task.description, "")
        self.assertIsNone(task.due_date)
        self.assertEqual(task.status, DEFAULT_STATUS)
        self.assertEqual(task.source, DEFAULT_SOURCE)
        self.assertEqual(len(store), 1)

    def test_create_stores_every_provided_field(self) -> None:
        store = self.make_store()

        task = store.create(
            "Prepare slides",
            description="Ten pages at most",
            due_date="2026-11-01",
            status=TASK_STATUS_IN_PROGRESS,
            source=TASK_SOURCE_CHAT,
        )

        self.assertEqual(task.description, "Ten pages at most")
        self.assertEqual(task.due_date, "2026-11-01")
        self.assertEqual(task.status, TASK_STATUS_IN_PROGRESS)
        self.assertEqual(task.source, TASK_SOURCE_CHAT)

    def test_create_assigns_unique_ids(self) -> None:
        store = self.make_store()

        first = store.create("one")
        second = store.create("two")

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(store), 2)

    def test_create_trims_surrounding_whitespace(self) -> None:
        store = self.make_store()

        task = store.create("   padded title   ", description="  body  ")

        self.assertEqual(task.title, "padded title")
        self.assertEqual(task.description, "body")

    def test_create_rejects_non_string_title(self) -> None:
        store = self.make_store()

        with self.assertRaises(TypeError):
            store.create(123)  # type: ignore[arg-type]

    def test_create_rejects_blank_title(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("   ")

    def test_create_rejects_overlong_title(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("x" * (MAX_TITLE_LENGTH + 1))

    def test_create_rejects_non_string_description(self) -> None:
        store = self.make_store()

        with self.assertRaises(TypeError):
            store.create("title", description=None)  # type: ignore[arg-type]

    def test_create_rejects_overlong_description(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("title", description="x" * (MAX_DESCRIPTION_LENGTH + 1))

    def test_create_rejects_unknown_status(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("title", status="doing")

    def test_create_rejects_non_string_status(self) -> None:
        store = self.make_store()

        with self.assertRaises(TypeError):
            store.create("title", status=1)  # type: ignore[arg-type]

    def test_create_rejects_unknown_source(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("title", source="email")

    def test_create_accepts_every_known_source(self) -> None:
        store = self.make_store()

        for source in (TASK_SOURCE_AGENT, TASK_SOURCE_CHAT):
            self.assertEqual(store.create("task", source=source).source, source)

    def test_create_rejects_loosely_formatted_due_date(self) -> None:
        store = self.make_store()

        for candidate in ("2026-1-1", "20260101", "2026/11/01", "not-a-date", ""):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    store.create("title", due_date=candidate)

    def test_create_rejects_impossible_calendar_date(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create("title", due_date="2026-02-30")

    def test_create_rejects_non_string_due_date(self) -> None:
        store = self.make_store()

        with self.assertRaises(TypeError):
            store.create("title", due_date=20261101)  # type: ignore[arg-type]

    def test_create_records_timestamps_from_the_clock(self) -> None:
        store = self.make_store()

        task = store.create("title")

        self.assertEqual(task.created_at, task.updated_at)
        self.assertTrue(task.created_at.startswith("2026-10-16T08:00:00"))


class TaskQueryTests(TaskStoreTestCase):
    def test_get_returns_stored_task(self) -> None:
        store = self.make_store()
        created = store.create("title")

        self.assertEqual(store.get(created.id), created)

    def test_get_raises_for_unknown_id(self) -> None:
        store = self.make_store()

        with self.assertRaises(TaskNotFoundError):
            store.get("missing")

    def test_get_rejects_blank_id(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.get("  ")

    def test_get_rejects_non_string_id(self) -> None:
        store = self.make_store()

        with self.assertRaises(TypeError):
            store.get(None)  # type: ignore[arg-type]

    def test_list_is_empty_initially(self) -> None:
        self.assertEqual(self.make_store().list(), [])

    def test_list_returns_newest_first(self) -> None:
        store = self.make_store()
        first = store.create("first")
        second = store.create("second")
        third = store.create("third")

        self.assertEqual(
            [task.id for task in store.list()],
            [third.id, second.id, first.id],
        )

    def test_list_filters_by_status(self) -> None:
        store = self.make_store()
        pending = store.create("pending one")
        done = store.create("done one", status=TASK_STATUS_DONE)

        self.assertEqual([task.id for task in store.list(TASK_STATUS_DONE)], [done.id])
        self.assertEqual([task.id for task in store.list(DEFAULT_STATUS)], [pending.id])

    def test_list_rejects_unknown_status_filter(self) -> None:
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.list("archived")

    def test_len_counts_stored_tasks(self) -> None:
        store = self.make_store()

        store.create("one")
        store.create("two")

        self.assertEqual(len(store), 2)


class TaskUpdateTests(TaskStoreTestCase):
    def test_update_changes_title_and_refreshes_updated_at(self) -> None:
        store = self.make_store()
        created = store.create("old title")

        updated = store.update(created.id, title="new title")

        self.assertEqual(updated.title, "new title")
        self.assertEqual(updated.created_at, created.created_at)
        self.assertGreater(updated.updated_at, created.updated_at)
        self.assertEqual(store.get(created.id).title, "new title")

    def test_update_changes_status(self) -> None:
        store = self.make_store()
        created = store.create("title")

        updated = store.update(created.id, status=TASK_STATUS_DONE)

        self.assertEqual(updated.status, TASK_STATUS_DONE)

    def test_update_clears_due_date_with_none(self) -> None:
        store = self.make_store()
        created = store.create("title", due_date="2026-11-01")

        updated = store.update(created.id, due_date=None)

        self.assertIsNone(updated.due_date)

    def test_update_rejects_unknown_field(self) -> None:
        store = self.make_store()
        created = store.create("title")

        with self.assertRaises(ValueError):
            store.update(created.id, colour="red")

    def test_update_rejects_immutable_fields(self) -> None:
        store = self.make_store()
        created = store.create("title")

        with self.assertRaises(ValueError):
            store.update(created.id, id="hijacked")

    def test_update_rejects_empty_changes(self) -> None:
        store = self.make_store()
        created = store.create("title")

        with self.assertRaises(ValueError):
            store.update(created.id)

    def test_update_validates_the_new_value(self) -> None:
        store = self.make_store()
        created = store.create("title")

        with self.assertRaises(ValueError):
            store.update(created.id, status="doing")

    def test_update_raises_for_unknown_id(self) -> None:
        store = self.make_store()

        with self.assertRaises(TaskNotFoundError):
            store.update("missing", title="new")

    def test_update_does_not_write_when_validation_fails(self) -> None:
        store = self.make_store()
        created = store.create("title")
        before = self.path.read_text(encoding="utf-8")

        with self.assertRaises(ValueError):
            store.update(created.id, title="")

        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


class TaskDeleteTests(TaskStoreTestCase):
    def test_delete_removes_task(self) -> None:
        store = self.make_store()
        created = store.create("title")

        store.delete(created.id)

        self.assertEqual(len(store), 0)
        with self.assertRaises(TaskNotFoundError):
            store.get(created.id)

    def test_delete_raises_for_unknown_id(self) -> None:
        store = self.make_store()

        with self.assertRaises(TaskNotFoundError):
            store.delete("missing")


class TaskPersistenceTests(TaskStoreTestCase):
    def test_tasks_survive_reload(self) -> None:
        store = self.make_store()
        created = store.create("persist me", description="body", due_date="2026-11-01")

        reloaded = self.make_store(with_clock=False)

        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded.get(created.id), created)

    def test_updates_survive_reload(self) -> None:
        store = self.make_store()
        created = store.create("title")
        store.update(created.id, status=TASK_STATUS_DONE)

        reloaded = self.make_store(with_clock=False)

        self.assertEqual(reloaded.get(created.id).status, TASK_STATUS_DONE)

    def test_deletions_survive_reload(self) -> None:
        store = self.make_store()
        created = store.create("title")
        store.delete(created.id)

        reloaded = self.make_store(with_clock=False)

        self.assertEqual(len(reloaded), 0)

    def test_unicode_title_survives_reload(self) -> None:
        store = self.make_store()
        created = store.create(UNICODE_TITLE)

        raw = self.path.read_text(encoding="utf-8")
        reloaded = self.make_store(with_clock=False)

        self.assertIn(UNICODE_TITLE, raw)
        self.assertEqual(reloaded.get(created.id).title, UNICODE_TITLE)

    def test_store_file_is_a_json_array(self) -> None:
        store = self.make_store()
        store.create("title")

        payload = json.loads(self.path.read_text(encoding="utf-8"))

        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["title"], "title")

    def test_save_leaves_no_temporary_file(self) -> None:
        store = self.make_store()
        store.create("title")

        self.assertFalse((self.path.parent / (self.path.name + ".tmp")).exists())

    def test_missing_file_loads_as_empty_store(self) -> None:
        reloaded = self.make_store(with_clock=False)

        self.assertEqual(len(reloaded), 0)

    def test_blank_file_loads_as_empty_store(self) -> None:
        self.path.write_text("   \n", encoding="utf-8")

        reloaded = self.make_store(with_clock=False)

        self.assertEqual(len(reloaded), 0)

    def test_load_rejects_invalid_json(self) -> None:
        self.path.write_text("not json at all", encoding="utf-8")

        with self.assertRaises(TaskStorageError):
            self.make_store(with_clock=False)

    def test_load_rejects_non_array_payload(self) -> None:
        self.path.write_text('{"tasks": []}', encoding="utf-8")

        with self.assertRaises(TaskStorageError):
            self.make_store(with_clock=False)

    def test_load_rejects_record_missing_required_field(self) -> None:
        self.path.write_text('[{"id": "abc"}]', encoding="utf-8")

        with self.assertRaises(TaskStorageError):
            self.make_store(with_clock=False)

    def test_load_rejects_record_with_invalid_status(self) -> None:
        record = {
            "id": "abc",
            "title": "title",
            "description": "",
            "due_date": None,
            "status": "nope",
            "source": "manual",
            "created_at": "2026-10-16T08:00:00+00:00",
            "updated_at": "2026-10-16T08:00:00+00:00",
        }
        self.path.write_text(json.dumps([record]), encoding="utf-8")

        with self.assertRaises(TaskStorageError):
            self.make_store(with_clock=False)


class TaskModelTests(TaskStoreTestCase):
    def test_task_is_immutable(self) -> None:
        store = self.make_store()
        task = store.create("title")

        with self.assertRaises(FrozenInstanceError):
            task.title = "changed"  # type: ignore[misc]

    def test_task_to_dict_exposes_all_fields(self) -> None:
        store = self.make_store()
        task = store.create("title")

        self.assertEqual(
            sorted(task.to_dict()),
            [
                "created_at",
                "description",
                "due_date",
                "id",
                "source",
                "status",
                "title",
                "updated_at",
            ],
        )


if __name__ == "__main__":
    unittest.main()