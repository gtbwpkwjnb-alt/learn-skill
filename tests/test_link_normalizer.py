from __future__ import annotations

from pathlib import Path
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.link_normalizer import normalize_input  # noqa: E402


class LinkNormalizerTests(unittest.TestCase):
    def test_prefers_supported_content_url_over_promotional_url(self):
        result = normalize_input(
            "推荐你看看 https://example.com/?utm_source=ad ，视频在 "
            "https://www.bilibili.com/video/BV1Ab411c7h7?spm_id_from=333.1007&p=2&t=31"
        )
        self.assertEqual(
            result.canonical_url,
            "https://www.bilibili.com/video/BV1Ab411c7h7?p=2&t=31",
        )
        self.assertEqual(result.platform_hint, "bilibili")

    def test_youtube_share_url_is_canonicalized(self):
        result = normalize_input("https://youtu.be/dQw4w9WgXcQ?si=tracking&utm_source=copy&t=45")
        self.assertEqual(result.canonical_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=45")
        self.assertIn("si", result.removed_params)

    def test_short_link_can_be_resolved_before_cleaning(self):
        result = normalize_input(
            "6.12 复制打开抖音 https://v.douyin.com/abcDEF/?share_token=ignored/",
            resolver=lambda _: "https://www.douyin.com/video/7345678901234567890?utm_source=copy",
        )
        self.assertEqual(result.canonical_url, "https://www.douyin.com/video/7345678901234567890")
        self.assertEqual(result.platform_hint, "douyin")

    def test_wechat_signed_parameters_are_preserved(self):
        result = normalize_input(
            "https://mp.weixin.qq.com/s?__biz=MzA=&mid=1&idx=2&sn=abc&utm_source=copy"
        )
        self.assertEqual(
            result.canonical_url,
            "https://mp.weixin.qq.com/s?__biz=MzA%3D&mid=1&idx=2&sn=abc",
        )
        self.assertEqual(result.platform_hint, "wechat")

    def test_unresolved_short_link_remains_auditable(self):
        result = normalize_input(
            "https://b23.tv/abc123?spm_id_from=333",
            resolver=lambda _: (_ for _ in ()).throw(ValueError("network unavailable")),
        )
        self.assertEqual(result.canonical_url, "https://b23.tv/abc123")
        self.assertIn("network unavailable", result.resolution_error or "")

    def test_local_media_path_is_unchanged(self):
        result = normalize_input(r"D:\videos\lesson.mp4")
        self.assertTrue(result.is_local_path)
        self.assertEqual(result.canonical_url, r"D:\videos\lesson.mp4")


if __name__ == "__main__":
    unittest.main()
