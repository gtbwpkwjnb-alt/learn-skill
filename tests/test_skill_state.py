from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from learn_core.skill_state import SkillState  # noqa: E402


class SkillStateTests(unittest.TestCase):
    def test_environment_check_is_persisted_and_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = SkillState(Path(tmp))
            with patch("learn_core.skill_state.shutil.which", return_value="C:/ffmpeg.exe"):
                first = state.check_environment(force=True)
            self.assertTrue((Path(tmp) / ".skill_state.json").is_file())
            with patch("learn_core.skill_state.shutil.which", side_effect=AssertionError("cache missed")):
                second = state.check_environment()
            self.assertEqual(first, second)
            self.assertEqual(json.loads(state.path.read_text(encoding="utf-8"))["schema"], 1)

    def test_cookie_failure_routes_next_douyin_attempt_to_playwright(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = SkillState(Path(tmp))
            state.record_extraction(
                "douyin", success=False, method="yt-dlp",
                error="Fresh cookies are needed", cookie_issue=True,
            )
            reloaded = SkillState(Path(tmp))
            self.assertEqual(reloaded.preferred_method("douyin"), "playwright_intercept")
            self.assertEqual(reloaded.data["stats"]["failed"], 1)

    def test_successful_yt_dlp_clears_cookie_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = SkillState(Path(tmp))
            state.record_extraction("douyin", success=False, cookie_issue=True)
            state.record_extraction("douyin", success=True, method="yt-dlp")
            self.assertEqual(state.preferred_method("douyin"), "yt-dlp")
            self.assertFalse(state.data["platform_memory"]["douyin"]["yt_dlp_cookie_issues"])


if __name__ == "__main__":
    unittest.main()
