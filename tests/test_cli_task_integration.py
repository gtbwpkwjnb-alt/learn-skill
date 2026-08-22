from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from learn_core.models import TaskStage
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
        from scripts import douyin_playwright_extract
        from scripts import extract_douyin

        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            metadata = {
                "title": "测试抖音", "author": "测试作者", "video_element": {"duration": 12},
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

            summary_args = {}

            def fake_summary(path, _url, _platform, _title, author, *_args, **_kwargs):
                summary_args["author"] = author
                Path(path).write_text("# summary", encoding="utf-8")

            visual = {
                "frames": [{"path": "frames/scene_001.jpg", "timestamp": 1.0}],
                "ocr": [{"timestamp": 1.0, "text": "画面文字"}],
            }

            with patch.object(douyin_playwright_extract, "extract_video", return_value=metadata), \
                 patch.object(douyin_playwright_extract, "download_video", side_effect=fake_download), \
                 patch.object(module.subprocess, "run", side_effect=fake_ffmpeg), \
                 patch.object(module, "_whisper_fallback", side_effect=fake_whisper), \
                 patch.object(module, "_write_summary", side_effect=fake_summary), \
                 patch.object(extract_douyin, "extract_visual_evidence", return_value=visual) as visual_mock:
                summary = module._playwright_fallback_douyin(
                    "https://www.douyin.com/video/1", task_dir, with_frames=True,
                )

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertTrue(summary.is_file())
            target_id = hashlib.md5("https://www.douyin.com/video/1".encode()).hexdigest()[:12]
            target = task_dir / f"douyin_playwright_{target_id}"
            self.assertTrue((target / "audio_source.mp4").exists())
            self.assertTrue((target / "merged.mp4").exists())
            self.assertEqual(summary_args["author"], "测试作者")
            visual_mock.assert_called_once()
            self.assertIn("画面文字", summary.read_text(encoding="utf-8"))

    def test_douyin_task_waits_for_host_analysis_then_finalizes(self):
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
                    "## 📝\n[00:01] 原始证据文本。\n[00:02] 不应进入最终笔记的全文句子。",
                    encoding="utf-8",
                )
                return summary

            module.run_douyin = fake_extract
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
            task_id = next((output_root / "_tasks").iterdir()).name
            self.assertEqual(TaskStore(output_root).get(task_id).stage, TaskStage.AWAITING_HOST_ANALYSIS)

            final_note = task_dir / "video" / "测试视频-2026-07-25.md"
            final_note.write_text("# 最终学习卡片", encoding="utf-8")
            module.finalize_host_analysis(output_root, task_id, final_note)
            record = TaskStore(output_root).get(task_id)
            self.assertEqual(record.stage, TaskStage.COMPLETED)
            self.assertEqual(record.metadata["final_markdown_path"], str(final_note.resolve()))

    def test_host_finalizer_records_vault_note(self):
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
            env = module.NetworkEnv()
            env.bilibili_ok = True
            self.assertTrue(module.process_single(url, env, output_root, resolve_short_links=False))

            task_id = hashlib.md5(url.encode()).hexdigest()[:12]
            task_dir = output_root / "_tasks" / task_id
            final_note = task_dir / "video" / "测试视频-2026-07-25.md"
            final_note.write_text("# 最终学习卡片", encoding="utf-8")
            vault_note = vault / "数字人创建.md"
            vault.mkdir()
            vault_note.write_text("# 最终学习卡片", encoding="utf-8")
            module.finalize_host_analysis(output_root, task_id, final_note, vault_note)
            record = TaskStore(output_root).get(task_id)
            self.assertTrue(task_dir.exists())
            self.assertIsNotNone(record)
            assert record is not None
            self.assertTrue(record.metadata["imported"])
            self.assertEqual(Path(record.metadata["vault_note_path"]), vault_note.resolve())

    def test_output_root_owns_its_registry(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            module.configure_output_root(first)
            module.mark_processed("https://example.com/video/1", "first.md")
            module.configure_output_root(second)
            self.assertFalse(module.is_duplicate("https://example.com/video/1"))

    def test_cli_finalizer_completes_waiting_task(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "output"
            store = TaskStore(output_root)
            store.create_or_resume(
                task_id="finalize123", raw_input="分享文案",
                canonical_url="https://example.com/video/1", platform="douyin",
            )
            store.transition("finalize123", TaskStage.AWAITING_HOST_ANALYSIS)
            final_note = output_root / "_tasks" / "finalize123" / "主题-2026-07-25.md"
            final_note.write_text("# 最终学习卡片", encoding="utf-8")

            with patch.object(sys, "argv", [
                "zhixi-learn.py", "--out", str(output_root), "--finalize-task", "finalize123",
                "--final-markdown", str(final_note),
            ]):
                module.main()

            self.assertEqual(TaskStore(output_root).get("finalize123").stage, TaskStage.COMPLETED)

    def test_relearn_creates_a_fresh_task_for_the_same_url(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "output"
            module.ensure_ffmpeg = lambda: None
            module.save_progress = lambda *_args, **_kwargs: None
            module.is_duplicate = lambda _url: False

            def fake_extract(_url, task_dir, _with_frames):
                summary = Path(task_dir) / "video" / "summary.md"
                summary.parent.mkdir(parents=True, exist_ok=True)
                summary.write_text('---\ntitle: "测试视频"\n---\n', encoding="utf-8")
                return summary

            module.run_douyin = fake_extract
            env = module.NetworkEnv()
            url = "https://www.douyin.com/video/7345678901234567890"
            self.assertTrue(module.process_single(url, env, output_root, resolve_short_links=False, relearn=True))
            self.assertTrue(module.process_single(url, env, output_root, resolve_short_links=False, relearn=True))
            self.assertEqual(len(list((output_root / "_tasks").iterdir())), 2)
