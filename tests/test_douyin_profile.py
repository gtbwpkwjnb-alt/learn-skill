from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.douyin_profile import (  # noqa: E402
    ProfileEnumeration, ProfileVideo, displayed_work_count, is_profile_url,
    parse_aweme_payload, write_profile_report,
)


class DouyinProfileTests(unittest.TestCase):
    def test_profile_detection_excludes_modal_video_urls(self):
        self.assertTrue(is_profile_url("https://www.douyin.com/user/abc"))
        self.assertTrue(is_profile_url("https://www.douyin.com/share/user/abc"))
        self.assertTrue(is_profile_url("https://www.iesdouyin.com/share/user/abc"))
        self.assertFalse(is_profile_url("https://www.douyin.com/user/abc?modal_id=123"))

    def test_parses_paginated_aweme_payload(self):
        videos, has_more = parse_aweme_payload({
            "data": {
                "aweme_list": [
                    {"aweme_id": "2", "desc": "第二条", "author": {"nickname": "作者"}},
                    {"aweme_id": "1", "desc": "第一条"},
                ],
                "has_more": 0,
            }
        })
        self.assertEqual([video.aweme_id for video in videos], ["2", "1"])
        self.assertEqual(videos[0].author, "作者")
        self.assertFalse(has_more)

    def test_displayed_count_supports_both_orders(self):
        self.assertEqual(displayed_work_count("作品 19 喜欢 3"), 19)
        self.assertEqual(displayed_work_count("1.2万 作品"), 12000)

    def test_report_marks_count_mismatch_without_claiming_cause(self):
        result = ProfileEnumeration(
            profile_url="https://www.douyin.com/user/a", final_url="https://www.douyin.com/user/a",
            author="作者", displayed_count=19,
            videos=[ProfileVideo("1", "https://www.douyin.com/video/1")],
            warnings=["原因待核验"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = write_profile_report(result, Path(tmp))
            text = report.read_text(encoding="utf-8")
            self.assertIn('"count_mismatch": true', text)
            self.assertIn('"accessible_count": 1', text)
            self.assertIn("原因待核验", text)

    def test_main_detector_accepts_plain_profile_url(self):
        import importlib.util

        path = SKILL_ROOT / "zhixi-learn.py"
        spec = importlib.util.spec_from_file_location("zhixi_profile_test", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.detect_platform("https://www.douyin.com/user/abc"), "douyin")


if __name__ == "__main__":
    unittest.main()
