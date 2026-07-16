from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("zhixi_learn_export_test", SKILL_ROOT / "zhixi-learn.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ObsidianExportTests(unittest.TestCase):
    def test_exports_note_and_frames_without_copying_original_media(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "task" / "video"
            source_dir.mkdir(parents=True)
            note = source_dir / "summary.md"
            note.write_text('---\ntitle: "测试笔记"\nplatform: "douyin"\ntask_id: "abc123"\n---\n![frame](frames/001.jpg)', encoding="utf-8")
            frames = source_dir / "frames"
            frames.mkdir()
            (frames / "001.jpg").write_bytes(b"image")
            (frames / "unused.jpg").write_bytes(b"unused image")
            (source_dir / "source.mp4").write_bytes(b"large media")
            (source_dir / "metadata.json").write_text('{"source": "temporary"}', encoding="utf-8")
            (source_dir / "page.html").write_text("temporary page capture", encoding="utf-8")
            (source_dir / "transcript.txt").write_text("temporary transcript", encoding="utf-8")
            vault = Path(tmp) / "vault"

            module.OBSIDIAN_LEARN_ROOT = "03-学习资料/自动导入（learn）"
            exported_note = module.export_to_obsidian(note, str(vault))
            self.assertIsNotNone(exported_note)
            assert exported_note is not None
            self.assertEqual(exported_note.name, "测试笔记.md")
            self.assertIn("03-学习资料", str(exported_note))
            self.assertTrue((exported_note.parent / "frames" / "001.jpg").exists())
            self.assertFalse((exported_note.parent / "frames" / "unused.jpg").exists())
            self.assertFalse((exported_note.parent / "source.mp4").exists())
            self.assertFalse((exported_note.parent / "summary.md").exists())
            self.assertFalse((exported_note.parent / "metadata.json").exists())
            self.assertFalse((exported_note.parent / "page.html").exists())
            self.assertFalse((exported_note.parent / "transcript.txt").exists())

    def test_cleanup_only_deletes_task_children(self):
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output"
            task = root / "_tasks" / "abc"
            task.mkdir(parents=True)
            (task / "video.mp4").write_bytes(b"video")
            self.assertTrue(module.cleanup_task_workspace(task, root))
            self.assertFalse(task.exists())
            self.assertFalse(module.cleanup_task_workspace(root / "not-a-task", root))


if __name__ == "__main__":
    unittest.main()
