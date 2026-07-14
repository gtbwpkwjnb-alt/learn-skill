"""Douyin artifact manifests independent of the current extraction backend."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DouyinProvider:
    platform = "douyin"
    supported_platforms = frozenset({"douyin", "tiktok"})

    def supports(self, platform: str) -> bool:
        return platform in self.supported_platforms

    def write_source_manifest(
        self,
        task_dir: Path,
        *,
        raw_input: str,
        canonical_url: str,
        normalized_link: dict[str, Any],
    ) -> Path:
        """Record source identity before any downloader mutates the task directory."""
        payload = {
            "provider": self.platform,
            "raw_input": raw_input,
            "canonical_url": canonical_url,
            "normalized_link": normalized_link,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = Path(task_dir) / "source.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def build_artifact_manifest(self, task_dir: Path, summary_path: Path) -> dict[str, Any]:
        """Describe completed media artifacts using paths relative to one task."""
        task_dir = Path(task_dir)
        files: list[str] = []
        for candidate in sorted(task_dir.rglob("*")):
            if candidate.is_file() and candidate.name not in {"task.json", "artifacts.json"}:
                files.append(candidate.relative_to(task_dir).as_posix())
        payload = {
            "provider": self.platform,
            "summary": summary_path.relative_to(task_dir).as_posix(),
            "files": files,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = task_dir / "artifacts.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
