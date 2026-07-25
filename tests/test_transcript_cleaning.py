from __future__ import annotations

import importlib.util
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

    def test_analysis_prompts_are_format_safe(self):
        mapped = module.MAP_ANALYSIS_PROMPT.format(
            title="测试", segment_number=1, segment_count=1, transcript="原文"
        )
        reduced = module.REDUCE_ANALYSIS_PROMPT.format(title="测试", facts_json="[]")
        self.assertIn('"claim"', mapped)
        self.assertIn('"highlights"', reduced)

    def test_map_parser_accepts_object_wrapped_facts(self):
        facts = module._parse_map_facts_payload(
            '{"facts":[{"claim":"事实","evidence_quote":"原文证据"}]}'
        )
        self.assertEqual(facts[0]["claim"], "事实")

    def test_analysis_fallback_keeps_timestamped_source_lines(self):
        original_key = module.DEEPSEEK_KEY
        module.DEEPSEEK_KEY = ""
        try:
            result = module.generate_structured_analysis("标题", "[00:01] 可验证的原文。")
        finally:
            module.DEEPSEEK_KEY = original_key

        self.assertEqual(result.category, "转录待整理")
        self.assertTrue(result.summary)
        self.assertEqual(result.highlights[0]["evidence"], "可验证的原文。")

    def test_map_reduce_verify_keeps_only_evidenced_items(self):
        original_key = module.DEEPSEEK_KEY
        original_call = module._call_deepseek
        original_record = module._record_api_call
        original_budget = module._check_analysis_api_budget
        original_external = os.environ.get("LEARN_ENABLE_EXTERNAL_AI")
        module.DEEPSEEK_KEY = "test-key"
        os.environ["LEARN_ENABLE_EXTERNAL_AI"] = "1"

        def fake_call(prompt, **kwargs):
            if kwargs["call_type"] == "analysis_map":
                return ('[{"claim":"事实","evidence_quote":"原文证据","timestamp":"00:01","speaker":"Speaker 1","confidence":"high","topic":"测试"}]', {})
            return ('{"category":"测试","tags":["测试"],"summary":"摘要","chapters":[],"highlights":[{"time":"00:01","text":"正确","evidence":"原文证据"},{"time":"00:02","text":"错误","evidence":"不存在"}],"glossary":[],"rating":{"overall":4},"flashcards":[],"deep_questions":[]}', {})

        try:
            module._call_deepseek = fake_call
            module._record_api_call = lambda *args, **kwargs: None
            module._check_analysis_api_budget = lambda *_args, **_kwargs: True
            result = module.generate_structured_analysis("标题", "[00:01] Speaker 1: 原文证据")
        finally:
            module.DEEPSEEK_KEY = original_key
            module._call_deepseek = original_call
            module._record_api_call = original_record
            module._check_analysis_api_budget = original_budget
            if original_external is None:
                os.environ.pop("LEARN_ENABLE_EXTERNAL_AI", None)
            else:
                os.environ["LEARN_ENABLE_EXTERNAL_AI"] = original_external

        self.assertEqual([item["text"] for item in result.highlights], ["正确"])
        self.assertEqual(result.verification["rejected"]["highlights"], 1)

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
