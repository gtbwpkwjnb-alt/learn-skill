from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from learn_core.models import TaskStage, TaskStatus  # noqa: E402
from learn_core.task_store import TaskStore  # noqa: E402


class TaskStoreTests(unittest.TestCase):
    def test_task_lifecycle_is_persisted_in_sqlite_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(Path(tmp))
            created = store.create_or_resume(
                task_id="abc123", raw_input="分享文案", canonical_url="https://example.com/video/1",
                platform="douyin", metadata={"method": "playwright"},
            )
            self.assertEqual(created.stage, TaskStage.CREATED)
            self.assertEqual(created.status, TaskStatus.RUNNING)

            resumed = store.create_or_resume(
                task_id="abc123", raw_input="new input", canonical_url="https://ignored",
                platform="douyin",
            )
            self.assertEqual(resumed.raw_input, "分享文案")

            done = store.complete("abc123", data={"note_path": "summary.md"})
            self.assertEqual(done.status, TaskStatus.COMPLETED)
            self.assertEqual(done.metadata["note_path"], "summary.md")
            self.assertEqual(len(store.events("abc123")), 2)

            manifest = json.loads((Path(tmp) / "_tasks" / "abc123" / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "completed")
            self.assertEqual(manifest["metadata"]["method"], "playwright")

    def test_cleaned_task_does_not_recreate_its_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = TaskStore(root)
            store.create_or_resume(
                task_id="cleaned", raw_input="分享文案", canonical_url="https://example.com/video",
                platform="douyin",
            )
            task_dir = root / "_tasks" / "cleaned"
            shutil.rmtree(task_dir)
            completed = store.complete("cleaned", data={"local_artifacts_cleaned": True})

            self.assertTrue(completed.metadata["local_artifacts_cleaned"])
            self.assertFalse(task_dir.exists())
