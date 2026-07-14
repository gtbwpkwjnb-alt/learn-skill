"""SQLite task history plus JSON task manifests for local recovery."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import TaskRecord, TaskStage, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskStore:
    """Persist task state independently from the legacy URL registry.

    The database makes task history searchable; each task directory receives a
    portable task.json so its media artifacts remain meaningful if moved.
    """

    def __init__(self, output_root: Path):
        self.output_root = Path(output_root)
        self.state_dir = self.output_root / ".learn"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "tasks.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        """Commit or roll back, then always release the SQLite file on Windows."""
        connection = self._connect()
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    raw_input TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    task_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_url ON tasks(canonical_url);
                CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at DESC);
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id);
                """
            )

    def task_dir(self, task_id: str) -> Path:
        return self.output_root / "_tasks" / task_id

    def create_or_resume(
        self,
        *,
        task_id: str,
        raw_input: str,
        canonical_url: str,
        platform: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskRecord:
        existing = self.get(task_id)
        if existing:
            return existing

        now = _now()
        task_dir = self.task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        payload = metadata or {}
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, raw_input, canonical_url, platform, task_dir,
                    status, stage, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id, raw_input, canonical_url, platform, str(task_dir),
                    TaskStatus.RUNNING, TaskStage.CREATED, now, now,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        self._write_manifest(task_id)
        self.transition(task_id, TaskStage.CREATED, data={"event": "created"})
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._record_from_row(row)

    def transition(
        self,
        task_id: str,
        stage: TaskStage,
        *,
        data: Optional[dict[str, Any]] = None,
        status: TaskStatus = TaskStatus.RUNNING,
        error: str = "",
    ) -> TaskRecord:
        current = self.get(task_id)
        if current is None:
            raise KeyError(f"Unknown learn task: {task_id}")
        now = _now()
        merged_metadata = dict(current.metadata)
        if data:
            merged_metadata.update(data)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET stage = ?, status = ?, updated_at = ?, metadata_json = ?, error = ?
                WHERE task_id = ?
                """,
                (stage, status, now, json.dumps(merged_metadata, ensure_ascii=False), error, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events (task_id, stage, status, occurred_at, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, stage, status, now, json.dumps(data or {}, ensure_ascii=False)),
            )
        self._write_manifest(task_id)
        return self.get(task_id)  # type: ignore[return-value]

    def complete(self, task_id: str, *, data: Optional[dict[str, Any]] = None) -> TaskRecord:
        return self.transition(task_id, TaskStage.COMPLETED, data=data, status=TaskStatus.COMPLETED)

    def fail(self, task_id: str, error: str, *, data: Optional[dict[str, Any]] = None) -> TaskRecord:
        return self.transition(task_id, TaskStage.FAILED, data=data, status=TaskStatus.FAILED, error=error)

    def skip(self, task_id: str, reason: str) -> TaskRecord:
        return self.transition(
            task_id, TaskStage.SKIPPED, data={"skip_reason": reason},
            status=TaskStatus.SKIPPED,
        )

    def events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT stage, status, occurred_at, data_json FROM task_events WHERE task_id = ? ORDER BY id",
                (task_id,),
            ).fetchall()
        return [
            {
                "stage": row["stage"], "status": row["status"],
                "occurred_at": row["occurred_at"], "data": json.loads(row["data_json"]),
            }
            for row in rows
        ]

    def _write_manifest(self, task_id: str) -> None:
        record = self.get(task_id)
        if record is None:
            return
        if record.metadata.get("local_artifacts_cleaned"):
            return
        manifest = {
            "task_id": record.task_id,
            "raw_input": record.raw_input,
            "canonical_url": record.canonical_url,
            "platform": record.platform,
            "status": record.status,
            "stage": record.stage,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.metadata,
            "error": record.error,
        }
        path = Path(record.task_dir) / "task.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"], raw_input=row["raw_input"],
            canonical_url=row["canonical_url"], platform=row["platform"],
            task_dir=row["task_dir"], status=TaskStatus(row["status"]),
            stage=TaskStage(row["stage"]), created_at=row["created_at"],
            updated_at=row["updated_at"], metadata=json.loads(row["metadata_json"]),
            error=row["error"],
        )
