from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from learn_core.providers.douyin import DouyinProvider  # noqa: E402
from scripts.extract_douyin import _sample_evenly  # noqa: E402


class DouyinProviderTests(unittest.TestCase):
    def test_keyframe_sampling_is_bounded_and_spans_timeline(self):
        sampled = _sample_evenly(list(range(303)), 60)
        self.assertEqual(len(sampled), 60)
        self.assertEqual(sampled[0], 0)
        self.assertEqual(sampled[-1], 302)
        self.assertEqual(len(set(sampled)), 60)

    def test_source_and_artifact_manifests_are_task_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task"
            task_dir.mkdir()
            summary = task_dir / "summary.md"
            summary.write_text("# test", encoding="utf-8")
            (task_dir / "media.mp4").write_bytes(b"video")

            provider = DouyinProvider()
            source = provider.write_source_manifest(
                task_dir, raw_input="分享文案", canonical_url="https://www.douyin.com/video/1",
                normalized_link={"removed_params": ["share_token"]},
            )
            artifacts = provider.build_artifact_manifest(task_dir, summary)

            self.assertTrue(provider.supports("tiktok"))
            self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["provider"], "douyin")
            self.assertEqual(artifacts["summary"], "summary.md")
            self.assertIn("media.mp4", artifacts["files"])
