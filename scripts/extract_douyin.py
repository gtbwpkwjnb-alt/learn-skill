#!/usr/bin/env python3
"""
Self-contained Douyin/TikTok deep extractor for learn skill.

Inlines all logic from tiktok-extractor (pipeline, download, audio, transcribe,
frames, OCR, preflight, markdown writer) — no external package dependency.

Usage:
    python scripts/extract_douyin.py <url> [--frames] [--out PATH]

Output (learn-compatible summary.md):
    learn-output/<video_id>/
    ├── summary.md       ← metadata + transcript + frames + OCR
    ├── transcript.txt
    ├── video.mp4
    ├── audio.wav
    └── frames/
        ├── scene_001.jpg
        └── ocr.txt
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ── Exceptions ───────────────────────────────────────────────────────────────

class MissingDependencyError(RuntimeError):
    """Raised when a required system tool is missing."""


class DownloadError(RuntimeError):
    """Raised when the video cannot be downloaded."""


class AudioExtractionError(RuntimeError):
    """Raised when ffmpeg fails to extract audio."""


class FrameExtractionError(RuntimeError):
    """Raised when frame extraction fails."""


# ── Preflight ────────────────────────────────────────────────────────────────

_BASE_BINARIES = ("ffmpeg",)
_FRAME_BINARIES = ()
_OCR_BINARIES = ("tesseract",)
_BASE_PYTHON_MODULES = ("yt_dlp",)


def _check_dependencies(*, require_frames: bool, require_ocr: bool) -> tuple[list[str], list[str]]:
    """Verify all required system tools and Python modules are available.
    
    Returns (missing_frame_deps, missing_ocr_deps) so callers can decide
    whether to skip frames/OCR rather than hard-failing.
    Raises MissingDependencyError only if CORE dependencies are missing.
    """
    binaries = list(_BASE_BINARIES)
    missing_frame: list[str] = []
    missing_ocr: list[str] = []

    if require_frames:
        for b in _FRAME_BINARIES:
            if shutil.which(b) is None:
                missing_frame.append(b)
    if require_ocr:
        for b in _OCR_BINARIES:
            if shutil.which(b) is None:
                missing_ocr.append(b)

    missing_bins = [b for b in binaries if shutil.which(b) is None]
    missing_mods = [
        m for m in _BASE_PYTHON_MODULES if importlib.util.find_spec(m) is None
    ]
    missing_core = missing_bins + missing_mods
    if missing_core:
        install_hints = {
            "ffmpeg": "winget install Gyan.FFmpeg | brew install ffmpeg | apt install ffmpeg",
            "tesseract": "winget install UB-Mannheim.TesseractOCR | brew install tesseract | apt install tesseract-ocr",
            "yt_dlp": "pip install yt-dlp",
        }
        hints = [install_hints.get(m, f"pip install {m}") for m in missing_core]
        raise MissingDependencyError(
            f"Missing core dependencies: {', '.join(missing_core)}.\n"
            f"Install: {' && '.join(hints)}"
        )

    return missing_frame, missing_ocr


# ── Downloader ───────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    video_path: Path
    metadata: dict
    metadata_path: Path
    video_id: str


def _resolve_video_id(url: str) -> str:
    """Resolve the canonical video ID via yt-dlp without downloading."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError as YtDlpDownloadError
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except YtDlpDownloadError as exc:
        raise DownloadError(f"yt-dlp could not resolve video: {exc}") from exc
    return str(info["id"])


def _download_video(url: str, base_out_dir: Path) -> DownloadResult:
    """Download video into base_out_dir/<video_id>/."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError as YtDlpDownloadError

    base_out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(base_out_dir / "%(id)s" / "video.%(ext)s"),
        "format": "best[vcodec=h264]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except YtDlpDownloadError as exc:
        raise DownloadError(f"yt-dlp could not download video: {exc}") from exc

    video_id = str(info["id"])
    target_dir = base_out_dir / video_id
    video_path = target_dir / "video.mp4"
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(json.dumps(info, indent=2, default=str, ensure_ascii=False))
    return DownloadResult(video_path=video_path, metadata=info, metadata_path=metadata_path, video_id=video_id)


# ── Audio extraction ─────────────────────────────────────────────────────────

def _extract_audio(video_path: Path) -> Path | None:
    """Extract 16kHz mono WAV next to the video. Returns None if no audio stream."""
    audio_path = video_path.parent / "audio.wav"
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", "-vn", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr or ""
        if "does not contain any stream" in stderr or "Output file #0 does not contain any stream" in stderr:
            return None
        raise AudioExtractionError(f"ffmpeg failed: {stderr.strip()}")
    return audio_path


def _extract_audio_from_source(audio_source_path: Path, output_wav: Path) -> Path:
    """Extract 16kHz mono WAV from a separate audio source file (e.g. Douyin audio track)."""
    cmd = ["ffmpeg", "-y", "-i", str(audio_source_path), "-ar", "16000", "-ac", "1", "-vn", str(output_wav)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioExtractionError(f"ffmpeg failed on audio source: {result.stderr.strip()}")
    return output_wav


def _merge_av(video_path: Path, audio_source_path: Path, output_path: Path) -> Path:
    """Merge video and separate audio track into one file. Skips if output exists."""
    if output_path.exists():
        return output_path
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_source_path),
        "-c:v", "copy", "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠ Audio-video merge failed (non-fatal): {result.stderr.strip()[:200]}")
        return video_path  # fallback to video-only
    return output_path


# ── Transcription (faster-whisper) ───────────────────────────────────────────

@dataclass
class TranscriptResult:
    plain_text: str
    segments: list[tuple[float, float, str]] = field(default_factory=list)
    language: str = ""


def _transcribe(audio_path: Path) -> TranscriptResult:
    """Run faster-whisper (base model) on the audio file."""
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="auto", compute_type="auto")
    segments_iter, info = model.transcribe(str(audio_path))
    segments: list[tuple[float, float, str]] = []
    for seg in segments_iter:
        segments.append((float(seg.start), float(seg.end), seg.text.strip()))
    plain_text = " ".join(text for _, _, text in segments).strip()
    return TranscriptResult(plain_text=plain_text, segments=segments, language=info.language)


def _write_srt(segments: list[tuple[float, float, str]], srt_path: Path) -> None:
    """Write segments as SRT subtitle file."""
    def _ts(seconds: float) -> str:
        millis = int(round(seconds * 1000))
        h, millis = divmod(millis, 3_600_000)
        m, millis = divmod(millis, 60_000)
        s, ms = divmod(millis, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    for idx, (start, end, text) in enumerate(segments, 1):
        lines.extend([str(idx), f"{_ts(start)} --> {_ts(end)}", text, ""])
    srt_path.write_text("\n".join(lines), encoding="utf-8")


# ── Keyframe extraction ─────────────────────────────────────────────────────

def _extract_keyframes(video_path: Path, out_dir: Path) -> list[tuple[Path, float]]:
    """Detect scenes via scenedetect, extract one JPEG per scene start."""
    from scenedetect import ContentDetector, detect, open_video

    out_dir.mkdir(parents=True, exist_ok=True)
    open_video(str(video_path))
    scenes = detect(str(video_path), ContentDetector())
    results: list[tuple[Path, float]] = []
    for idx, (start, _end) in enumerate(scenes, 1):
        ts = float(start.get_seconds())
        frame_path = out_dir / f"scene_{idx:03d}.jpg"
        cmd = ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(video_path),
               "-frames:v", "1", "-q:v", "2", str(frame_path)]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            raise FrameExtractionError(f"ffmpeg frame extraction failed: {completed.stderr.strip()}")
        results.append((frame_path, ts))
    return results


# ── OCR ──────────────────────────────────────────────────────────────────────

def _ocr_frames(frames: list[tuple[Path, float]]) -> list[tuple[float, str]]:
    """Run Tesseract OCR on each frame; return (timestamp, text) for non-empty results."""
    import pytesseract
    from PIL import Image

    results: list[tuple[float, str]] = []
    for frame_path, ts in frames:
        image = Image.open(str(frame_path))
        raw = pytesseract.image_to_string(image, lang="chi_sim+eng")
        text = raw.strip()
        if text:
            results.append((ts, text))
    return results


def _write_ocr(items: list[tuple[float, str]], out_path: Path) -> None:
    """Write OCR results as timestamped text."""
    lines = [f"[{int(ts)//60:02d}:{int(ts)%60:04.1f}] {text}" for ts, text in items]
    out_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


# ── Summary writer (learn-compatible) ────────────────────────────────────────

@dataclass
class SummaryInput:
    metadata: dict
    original_url: str
    extracted_at: datetime
    transcript_plain: str
    transcript_segments: list[tuple[float, float, str]]
    transcript_language: str
    ocr_entries: list[tuple[float, str]] = field(default_factory=list)
    frames: list[tuple[Path, float]] = field(default_factory=list)


def _fmt_duration(seconds: float | int | None) -> str:
    if not seconds:
        return "—"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _fmt_date(yyyymmdd: str | None) -> str:
    if not yyyymmdd or len(yyyymmdd) != 8:
        return "—"
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _fmt_clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text or "")


def _get_title(md: dict) -> str:
    """Extract best available title from metadata."""
    return (md.get("title")
            or md.get("fulltitle")
            or md.get("description", "")[:80]
            or "Untitled")


def _get_author(md: dict) -> str:
    return (md.get("uploader")
            or md.get("creator")
            or md.get("channel")
            or md.get("uploader_id")
            or "—")


def _get_platform(url: str) -> str:
    if "douyin" in url or "iesdouyin" in url:
        return "douyin"
    if "tiktok" in url:
        return "tiktok"
    return "video"


def write_summary(data: SummaryInput, out_path: Path) -> None:
    """Write learn-compatible summary.md with bilingual metadata."""
    md = data.metadata
    title = _get_title(md)
    author = _get_author(md)
    platform = _get_platform(data.original_url)
    duration = _fmt_duration(md.get("duration"))
    hashtags = _extract_hashtags(md.get("description") or "")
    tags_line = " ".join(f"`{h}`" for h in hashtags) if hashtags else "—"

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 📋 Metadata / 元数据")
    lines.append(f"- **Platform / 平台**: {platform}")
    lines.append(f"- **Author / 作者**: {author}")
    lines.append(f"- **Duration / 时长**: {duration}")
    lines.append(f"- **Source / 来源**: [{data.original_url}]({data.original_url})")
    lines.append(f"- **Extracted / 提取时间**: {data.extracted_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Language / 语言**: {data.transcript_language or '—'}")
    lines.append(f"- **Hashtags / 标签**: {tags_line}")
    lines.append("")

    lines.append("## 🎵 Music")
    track = md.get("track") or "—"
    artist = md.get("artist") or "—"
    lines.append(f"- **Track / 曲目**: {track}")
    lines.append(f"- **Artist / 艺人**: {artist}")
    lines.append("")

    lines.append("## 📝 Transcript / 内容转录")
    if data.transcript_plain:
        lines.append(data.transcript_plain)
    else:
        lines.append("_(kein Audio erkannt / no audio detected)_")
    lines.append("")

    if data.transcript_segments:
        lines.append("### Transcript with Timestamps / 带时间戳转录")
        for start, end, text in data.transcript_segments[:50]:  # cap at 50 segments
            lines.append(f"- **[{_fmt_clock(start)} - {_fmt_clock(end)}]** {text}")
        if len(data.transcript_segments) > 50:
            lines.append(f"- _... and {len(data.transcript_segments) - 50} more segments_")
        lines.append("")

    if data.ocr_entries:
        lines.append("## 🔍 On-Screen Text (OCR) / 屏幕文本")
        for ts, text in data.ocr_entries:
            lines.append(f"- **[{_fmt_clock(ts)}]** {text}")
        lines.append("")

    if data.frames:
        lines.append("## 🖼 Visual Content / 关键帧")
        for idx, (frame_path, ts) in enumerate(data.frames, 1):
            rel = frame_path.relative_to(out_path.parent)
            lines.append(f"![Scene {idx} @ {ts:.1f}s]({rel.as_posix()})")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ── Pipeline orchestration ──────────────────────────────────────────────────

def run_pipeline(url: str, base_out_dir: Path, *, with_frames: bool) -> Path:
    """Run full extraction pipeline. Returns path to summary.md. Idempotent."""
    missing_frame, missing_ocr = _check_dependencies(
        require_frames=with_frames, require_ocr=with_frames
    )
    base_out_dir = Path(base_out_dir)

    can_extract_frames = with_frames and not missing_frame
    can_extract_ocr = with_frames and not missing_ocr

    if missing_frame and with_frames:
        print(f"⚠ scenedetect not found — skipping keyframe extraction")
        print(f"  Install: pip install scenedetect")
    if missing_ocr and with_frames:
        print(f"⚠ tesseract not found — skipping OCR")
        print(f"  Install: winget install UB-Mannheim.TesseractOCR")

    # Extract video ID from URL or resolve via yt-dlp
    match = re.search(r"/video/(\d+)", url)
    video_id = match.group(1) if match else _resolve_video_id(url)

    summary_path = base_out_dir / video_id / "summary.md"
    if summary_path.exists():
        print(f"[skip] Already extracted: {summary_path}")
        return summary_path

    # Download
    result = _download_video(url, base_out_dir)
    target_dir = result.video_path.parent

    # Audio → transcribe
    audio_path = _extract_audio(result.video_path)
    if audio_path is None:
        print("⚠ No audio stream in video — checking for separate audio track...")
        # Check if a separate audio file exists (Douyin/TikTok pattern)
        audio_source = target_dir / "audio_source.mp4"
        if audio_source.exists():
            audio_path = _extract_audio_from_source(audio_source, target_dir / "audio.wav")
        elif audio_path is None:
            transcript = TranscriptResult(plain_text="", segments=[], language="")
        else:
            transcript = _transcribe(audio_path)
    else:
        transcript = _transcribe(audio_path)

    transcript_path = target_dir / "transcript.txt"
    transcript_path.write_text(transcript.plain_text, encoding="utf-8")
    _write_srt(transcript.segments, target_dir / "transcript.srt")

    # Frames + OCR (depth mode, graceful degradation)
    frames: list[tuple[Path, float]] = []
    ocr_entries: list[tuple[float, str]] = []
    if can_extract_frames:
        frames_dir = target_dir / "frames"
        frames = _extract_keyframes(result.video_path, frames_dir)
        if can_extract_ocr:
            ocr_entries = _ocr_frames(frames)
            _write_ocr(ocr_entries, frames_dir / "ocr.txt")
        else:
            print("  (OCR skipped — install tesseract to enable)")
    else:
        print("  (Keyframe extraction skipped — install scenedetect to enable)")

    # Relative frame paths
    relative_frames = [(p.relative_to(target_dir), ts) for p, ts in frames]

    write_summary(
        SummaryInput(
            metadata=result.metadata,
            original_url=url,
            extracted_at=datetime.now(),
            transcript_plain=transcript.plain_text,
            transcript_segments=transcript.segments,
            transcript_language=transcript.language,
            ocr_entries=ocr_entries,
            frames=relative_frames,
        ),
        summary_path,
    )
    return summary_path


# ── CLI entry point ──────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deep extract Douyin/TikTok video: metadata, transcript, keyframes + OCR."
    )
    parser.add_argument("url", help="Video URL (douyin.com, tiktok.com, iesdouyin.com)")
    parser.add_argument("--frames", action="store_true", help="Extract keyframes + OCR")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Output directory (default: ./output)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        summary_path = run_pipeline(args.url, args.out, with_frames=args.frames)
    except MissingDependencyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DownloadError as exc:
        print(f"⚠ yt-dlp download failed: {exc}", file=sys.stderr)
        print("  Tips for Douyin/TikTok:", file=sys.stderr)
        print("  1. Fresh cookies needed: use Playwright fallback", file=sys.stderr)
        print("     → python scripts/douyin_playwright_extract.py <url>", file=sys.stderr)
        print("  2. Install browser_cookie3 to auto-extract cookies:", file=sys.stderr)
        print("     → pip install browser_cookie3", file=sys.stderr)
        return 2
    except AudioExtractionError as exc:
        print(f"⚠ Audio extraction error: {exc}", file=sys.stderr)
        print("  If this is a Douyin video, audio may be in a separate stream.", file=sys.stderr)
        print("  Use the Playwright fallback script to capture both streams.", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 4

    print(f"Done: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
