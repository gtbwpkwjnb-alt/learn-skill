from __future__ import annotations

from pathlib import Path
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.ocr_provider import _paddle_texts, select_ocr_provider  # noqa: E402


class OcrProviderTests(unittest.TestCase):
    def test_extracts_legacy_paddleocr_tuples(self):
        raw = [[[[0, 0], [1, 0]], ("第一行", 0.99)], [[[0, 1], [1, 1]], ("第二行", 0.98)]]
        self.assertEqual(_paddle_texts(raw), ["第一行", "第二行"])

    def test_extracts_modern_paddleocr_dictionary(self):
        raw = [{"rec_texts": ["标题", "正文"]}]
        self.assertEqual(_paddle_texts(raw), ["标题", "正文"])

    def test_prefers_paddleocr_when_initialization_succeeds(self):
        class Engine:
            def ocr(self, _path, cls=True):
                return [[([0], ("Paddle 文本", 0.9))]]

        provider = select_ocr_provider(paddle_factory=Engine)
        self.assertEqual(provider.name, "paddleocr")
        self.assertEqual(provider.read(Path("frame.jpg")), "Paddle 文本")

    def test_falls_back_to_tesseract_after_paddle_failure(self):
        provider = select_ocr_provider(
            paddle_factory=lambda: (_ for _ in ()).throw(RuntimeError("protobuf incompatible")),
            tesseract_factory=lambda: lambda _: "Tesseract 文本",
        )
        self.assertEqual(provider.name, "tesseract")
        self.assertIn("protobuf incompatible", provider.fallback_reason)
        self.assertEqual(provider.read(Path("frame.jpg")), "Tesseract 文本")
