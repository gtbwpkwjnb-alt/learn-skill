from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.extract_douyin import _load_transcription_checkpoint, _save_transcription_checkpoint  # noqa: E402


class TranscriptionResumeTests(unittest.TestCase):
    def test_restores_completed_chunks_for_unchanged_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            audio.write_bytes(b"audio")
            completed = {0: [(0.0, 1.0, "第一段")]}

            _save_transcription_checkpoint(audio, 2, completed)

            self.assertEqual(_load_transcription_checkpoint(audio, 2), completed)

    def test_invalidates_checkpoint_after_audio_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            audio.write_bytes(b"audio")
            _save_transcription_checkpoint(audio, 1, {0: [(0.0, 1.0, "旧内容")]})
            audio.write_bytes(b"changed audio source")

            self.assertEqual(_load_transcription_checkpoint(audio, 1), {})
