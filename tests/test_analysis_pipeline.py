from __future__ import annotations

from pathlib import Path
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.analysis_pipeline import parse_json_payload, split_transcript, verify_analysis_payload  # noqa: E402
from scripts.assemble_md import assemble  # noqa: E402


class AnalysisPipelineTests(unittest.TestCase):
    def test_split_transcript_keeps_all_paragraphs(self):
        text = "\n\n".join(["第一段内容。" * 8, "第二段内容。" * 8, "第三段内容。" * 8])
        chunks = split_transcript(text, max_chars=50)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks).replace("\n", ""), text.replace("\n", ""))
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))

    def test_parse_json_payload_accepts_fenced_json(self):
        payload = parse_json_payload("说明\n```json\n[{\"claim\": \"事实\"}]\n```", list)
        self.assertEqual(payload[0]["claim"], "事实")

    def test_verify_analysis_payload_rejects_unsupported_claims(self):
        transcript = "[00:01] Speaker 1: 真正出现在原文的证据。"
        payload = {
            "highlights": [
                {"text": "正确", "evidence": "真正出现在原文的证据"},
                {"text": "幻觉", "evidence": "原文没有这句话"},
            ],
            "glossary": [],
            "chapters": [],
            "flashcards": [],
            "deep_questions": [],
        }
        verified, report = verify_analysis_payload(payload, transcript)
        self.assertEqual([item["text"] for item in verified["highlights"]], ["正确"])
        self.assertEqual(report["rejected"]["highlights"], 1)

    def test_markdown_renderer_keeps_evidence(self):
        markdown = assemble(
            title="测试", url="https://example.com", platform="test",
            highlights=[{"time": "00:01", "text": "要点", "evidence": "原文证据"}],
            glossary=[{"term": "术语", "definition": "定义", "evidence": "原文术语"}],
            chapters=[{"time": "00:00", "title": "章节", "summary": "章节摘要", "evidence": "章节原文"}],
            flashcards=[{"q": "问题", "a": "答案", "evidence": "闪卡原文"}],
        )
        self.assertIn("> 证据：原文证据", markdown)
        self.assertIn("> 证据：章节原文", markdown)
        self.assertIn("> 证据：闪卡原文", markdown)


if __name__ == "__main__":
    unittest.main()
