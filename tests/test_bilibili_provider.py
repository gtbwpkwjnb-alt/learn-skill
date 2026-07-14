from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts import bilibili_provider as provider  # noqa: E402


class BilibiliProviderTests(unittest.TestCase):
    def test_parses_timeline_segments_and_metadata(self):
        payload = {
            "ok": True,
            "data": {
                "video": {"title": "测试视频", "owner": {"name": "UP主"}, "duration": 125},
                "subtitle": {"segments": [
                    {"from": 1.2, "content": "第一句"},
                    {"start": 62, "text": "第二句"},
                ]},
            },
        }
        result = provider.parse_bili_payload(payload, "bili.exe")
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "测试视频")
        self.assertEqual(result.author, "UP主")
        self.assertEqual(result.duration_sec, 125)
        self.assertEqual(result.transcript, "[00:01] 第一句\n[01:02] 第二句")

    def test_returns_none_for_missing_subtitle(self):
        self.assertIsNone(provider.parse_bili_payload({"data": {"video": {"title": "无字幕"}}}))

    def test_fetch_uses_timeline_json_command(self):
        original_finder = provider.find_bili_command
        seen = []

        def fake_runner(args, **kwargs):
            seen.extend(args)
            return subprocess.CompletedProcess(
                args, 0,
                stdout=json.dumps({"data": {"video": {"title": "标题"}, "subtitle": "[00:00] 字幕"}}),
                stderr="",
            )

        try:
            provider.find_bili_command = lambda: "bili"
            result, error = provider.fetch_bilibili_subtitles("https://www.bilibili.com/video/BV1x", runner=fake_runner)
        finally:
            provider.find_bili_command = original_finder

        self.assertIsNone(error)
        self.assertEqual(result.transcript, "[00:00] 字幕")
        self.assertEqual(seen, ["bili", "video", "https://www.bilibili.com/video/BV1x", "--subtitle-timeline", "--json"])


if __name__ == "__main__":
    unittest.main()
