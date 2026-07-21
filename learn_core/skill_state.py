"""Persistent environment checks and extraction routing for learn."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STATE_SCHEMA = 1
ENV_CACHE_TTL = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat(timespec="seconds")


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _binary_version(command: str, args: list[str] | None = None) -> str:
    executable = shutil.which(command)
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, *(args or ["-version"])], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5, check=False,
        )
        first_line = (result.stdout or result.stderr).splitlines()
        return first_line[0].strip() if first_line else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _module_check(module: str, distribution: str, level: str, impact: str) -> dict[str, Any]:
    found = importlib.util.find_spec(module) is not None
    return {
        "found": found,
        "version": _package_version(distribution) if found else "",
        "level": level,
        "impact": "" if found else impact,
    }


class SkillState:
    """Own `.skill_state.json` and make routing decisions from observed results."""

    def __init__(self, output_root: Path, skill_version: str = "5.2.0"):
        self.output_root = Path(output_root)
        self.path = self.output_root / ".skill_state.json"
        self.skill_version = skill_version
        self.data = self._load()

    def _default(self) -> dict[str, Any]:
        return {
            "schema": STATE_SCHEMA,
            "skill_version": self.skill_version,
            "last_check": "",
            "env": {},
            "platform_memory": {},
            "stats": {
                "total_extractions": 0,
                "successful": 0,
                "failed": 0,
                "last_extraction": "",
            },
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
                return self._default()
            payload.setdefault("env", {})
            payload.setdefault("platform_memory", {})
            payload.setdefault("stats", self._default()["stats"])
            payload["skill_version"] = self.skill_version
            return payload
        except (OSError, json.JSONDecodeError):
            return self._default()

    def save(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _cache_fresh(self) -> bool:
        raw = str(self.data.get("last_check", ""))
        if not raw or not self.data.get("env"):
            return False
        try:
            checked = datetime.fromisoformat(raw)
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            return _now() - checked < ENV_CACHE_TTL
        except ValueError:
            return False

    def check_environment(self, *, force: bool = False) -> dict[str, Any]:
        if not force and self._cache_fresh():
            return self.data["env"]

        ffmpeg_path = shutil.which("ffmpeg") or ""
        yt_dlp = _module_check("yt_dlp", "yt-dlp", "auxiliary", "下载器不可用，将依赖平台兜底")
        playwright = _module_check("playwright", "playwright", "douyin_required", "抖音浏览器兜底不可用")
        whisper = _module_check("faster_whisper", "faster-whisper", "required", "无字幕内容无法转写")
        scenedetect = _module_check("scenedetect", "scenedetect", "depth_optional", "跳过关键帧")
        browser_cookie3 = _module_check("browser_cookie3", "browser-cookie3", "optional", "跳过浏览器 Cookie")

        try:
            from scripts.ocr_provider import (
                paddleocr_installed, ppocr_v6_available, tesseract_available,
            )
            ocr_found = ppocr_v6_available() or paddleocr_installed() or tesseract_available()
        except ImportError:
            ocr_found = False

        self.data["env"] = {
            "ffmpeg": {
                "found": bool(ffmpeg_path), "path": ffmpeg_path,
                "version": _binary_version("ffmpeg"), "level": "required",
                "impact": "" if ffmpeg_path else "无法处理音视频",
            },
            "yt-dlp": yt_dlp,
            "playwright": playwright,
            "faster-whisper": whisper,
            "scenedetect": scenedetect,
            "ocr": {
                "found": ocr_found, "version": "", "level": "depth_optional",
                "impact": "" if ocr_found else "跳过 OCR",
            },
            "browser_cookie3": browser_cookie3,
            "python": {
                "found": True, "path": sys.executable,
                "version": sys.version.split()[0], "level": "required", "impact": "",
            },
        }
        self.data["last_check"] = _iso_now()
        self.save()
        return self.data["env"]

    def print_environment_report(self, env: dict[str, Any]) -> None:
        print("🔍 Learn 环境自检报告")
        print("━" * 33)
        for name, item in env.items():
            found = bool(item.get("found"))
            marker = "✅" if found else ("❌" if item.get("level") in {"required", "douyin_required"} else "⚠")
            detail = item.get("path") or item.get("version") or ("OK" if found else "MISSING")
            impact = f" (影响: {item['impact']})" if item.get("impact") else ""
            print(f"{marker} {name:<16} → {detail}{impact}")
        print("━" * 33)

    def missing_required(self, platform: str = "") -> list[str]:
        missing = []
        for name, item in self.data.get("env", {}).items():
            if item.get("found"):
                continue
            if item.get("level") == "required" or (
                platform == "douyin" and item.get("level") == "douyin_required"
            ):
                missing.append(name)
        return missing

    def preferred_method(self, platform: str) -> str:
        memory = self.data.get("platform_memory", {}).get(platform, {})
        if platform == "douyin" and (
            memory.get("yt_dlp_cookie_issues")
            or memory.get("last_success_method") == "playwright_intercept"
        ):
            return "playwright_intercept"
        return str(memory.get("last_success_method") or "yt-dlp")

    def record_extraction(
        self, platform: str, *, success: bool, method: str = "",
        error: str = "", cookie_issue: bool = False,
    ) -> None:
        stats = self.data.setdefault("stats", self._default()["stats"])
        stats["total_extractions"] = int(stats.get("total_extractions", 0)) + 1
        key = "successful" if success else "failed"
        stats[key] = int(stats.get(key, 0)) + 1
        stats["last_extraction"] = _iso_now()

        memory = self.data.setdefault("platform_memory", {}).setdefault(platform, {})
        memory["attempts"] = int(memory.get("attempts", 0)) + 1
        if success:
            memory["failures"] = 0
            memory["last_success"] = _iso_now()
            if method:
                memory["last_success_method"] = method
        else:
            memory["failures"] = int(memory.get("failures", 0)) + 1
            memory["last_fail_reason"] = error[:500]
        if cookie_issue:
            memory["yt_dlp_cookie_issues"] = True
        elif success and method == "yt-dlp":
            memory["yt_dlp_cookie_issues"] = False
        self.save()
