"""Stable data models for recoverable learn tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStage(StrEnum):
    CREATED = "created"
    NORMALIZED = "normalized"
    EXTRACTING = "extracting"
    MEDIA_READY = "media_ready"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    EXPORTING = "exporting"
    INDEXED = "indexed"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    raw_input: str
    canonical_url: str
    platform: str
    task_dir: str
    status: TaskStatus
    stage: TaskStage
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""
