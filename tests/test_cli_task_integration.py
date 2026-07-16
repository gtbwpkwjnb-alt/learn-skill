from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from learn_core.task_store import TaskStore


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def _load_cli_module():
    path = SKILL_ROOT / "zhixi-learn.py"
    spec = importlib.util.spec_from_file_location("zhixi_learn_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CliTaskIntegrationTests(unittest.TestCase):
    def test_timestamped_whisper_output_writes_text_json_and_srt(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            transcript = module._write_timestamped_transcript(
                Path(tmp), [(1.2, 2.5, "第一句"), (62.0, 63.5, "第二句")]
            )
            self.assertIn("[00:01] 第一句", transcript.read_text(encoding="utf-8"))
            self.assertIn('"start": 62.0', (Path(tmp) / "transcript.json").read_text(encoding="utf-8"))
            self.assertIn("00:01:02,000", (Path(tmp) / "transcript.srt").read_text(encoding="utf-8"))

    def test_douyin_uses_playwright_when_primary_extractor_requires_cookies(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "playwright" / "summary.md"
            expected.parent.mkdir(parents=True)
            expected.write_text("# fallback", encoding="utf-8")
            with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                returncode=2, stderr="Fresh cookies are needed", stdout=""
            )), patch.object(module, "_playwright_fallback_douyin", return_value=expected):
                self.assertEqual(
                    module.run_douyin("https://www.douyin.com/video/1", Path(tmp), with_frames=True),
                    expected,
                )

    def test_playwright_merges_separated_douyin_streams_before_whisper(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            metadata = {
                "title": "测试抖音", "video_element": {"duration": 12},
                "video_urls": [
                    "https://media.example/media-audio.mp4",
                    "https://media.example/media-video.mp4",
                ],
            }

            def fake_download(_url, path):
                Path(path).write_bytes(b"stream-data" * 256)
                return True

            def fake_ffmpeg(command, **_kwargs):
                Path(command[-1]).write_bytes(b"merged-media" * 256)
                return SimpleNamespace(returncode=0, stderr="")

            def fake_whisper(path, out_dir):
                self.assertEqual(Path(path).name, "merged.mp4")
                transcript = Path(out_dir) / "transcript.txt"
                transcript.write_text("[00:01] 原文", encoding="utf-8")
                return transcript

            def fake_summary(path, *_args, **_kwargs):
                Path(path).write_text("# summary", encoding="utf-8")

            with patch("scripts.douyin_playwright_extract.extract_video", return_value=metadata), \
                 patch("scripts.douyin_playwright_extract.download_video", side_effect=fake_download), \
                 patch.object(module.subprocess, "run", side_effect=fake_ffmpeg), \
                 patch.object(module, "_whisper_fallback", side_effect=fake_whisper), \
                 patch.object(module, "_write_summary", side_effect=fake_summary):
                summary = module._playwright_fallback_douyin(
                    "https://www.douyin.com/video/1", task_dir
                )

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertTrue(summary.is_file())
            target_id = hashlib.md5("https://www.douyin.com/video/1".encode()).hexdigest()[:12]
            target = task_dir / f"douyin_playwright_{target_id}"
            self.assertTrue((target / "audio_source.mp4").exists())
            self.assertTrue((target / "merged.mp4").exists())

    def test_douyin_task_writes_manifest_analysis_and_obsidian_markdown(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "output"
            module.ensure_ffmpeg = lambda: None
            module.save_progress = lambda *_args, **_kwargs: None
            module.mark_processed = lambda *_args, **_kwargs: None
            module.build_related_notes = lambda *_args, **_kwargs: []

            def fake_extract(_url, task_dir, _with_frames):
                summary = Path(task_dir) / "video" / "summary.md"
                summary.parent.mkdir(parents=True, exist_ok=True)
                summary.write_text(
                    '---\ntitle: "测试视频"\nauthor: "作者"\nduration: "00:12"\n---\n\n'
                    "## 📝\n[00:01] 原始证据文本。",
                    encoding="utf-8",
                )
                return summary

            module.run_douyin = fake_extract
            module.generate_structured_analysis = lambda *_args: module.StructuredAnalysis(
                category="测试", tags=["抖音"], summary="总结", rating="4",
                highlights=[{"time": "00:01", "text": "要点", "evidence": "原始证据文本"}],
            )
            env = module.NetworkEnv()
            env.bilibili_ok = True
            module.is_duplicate = lambda _url: False

            success = module.process_single(
                "https://www.douyin.com/video/7345678901234567890", env, output_root,
                no_import=True, resolve_short_links=False,
            )

            self.assertTrue(success)
            task_dir = next((output_root / "_tasks").iterdir())
            self.assertTrue((task_dir / "task.json").exists())
            self.assertTrue((task_dir / "source.json").exists())
            self.assertTrue((task_dir / "artifacts.json").exists())
            analysis = next(task_dir.rglob("analysis.json"))
            self.assertIn("原始证据文本", analysis.read_text(encoding="utf-8"))
            note = next(task_dir.rglob("summary.md"))
            markdown = note.read_text(encoding="utf-8")
            self.assertIn('task_id: "', markdown)
            self.assertIn("原始证据文本", markdown)

    def test_successful_vault_export_cleans_local_task_by_default(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "output"
            vault = Path(tmp) / "vault"
            url = "https://www.douyin.com/video/7345678901234567890"
            module.ensure_ffmpeg = lambda: None
            module.save_progress = lambda *_args, **_kwargs: None
            module.mark_processed = lambda *_args, **_kwargs: None
            module.build_related_notes = lambda *_args, **_kwargs: []
            module.is_duplicate = lambda _url: False

            def fake_extract(_url, task_dir, _with_frames):
                summary = Path(task_dir) / "video" / "summary.md"
                summary.parent.mkdir(parents=True, exist_ok=True)
                summary.write_text(
                    '---\ntitle: "测试视频"\nauthor: "作者"\nduration: "00:12"\n---\n\n'
                    "## 📝\n[00:01] 原始证据文本。",
                    encoding="utf-8",
                )
                return summary

            module.run_douyin = fake_extract
            module.generate_structured_analysis = lambda *_args: module.StructuredAnalysis(
                category="测试", tags=["抖音"], summary="总结", rating="4",
                highlights=[{"time": "00:01", "text": "要点", "evidence": "原始证据文本"}],
            )
            env = module.NetworkEnv()
            env.bilibili_ok = True
            env.obsidian_vault = str(vault)

            self.assertTrue(module.process_single(url, env, output_root, resolve_short_links=False))

            task_id = hashlib.md5(url.encode()).hexdigest()[:12]
            task_dir = output_root / "_tasks" / task_id
            record = TaskStore(output_root).get(task_id)
            self.assertFalse(task_dir.exists())
            self.assertIsNotNone(record)
            assert record is not None
            self.assertTrue(record.metadata["local_artifacts_cleaned"])
            self.assertTrue(Path(record.metadata["vault_note_path"]).is_file())
