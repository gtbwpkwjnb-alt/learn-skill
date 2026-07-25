from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

spec = importlib.util.spec_from_file_location("zhixi_learn_test", SKILL_ROOT / "zhixi-learn.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TranscriptCleaningTests(unittest.TestCase):
    def test_preserves_english_speaker_labels(self):
        cleaned = module.clean_transcript("Speaker 1: Hello there\nSPEAKER 2：Good morning")
        self.assertIn("Speaker 1: Hello there", cleaned)
        self.assertIn("SPEAKER 2: Good morning", cleaned)

    def test_preserves_chinese_speaker_labels(self):
        cleaned = module.clean_transcript("说话人 1：这是第一句\n发言人2: 这是第二句")
        self.assertIn("说话人 1: 这是第一句", cleaned)
        self.assertIn("发言人2: 这是第二句", cleaned)

    def test_analysis_fallback_keeps_timestamped_source_lines(self):
        result = module.generate_structured_analysis("标题", "[00:01] 可验证的原文。")
        self.assertEqual(result.category, "转录待整理")
        self.assertTrue(result.summary)
        self.assertEqual(result.highlights[0]["evidence"], "可验证的原文。")

    def test_analysis_does_not_expose_external_model_hooks(self):
        source = inspect.getsource(module.generate_structured_analysis)
        self.assertNotIn("requests", source)
        self.assertNotIn("http", source)
        result = module.generate_structured_analysis("标题", "[00:01] 原文证据")
        self.assertTrue(result.verification["fallback"])
        self.assertIn("宿主 agent", result.verification["reason"])

    def test_progress_keeps_link_and_verification_audit_data(self):
        original_progress_file = module.PROGRESS_FILE
        with tempfile.TemporaryDirectory() as tmp:
            module.PROGRESS_FILE = Path(tmp) / "progress.json"
            try:
                module.save_progress("task", "extracting", {"link_normalization": {"raw_input": "分享文案"}})
                module.save_progress("task", "ai_analysis", {"verification": {"rejected": {"highlights": 1}}})
                stored = module.load_progress("task")
            finally:
                module.PROGRESS_FILE = original_progress_file

        self.assertEqual(stored["data"]["link_normalization"]["raw_input"], "分享文案")
        self.assertEqual(stored["data"]["verification"]["rejected"]["highlights"], 1)
        self.assertEqual(stored["history"][0]["step"], "extracting")

    def test_bilibili_prefers_specialized_subtitle_provider(self):
        original_fetch = module.fetch_bilibili_subtitles
        with tempfile.TemporaryDirectory() as tmp:
            result_type = __import__("scripts.bilibili_provider", fromlist=["BilibiliSubtitleResult"]).BilibiliSubtitleResult
            module.fetch_bilibili_subtitles = lambda _: (
                result_type("B站标题", "UP主", 61, "[00:01] 专用字幕", "bili"), None
            )
            try:
                summary_path = module.run_bilibili("https://www.bilibili.com/video/BV1x", Path(tmp), module.NetworkEnv())
            finally:
                module.fetch_bilibili_subtitles = original_fetch

            content = summary_path.read_text(encoding="utf-8")
        self.assertIn("B站标题", content)
        self.assertIn("专用字幕", content)


if __name__ == "__main__":
    unittest.main()
