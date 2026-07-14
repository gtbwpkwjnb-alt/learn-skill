"""Optional Bilibili subtitle provider backed by the local bilibili-cli."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Optional


@dataclass
class BilibiliSubtitleResult:
    title: str
    author: str
    duration_sec: int
    transcript: str
    command: str


def find_bili_command() -> Optional[str]:
    """Find bili on PATH or next to the Python interpreter used by learn."""
    configured = (Path(value) for value in [os.environ.get("BILI_CLI_BIN", "")] if value)
    candidates = [*configured]
    resolved = shutil.which("bili")
    if resolved:
        candidates.append(Path(resolved))
    scripts_dir = Path(sys.executable).resolve().parent / "Scripts"
    candidates.extend([scripts_dir / "bili.exe", scripts_dir / "bili"])
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _seconds(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _timestamp(value: Any) -> str:
    seconds = _seconds(value)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _subtitle_segments(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("segments", "body", "items", "subtitles", "data"):
        found = _subtitle_segments(value.get(key))
        if found:
            return found
    return []


def parse_bili_payload(payload: dict[str, Any], command: str = "bili") -> Optional[BilibiliSubtitleResult]:
    """Normalize the stable bilibili-cli JSON envelope to learn's transcript shape."""
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return None
    video = data.get("video", data)
    if not isinstance(video, dict):
        video = {}
    subtitle = data.get("subtitle", video.get("subtitle", data.get("subtitles")))
    if isinstance(subtitle, str) and subtitle.strip():
        transcript = subtitle.strip()
    else:
        lines: list[str] = []
        for item in _subtitle_segments(subtitle):
            text = str(item.get("content", item.get("text", item.get("body", "")))).strip()
            if not text:
                continue
            start = item.get("from", item.get("start", item.get("start_time", item.get("timestamp", 0))))
            lines.append(f"[{_timestamp(start)}] {text}")
        transcript = "\n".join(lines)
    if not transcript:
        return None

    owner = video.get("owner", {})
    author = ""
    if isinstance(owner, dict):
        author = str(owner.get("name", owner.get("uname", "")))
    author = author or str(video.get("author", video.get("uploader", "")))
    return BilibiliSubtitleResult(
        title=str(video.get("title", data.get("title", ""))),
        author=author,
        duration_sec=_seconds(video.get("duration", data.get("duration", 0))),
        transcript=transcript,
        command=command,
    )


def fetch_bilibili_subtitles(
    url: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 90,
) -> tuple[Optional[BilibiliSubtitleResult], Optional[str]]:
    """Fetch a timeline transcript through bilibili-cli without changing login state."""
    command = find_bili_command()
    if not command:
        return None, "未检测到 bilibili-cli（可选 provider）"
    completed = runner(
        [command, "video", url, "--subtitle-timeline", "--json"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误").strip()
        return None, f"bilibili-cli 失败: {detail[:300]}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return None, f"bilibili-cli 未返回 JSON: {error}"
    result = parse_bili_payload(payload, command)
    if not result:
        return None, "bilibili-cli 未返回可用字幕（可能需要登录或该视频没有字幕轨）"
    return result, None
