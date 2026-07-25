#!/usr/bin/env python3
"""
Zhixi-Learn Skill (知析) — Universal Video/Audio → Knowledge Base Import
═══════════════════════════════════════════════════════════════════════
One command: URL → extract → AI structured analysis → import to your note system.

Usage:
    python zhixi-learn.py "<url>" [<url2> ...] [--frames] [--out DIR] [--no-import] [--dry-run]

Supports: Douyin, TikTok, Bilibili, YouTube, podcasts, local files (auto-detects network).
Outputs: SiYuan (auto-start), Obsidian vault, or plain local markdown.

知析 Skill — 通用视频/音频 → 知识库导入
══════════════════════════════════════
一条命令：链接 → 内容提取 → AI 结构化分析 → 导入笔记系统。

    用法: python zhixi-learn.py "<链接>" [<链接2> ...] [--frames] [--out 目录] [--no-import] [--dry-run]

    支持: 抖音、TikTok、B站、YouTube、播客、本地文件（自动检测网络环境）。
    输出: 思源笔记（自动启动）、Obsidian、或纯本地 Markdown。
"""

import sys, os, re, json, time, shutil, hashlib, subprocess, tempfile, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

# Keep bundled helpers importable when this file is launched by absolute path
# from an arbitrary working directory.
SKILL_DIR = Path(__file__).parent.resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# Load .env file if present / 加载 .env 文件
_ENV_FILE = Path(__file__).parent / ".env"
_ENV_ALLOWLIST = {
    "PYTHON_BIN", "FFMPEG_BIN", "LEARN_OUTPUT", "SIYUAN_API", "SIYUAN_TOKEN",
    "OBSIDIAN_VAULT", "OBSIDIAN_LEARN_ROOT", "HTTP_PROXY", "HTTPS_PROXY",
}
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k in _ENV_ALLOWLIST and _k not in os.environ:
                os.environ[_k] = _v


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _reexec_with_compatible_python() -> None:
    """Use an installed Python that has the media stack when PATH selects another one."""
    required = ("yt_dlp", "playwright", "faster_whisper")
    if all(_module_available(name) for name in required):
        return
    if os.environ.get("ZHIXI_LEARN_RUNTIME_SELECTED") == "1":
        return

    candidates = []
    configured = os.environ.get("PYTHON_BIN", "").strip()
    if configured:
        candidates.append(configured)
    try:
        launcher = shutil.which("py")
        if launcher:
            listing = subprocess.check_output(
                [launcher, "-0p"], text=True, encoding="utf-8", errors="replace", timeout=5
            )
            candidates.extend(re.findall(r"([A-Za-z]:\\[^\r\n]*python\.exe)", listing, re.I))
    except (OSError, subprocess.SubprocessError):
        pass

    for candidate in dict.fromkeys(candidates):
        if os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(os.path.abspath(sys.executable)):
            continue
        probe = "import importlib.util; raise SystemExit(not all(importlib.util.find_spec(n) for n in ('yt_dlp', 'playwright', 'faster_whisper')))"
        try:
            result = subprocess.run([candidate, "-c", probe], timeout=10, check=False)
        except OSError:
            continue
        if result.returncode == 0:
            env = os.environ.copy()
            env["ZHIXI_LEARN_RUNTIME_SELECTED"] = "1"
            raise SystemExit(
                subprocess.call(
                    [candidate, str(Path(__file__).resolve()), *sys.argv[1:]], env=env
                )
            )


if __name__ == "__main__":
    _reexec_with_compatible_python()

# ═══════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════
PYTHON = os.environ.get("PYTHON_BIN", sys.executable)
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", r"C:\Tools\ffmpeg-8.1.1-essentials_build\bin")
TOOLS_DIR = SKILL_DIR
DOUYIN2MD = TOOLS_DIR / "scripts" / "extract_douyin.py"
DOUYIN_PLAYWRIGHT = TOOLS_DIR / "scripts" / "douyin_playwright_extract.py"
PROJECT_ROOT = TOOLS_DIR.parent
_configured_output_root = os.environ.get("LEARN_OUTPUT", "").strip()
DEFAULT_OUT = Path(_configured_output_root).expanduser() if _configured_output_root else PROJECT_ROOT / "learn-output"
REGISTRY_FILE = DEFAULT_OUT / ".registry.json"
PROGRESS_FILE = DEFAULT_OUT / ".progress.json"

# ── Unified Timeouts / 统一超时 ──────────────────────────────────────────────
TIMEOUT_WHISPER = 1200    # 本地 Whisper 转写（秒）
TIMEOUT_NET = 8           # 网络检测（秒）
TIMEOUT_KB = 20           # 知识库导入（秒）
TIMEOUT_SUBPROCESS = 900  # 子进程提取（秒）

# SiYuan / 思源
SIYUAN_PATHS = [
    r"D:\Program Files\siyuan\SiYuan.exe",
    r"C:\Program Files\siyuan\SiYuan.exe",
    r"D:\SiYuan\SiYuan.exe",
]
SIYUAN_API = os.environ.get("SIYUAN_API", "http://127.0.0.1:6806")
SIYUAN_TOKEN = os.environ.get("SIYUAN_TOKEN", "")
SIYUAN_STARTUP_WAIT = 15  # seconds / 秒


from scripts.bilibili_provider import fetch_bilibili_subtitles
from scripts.douyin_profile import enumerate_profile_videos, is_profile_url, write_profile_report
from scripts.link_normalizer import LinkNormalizationError, normalize_input
from learn_core.models import TaskStage
from learn_core.providers.douyin import DouyinProvider
from learn_core.skill_state import SkillState
from learn_core.task_store import TaskStore

# Obsidian (international users / 国际用户)
OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")
# Relative directory inside the vault for automatically imported learning notes.
# Keep the generic "learn" default for other vaults; a knowledge base can opt
# into its own collection structure through OBSIDIAN_LEARN_ROOT.
OBSIDIAN_LEARN_ROOT = os.environ.get("OBSIDIAN_LEARN_ROOT", "learn")

# ═══════════════════════════════════════════════════════════════════════════
# Network Environment Detection / 网络环境检测
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NetworkEnv:
    """Detected network environment / 检测到的网络环境"""
    is_china: bool = True          # Behind GFW? / 是否在国内
    youtube_ok: bool = False       # YouTube accessible? / YouTube 可访问
    bilibili_ok: bool = True       # Bilibili accessible? / B站可访问
    github_ok: bool = False        # GitHub HTTPS ok? / GitHub HTTPS 可访问
    jina_ok: bool = False          # Jina AI ok? / Jina AI 可访问
    has_browser: bool = False       # Chrome/Edge browser? / 浏览器可用
    has_siyuan: bool = False       # SiYuan installed? / 思源已安装
    siyuan_running: bool = False   # SiYuan running? / 思源运行中
    obsidian_vault: str = ""       # Obsidian vault path / Obsidian 库路径

    @property
    def platform_status(self) -> Dict[str, str]:
        """Which platforms are available / 各平台可用状态"""
        return {
            "douyin":      "ok" if self.bilibili_ok else "blocked",
            "tiktok":      "ok",
            "bilibili":    "ok" if self.bilibili_ok else "blocked",
            "youtube":     "ok" if self.youtube_ok else "need_proxy",
            "podcast":     "ok",
            "local":       "ok",
            "wechat":      "ok" if self.has_browser else "need_browser",
            "xiaohongshu": "ok" if self.has_browser else "need_browser",
        }


def detect_network() -> NetworkEnv:
    """Auto-detect network environment / 自动检测网络环境"""
    env = NetworkEnv()
    import urllib.request, urllib.error

    def _check(url: str, timeout: float = 5.0) -> bool:
        try:
            req = urllib.request.Request(url, method="GET",
                headers={"User-Agent": "Mozilla/5.0 (compatible; LearnSkill/2.0)"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            # Any response (even 4xx) means the server is reachable / 任何响应都说明可达
            return True
        except urllib.error.HTTPError as e:
            # 412, 403 etc = server reachable, just denied our request / 服务器可达只是拒绝请求
            return e.code is not None
        except Exception:
            return False

    # Parallel-sequential: fast checks first / 快速检查优先
    check_timeout = TIMEOUT_NET
    env.bilibili_ok = _check("https://www.bilibili.com", check_timeout)
    env.youtube_ok = _check("https://www.youtube.com", check_timeout)
    env.github_ok = _check("https://github.com", check_timeout)
    env.jina_ok = _check("https://r.jina.ai", check_timeout)
    env.is_china = env.bilibili_ok and not env.youtube_ok

    # Chrome/Chromium/Edge detection / 浏览器检测
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    env.has_browser = any(Path(p).exists() for p in chrome_paths)
    if not env.has_browser:
        # Also check for playwright/patchright Chromium / 检查playwright安装的Chromium
        pw_dirs = [
            os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"),
            os.path.expandvars(r"%USERPROFILE%\.cache\ms-playwright"),
        ]
        for d in pw_dirs:
            if Path(d).exists():
                env.has_browser = True
                break

    # SiYuan / 思源
    env.has_siyuan = any(Path(p).exists() for p in SIYUAN_PATHS)
    env.siyuan_running = _check(f"{SIYUAN_API}/api/system/version", 2)

    # Obsidian
    env.obsidian_vault = OBSIDIAN_VAULT
    if env.obsidian_vault and not Path(env.obsidian_vault).exists():
        env.obsidian_vault = ""

    return env


# ═══════════════════════════════════════════════════════════════════════════
# Platform Detection / 平台检测
# ═══════════════════════════════════════════════════════════════════════════

PLATFORM_PATTERNS = {
    "douyin":      [r"(?:v\.douyin\.com|www\.douyin\.com/video|www\.iesdouyin\.com/share/video|douyin\.com/(?:share/)?user/)"],
    "tiktok":      [r"(?:tiktok\.com|vm\.tiktok\.com)"],
    "bilibili":    [r"bilibili\.com/video/", r"(?:b23\.tv|bili2233\.cn)/"],
    "youtube":     [r"(?:youtube\.com/watch|youtu\.be/)"],
    "wechat":      [r"mp\.weixin\.qq\.com"],
    "xiaohongshu": [r"(?:xiaohongshu\.com|xhslink\.com)"],
    "podcast":     [r"\.(?:xml|rss)(?:\?|$)", r"/feed/?$", r"podcast"],
    "local":       [r"\.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$"],
}


def detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL / 从 URL 检测平台"""
    url_lower = url.lower().strip()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, url_lower):
                return platform
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SiYuan Lifecycle / 思源生命周期管理
# ═══════════════════════════════════════════════════════════════════════════

def find_siyuan_exe() -> Optional[Path]:
    """Find SiYuan executable / 查找思源可执行文件"""
    for p in SIYUAN_PATHS:
        path = Path(p)
        if path.exists():
            return path
    return None


def ensure_siyuan_running() -> bool:
    """Make sure SiYuan is running; start it if not / 确保思源运行中，否则启动"""
    import urllib.request

    # Already running? / 已在运行？
    try:
        req = urllib.request.Request(f"{SIYUAN_API}/api/system/version")
        urllib.request.urlopen(req, timeout=TIMEOUT_NET)
        return True
    except Exception:
        pass

    # Find and start / 查找并启动
    exe = find_siyuan_exe()
    if not exe:
        return False

    print(f"  🔧 正在启动思源笔记: {exe}")
    try:
        # Start detached / 分离启动
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        # Wait for it to be ready / 等待就绪
        for i in range(SIYUAN_STARTUP_WAIT):
            time.sleep(1)
            try:
                req = urllib.request.Request(f"{SIYUAN_API}/api/system/version")
                urllib.request.urlopen(req, timeout=TIMEOUT_NET)
                print(f"  ✅ 思源已启动 (耗时 {i+1}s)")
                return True
            except Exception:
                continue
        print(f"  ⚠ 思源启动超时 ({SIYUAN_STARTUP_WAIT}s)，继续等待...")
    except Exception as e:
        print(f"  ⚠ 启动思源失败: {e}")

    return False


# ═══════════════════════════════════════════════════════════════════════════
# Registry (dedup) / 去重注册表
# ═══════════════════════════════════════════════════════════════════════════

def load_registry() -> Dict:
    """Load URL registry / 加载去重注册表"""
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_registry(reg: Dict):
    """Save URL registry / 保存去重注册表"""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def is_duplicate(url: str) -> bool:
    """Check if URL already processed / 检查是否已处理"""
    reg = load_registry()
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return url_hash in reg


def mark_processed(url: str, output_path: str, metadata: Dict = None):
    """Mark URL as processed / 标记URL已处理"""
    reg = load_registry()
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    reg[url_hash] = {
        "url": url,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output": str(output_path),
        "metadata": metadata or {},
    }
    save_registry(reg)


# ═══════════════════════════════════════════════════════════════════════════
# Progress tracking / 进度追踪
# ═══════════════════════════════════════════════════════════════════════════

def save_progress(task_id: str, step: str, data: Dict = None):
    """Save progress for resume / 保存进度以支持断点续传"""
    progress = {}
    if PROGRESS_FILE.exists():
        try:
            progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    previous = progress.get(task_id, {})
    merged_data = dict(previous.get("data", {}) or {})
    merged_data.update(data or {})
    history = list(previous.get("history", []) or [])
    if previous.get("step"):
        history.append({
            "step": previous["step"],
            "time": previous.get("time", ""),
        })
    progress[task_id] = {
        "step": step,
        "data": merged_data,
        "time": datetime.now().isoformat(),
        "history": history[-20:],
    }
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def load_progress(task_id: str) -> Optional[Dict]:
    """Load progress for resume / 加载进度"""
    if not PROGRESS_FILE.exists():
        return None
    try:
        progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return progress.get(task_id)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Transcript processing / 字幕处理
# ═══════════════════════════════════════════════════════════════════════════

def clean_transcript(text: str) -> str:
    """Clean transcript without losing speaker attribution or evidence labels."""
    lines = text.splitlines()
    cleaned = []
    prev = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Keep diarization labels.  They are evidence, not formatting noise.
        speaker_match = re.match(
            r'^\s*((?:speaker|说话人|发言人)\s*\d+)\s*[:：]\s*',
            line,
            flags=re.IGNORECASE,
        )
        speaker_prefix = ""
        if speaker_match:
            speaker_prefix = f"{speaker_match.group(1).strip()}: "
            line = line[speaker_match.end():].strip()

        # Fix ALL CAPS lines (>80% uppercase) / 修正全大写行
        alpha_chars = [c for c in line if c.isalpha()]
        if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.8:
            line = line.lower().capitalize()

        line = speaker_prefix + line

        # Dedup consecutive identical lines / 去重连续相同行
        if line == prev:
            continue

        # Merge very short fragments with previous / 合并过短的片段
        if len(line) < 10 and cleaned:
            cleaned[-1] = cleaned[-1].rstrip() + " " + line
        else:
            cleaned.append(line)
        prev = line

    # Join back with paragraph breaks on long pauses / 合并为段落
    result = []
    buf = []
    for line in cleaned:
        buf.append(line)
        if len(" ".join(buf)) > 200:  # paragraph threshold
            result.append(" ".join(buf))
            buf = []
    if buf:
        result.append(" ".join(buf))

    return "\n\n".join(result)


def segment_transcript(text: str, window_minutes: int = 3) -> str:
    """Split long transcript into ## sections / 将长转录分段为 ## 章节"""
    paragraphs = text.split("\n\n")
    if len(paragraphs) < 3:
        return text  # already short enough

    # Simple heuristic: every N paragraphs form a section
    # Better: use LLM to identify topic boundaries / 更好方案：用LLM识别主题边界
    sections = []
    section_size = max(1, len(paragraphs) // max(1, len(paragraphs) // 4))

    for i in range(0, len(paragraphs), section_size):
        chunk = paragraphs[i:i+section_size]
        # Use first sentence as section title / 用第一句话作为章节标题
        first_line = chunk[0][:60].strip()
        if len(first_line) > 50:
            first_line = first_line[:50] + "..."
        sections.append(f"## {first_line}\n\n" + "\n\n".join(chunk))

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════
# Bilibili Cookie Support / B站 Cookie 支持
# ═══════════════════════════════════════════════════════════════════════════

def load_bilibili_cookie() -> Optional[str]:
    """Load Bilibili cookie from .env / 从 .env 加载B站 Cookie"""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("BILI_COOKIE="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.startswith("BILI_SESSDATA="):
            sessdata = line.split("=", 1)[1].strip().strip('"').strip("'")
            return f"SESSDATA={sessdata}"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Structured Analysis / 结构化分析
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StructuredAnalysis:
    """Evidence-verified result of Map -> Reduce -> Verify analysis."""
    category: str = "未分类"
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    chapters: List[Dict] = field(default_factory=list)
    highlights: List[Dict] = field(default_factory=list)
    glossary: List[Dict] = field(default_factory=list)
    rating: str = ""
    rating_detail: Dict = field(default_factory=dict)
    flashcards: List[Dict] = field(default_factory=list)
    deep_questions: List[Dict] = field(default_factory=list)
    verification: Dict = field(default_factory=dict)


def _fallback_structured_analysis(transcript: str, reason: str) -> StructuredAnalysis:
    """Keep the exported note useful when evidence analysis is unavailable.

    This deliberately summarizes no new facts: it preserves a short list of
    timestamped source lines so the Markdown can be imported and reviewed
    instead of becoming an empty shell.
    """
    highlights: List[Dict] = []
    for line in (transcript or "").splitlines():
        match = re.match(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$", line.strip())
        if not match:
            continue
        evidence = match.group(2).strip()
        if evidence:
            highlights.append({"time": match.group(1), "text": evidence, "evidence": evidence})
        if len(highlights) >= 3:
            break
    return StructuredAnalysis(
        category="转录待整理",
        tags=["待整理"],
        summary="自动结构化分析未获得可验证结果；已保留原始转写与时间戳，可直接导入知识库后继续复核。",
        highlights=highlights,
        verification={"fallback": True, "reason": reason, "verified": {}, "rejected": {}},
    )


def generate_structured_analysis(title: str, transcript: str) -> StructuredAnalysis:
    """Return a local evidence placeholder for host-agent analysis.

    The skill intentionally does not invoke any model API. The active host
    agent reads the extracted transcript and writes the semantic Markdown
    summary; this function only keeps standalone CLI output non-empty.
    """
    return _fallback_structured_analysis(
        transcript, "宿主 agent 负责当前会话模型分析；本地脚本不调用外部模型 API"
    )


def build_related_notes(tags: List[str], current_title: str, max_notes: int = 5) -> List[Dict[str, str]]:
    """Build related notes list from registry, matched by tags.
    
    Returns:
        [{"title": "...", "relation": "tag_name"}, ...]
    """
    if not tags:
        return []
    reg = load_registry()
    matches = []
    for entry_hash, entry in reg.items():
        meta = entry.get("metadata", {}) or {}
        entry_tags = meta.get("tags", []) or []
        entry_title = meta.get("title", "") or entry.get("url", "")
        if entry_title == current_title:
            continue
        # Find matching tags
        common = set(t.lower() for t in tags) & set(t.lower() for t in entry_tags)
        for tag in common:
            matches.append({"title": entry_title, "relation": tag})
    # Dedup by title, keep first relation
    seen = set()
    unique = []
    for m in matches:
        if m["title"] not in seen:
            seen.add(m["title"])
            unique.append(m)
    return unique[:max_notes]


# ═══════════════════════════════════════════════════════════════════════════
# 增强的字幕兜底链 / Enhanced Subtitle Fallback Chain
# ═══════════════════════════════════════════════════════════════════════════

def _write_timestamped_transcript(out_dir: Path, segments: List[Tuple[float, float, str]]) -> Path:
    """Persist ASR output in formats usable by evidence verification and players."""
    cleaned = [(float(start), float(end), text.strip()) for start, end, text in segments if text.strip()]
    transcript_path = out_dir / "transcript.txt"
    transcript_path.write_text(
        "\n".join(f"[{_format_duration(int(start))}] {text}" for start, _end, text in cleaned),
        encoding="utf-8",
    )
    (out_dir / "transcript.json").write_text(
        json.dumps(
            [{"start": start, "end": end, "text": text} for start, end, text in cleaned],
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    def _srt_time(seconds: float) -> str:
        millis = int(round(seconds * 1000))
        hours, millis = divmod(millis, 3_600_000)
        minutes, millis = divmod(millis, 60_000)
        secs, milliseconds = divmod(millis, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    srt_lines: List[str] = []
    for index, (start, end, text) in enumerate(cleaned, 1):
        srt_lines.extend([str(index), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""])
    (out_dir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    return transcript_path


def _whisper_fallback(video_path: Path, out_dir: Path) -> Optional[Path]:
    """Direct whisper fallback for any video file / Whisper 直接转写兜底"""
    try:
        from faster_whisper import WhisperModel
        print(f"  ▶ Whisper 直接转写兜底...")
        audio_path = out_dir / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", "-vn", str(audio_path)],
            capture_output=True, text=True, timeout=TIMEOUT_WHISPER,
        )
        if not audio_path.exists():
            return None
        model = WhisperModel("base", device="auto", compute_type="auto")
        segments_iter, _info = model.transcribe(str(audio_path))
        segments = [(float(seg.start), float(seg.end), seg.text.strip()) for seg in segments_iter]
        transcript_path = _write_timestamped_transcript(out_dir, segments)
        print(f"  ✅ Whisper 兜底转写完成 ({len(segments)} 段)")
        return transcript_path
    except ImportError:
        print(f"  ⚠ faster-whisper 未安装，无法兜底")
        return None
    except Exception as e:
        print(f"  ⚠ Whisper 兜底失败: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# AI Classification / AI 分类
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Environments / 环境准备
# ═══════════════════════════════════════════════════════════════════════════

def ensure_ffmpeg():
    """Ensure ffmpeg in PATH / 确保 ffmpeg 在 PATH 中"""
    if shutil.which("ffmpeg"):
        return
    ffmpeg_dir = Path(FFMPEG_BIN)
    if ffmpeg_dir.is_dir():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
    if not shutil.which("ffmpeg"):
        print("❌ ffmpeg 未找到，请确认已安装至 %s" % FFMPEG_BIN, file=sys.stderr)
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# Extraction tool wrappers / 提取工具封装
# ═══════════════════════════════════════════════════════════════════════════

def _run_douyin_primary(url: str, out_dir: Path, with_frames: bool = False) -> Tuple[Optional[Path], str]:
    """Run the fast yt-dlp-backed extractor and preserve its failure reason."""
    cmd = [PYTHON, str(DOUYIN2MD), url, "--out", str(out_dir)]
    if with_frames:
        cmd.append("--frames")
    print(f"  ▶ 抖音提取: {DOUYIN2MD.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SUBPROCESS)
    if result.returncode != 0:
        print(f"  ❌ 提取失败: {result.stderr.strip()}", file=sys.stderr)
        return None, result.stderr.strip()
    for line in result.stdout.splitlines():
        if "完成" in line and "→" in line:
            p = Path(line.split("→")[-1].strip())
            if p.exists():
                return p, ""
    candidates = list(out_dir.rglob("summary.md"))
    return (max(candidates, key=lambda p: p.stat().st_mtime), "") if candidates else (None, "extractor returned no summary.md")


def run_douyin_routed(
    url: str, out_dir: Path, with_frames: bool = False,
    preferred_method: str = "yt-dlp",
) -> Tuple[Optional[Path], str, bool, str]:
    """Return (summary, actual_method, cookie_issue, last_error)."""
    if preferred_method == "playwright_intercept":
        print("  🧠 平台记忆：上次抖音使用 Playwright，优先复用该路径")
        summary = _playwright_fallback_douyin(url, out_dir, with_frames)
        if summary:
            return summary, "playwright_intercept", False, ""

    summary, error = _run_douyin_primary(url, out_dir, with_frames)
    cookie_issue = "cookie" in error.lower()
    if summary:
        return summary, "yt-dlp", cookie_issue, ""

    if preferred_method != "playwright_intercept":
        summary = _playwright_fallback_douyin(url, out_dir, with_frames)
        if summary:
            return summary, "playwright_intercept", cookie_issue, ""
    return None, "", cookie_issue, error or "all Douyin extraction methods failed"


def run_douyin(url: str, out_dir: Path, with_frames: bool = False) -> Optional[Path]:
    """Backward-compatible single-result wrapper used by integrations."""
    return run_douyin_routed(url, out_dir, with_frames)[0]


def run_bilibili(url: str, out_dir: Path, env: NetworkEnv) -> Optional[Path]:
    """Bilibili: dedicated subtitle CLI -> yt-dlp -> hearsay/Whisper fallback."""

    bvid = _extract_bvid(url)
    video_dir = out_dir / f"bilibili_{bvid}"
    video_dir.mkdir(parents=True, exist_ok=True)
    srt_path = video_dir / "subtitle.srt"
    txt_path = video_dir / "transcript.txt"

    # Step 1: platform-specific provider. It handles Bilibili's subtitle API,
    # browser cookies, and timeline output more reliably than generic yt-dlp.
    cli_result, cli_error = fetch_bilibili_subtitles(url)
    if cli_result:
        cleaned = clean_transcript(cli_result.transcript)
        txt_path.write_text(cleaned, encoding="utf-8")
        title = cli_result.title or bvid
        _write_summary(video_dir / "summary.md", url, "bilibili", title,
                       cli_result.author, cli_result.duration_sec, txt_path)
        print(f"  ✅ B站专用字幕 provider 成功: {cli_result.command}")
        return video_dir / "summary.md"
    if cli_error:
        print(f"  ⚠ B站专用字幕不可用，转入通用兜底: {cli_error}")

    import yt_dlp

    # Step 2: yt-dlp download subtitles / 下载字幕
    cookie = load_bilibili_cookie()
    print(f"  ▶ B站字幕下载 (Cookie: {'已配置' if cookie else '未配置 - 仅公开字幕'})")

    try:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en", "ai-zh"],
            "subtitlesformat": "srt",
            "outtmpl": str(video_dir / "%(id)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if cookie:
            opts["cookiefile"] = _write_temp_cookie(cookie)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            srt_files = list(video_dir.glob("*.srt"))
            if srt_files:
                shutil.move(str(srt_files[0]), str(srt_path))
                raw_text = _srt_to_text(srt_path)
                cleaned = clean_transcript(raw_text)
                txt_path.write_text(cleaned, encoding="utf-8")
                print(f"  ✅ 字幕下载成功 + 清洗完成")
    except Exception as e:
        print(f"  ⚠ yt-dlp 字幕下载失败: {e}")

    # Step 2: Metadata / 元数据
    title = bvid; author = ""; duration_sec = 0
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", bvid)
            author = info.get("uploader", "")
            duration_sec = info.get("duration", 0)
    except Exception:
        pass

    # Step 3: Whisper fallback if no subtitles / 无字幕时Whisper兜底
    if not srt_path.exists():
        print(f"  ▶ hearsay whisper 兜底转写...")
        try:
            cmd = [PYTHON, "-m", "hearsay", "ingest", url,
                   "-o", str(video_dir / "hearsay.md"), "--transcribe"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_WHISPER)
            if result.returncode == 0 and (video_dir / "hearsay.md").exists():
                h_content = (video_dir / "hearsay.md").read_text(encoding="utf-8")
                # Extract transcript part from hearsay output / 从hearsay输出提取转录
                h_body = h_content.split("---", 2)[-1] if h_content.count("---") >= 2 else h_content
                cleaned = clean_transcript(h_body)
                txt_path.write_text(cleaned, encoding="utf-8")
                print(f"  ✅ hearsay 转写完成")
        except Exception as e:
            print(f"  ⚠ hearsay 转写失败: {e}")

    # Step 4: Segment if long / 长视频分段
    if txt_path.exists():
        raw = txt_path.read_text(encoding="utf-8")
        if len(raw) > 1000:
            segmented = segment_transcript(raw)
            txt_path.write_text(segmented, encoding="utf-8")

    # Step 5: Generate summary.md / 生成汇总
    md_path = video_dir / "summary.md"
    _write_summary(md_path, url, "bilibili", title, author, duration_sec,
                   txt_path if txt_path.exists() else None)
    return md_path


def run_hearsay(url: str, out_dir: Path, is_local: bool = False) -> Optional[Path]:
    """hearsay: podcasts + local files / hearsay: 播客+本地文件"""
    cmd = [PYTHON, "-m", "hearsay", "ingest", url, "-o", str(out_dir / "hearsay.md")]
    if is_local:
        cmd.append("--transcribe")
    print(f"  ▶ hearsay 提取...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SUBPROCESS)
    if result.returncode != 0:
        print(f"  ❌ hearsay 失败: {result.stderr.strip()}", file=sys.stderr)
        return None
    md_path = out_dir / "hearsay.md"
    if md_path.exists():
        # Clean hearsay output / 清洗hearsay输出
        content = md_path.read_text(encoding="utf-8")
        body = content.split("---", 2)[-1] if content.count("---") >= 2 else content
        cleaned = clean_transcript(body)
        if len(cleaned) > 1000:
            cleaned = segment_transcript(cleaned)
        # Rebuild with original frontmatter / 保留原frontmatter，替换body
        if content.count("---") >= 2:
            parts = content.split("---", 2)
            md_path.write_text(parts[0] + "---" + parts[1] + "---\n\n" + cleaned, encoding="utf-8")
        else:
            md_path.write_text(cleaned, encoding="utf-8")
        return md_path
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Summary writer helpers — each builds one section of the markdown output
# ═══════════════════════════════════════════════════════════════════════════

def _build_mindmap_md(title: str, chapters: Optional[List[Dict]],
                      highlights: Optional[List[Dict]]) -> str:
    """Build Mermaid mindmap from chapters or highlights."""
    md = ""
    if chapters:
        md += "```mermaid\nmindmap\n  root((\""
        md += title.replace('"', "'")[:40] + "\"))\n"
        for ch in chapters:
            ch_t = ch.get("title", "").replace('"', "'")[:30]
            md += f"    {ch_t}\n"
            for pt in (ch.get("points", []) or [])[:3]:
                point_text = str(pt).replace('"', "'")[:40]
                md += f"      {point_text}\n"
        md += "```\n\n"
    elif highlights:
        md += "```mermaid\nmindmap\n  root((\""
        md += title.replace('"', "'")[:40] + "\"))\n"
        for h in highlights[:6]:
            ht_text = h.get("text", "").replace('"', "'")[:40]
            md += f"    {ht_text}\n"
        md += "```\n\n"
    return md


def _build_chapters_md(chapters: Optional[List[Dict]]) -> str:
    """Build chapter breakdown markdown."""
    if not chapters:
        return ""
    md = ""
    for i, ch in enumerate(chapters, 1):
        ch_title = ch.get("title", f"章节{i}")
        ch_time = ch.get("time", "")
        ch_summary = ch.get("summary", "")
        ch_points = ch.get("points", []) or []
        time_tag = f"⏱ {ch_time}" if ch_time else ""
        md += f"### 📍 章节{i}: {ch_title} {time_tag}\n\n"
        if ch_summary:
            md += f"{ch_summary}\n\n"
        if ch_points:
            md += "要点：\n" + "\n".join(f"- {pt}" for pt in ch_points) + "\n\n"
        if ch.get("evidence"):
            md += f"> 证据：{ch['evidence']}\n\n"
    return md


def _build_highlights_md(highlights: Optional[List[Dict]]) -> str:
    """Build highlights list markdown."""
    if not highlights:
        return ""
    md = ""
    for h in highlights:
        ht = h.get("time", "")
        ht_tag = f"`{ht}` " if ht else ""
        md += f"- {ht_tag}{h.get('text', '')}\n"
        if h.get("evidence"):
            md += f"  > 证据：{h['evidence']}\n"
    return md


def _build_glossary_md(glossary: Optional[List[Dict]]) -> str:
    """Build glossary definition list markdown."""
    if not glossary:
        return ""
    lines = []
    for g in glossary:
        lines.append(f"- **{g.get('term', '')}**: {g.get('definition', '')}")
        if g.get("evidence"):
            lines.append(f"  > 证据：{g['evidence']}")
    return "\n".join(lines) + "\n"


def _build_qa_list_md(items: Optional[List[Dict]], label_q: str = "Q",
                      label_a: str = "A") -> str:
    """Build Q&A formatted markdown (for flashcards and deep thinking)."""
    if not items:
        return ""
    md = ""
    for i, item in enumerate(items, 1):
        md += f"**{label_q}{i}:** {item.get('q', '')}\n"
        md += f"**{label_a}{i}:** {item.get('a', '')}\n\n"
        if item.get("evidence"):
            md += f"> 证据：{item['evidence']}\n\n"
    return md


def _build_rating_detail_md(rating_detail: Optional[Dict]) -> str:
    """Build rating detail lines for information_density/practicality/clarity."""
    if not rating_detail or not isinstance(rating_detail, dict):
        return ""
    label_map = {"information_density": "信息密度", "practicality": "实用价值", "clarity": "清晰度"}
    parts = []
    for k, v in rating_detail.items():
        if k != "overall":
            label = label_map.get(k, k)
            parts.append(f"  - **{label}**: {v}/5")
    return "\n".join(parts) + "\n" if parts else ""


def _build_related_md(related_notes: Optional[List[Dict]]) -> str:
    """Build related notes wiki-link list."""
    if not related_notes:
        return ""
    md = ""
    for rn in related_notes:
        rel_tag = rn.get("relation", "")
        rel_note = rn.get("title", "")
        tag_str = f" (#{rel_tag})" if rel_tag else ""
        md += f"- [[{rel_note}]]{tag_str}\n"
    return md


def _write_summary(md_path: Path, url: str, platform: str,
                   title: str, author: str, duration_sec: int,
                   transcript_path: Optional[Path] = None,
                   category: str = "未分类",
                   tags: Optional[List[str]] = None,
                   summary: str = "",
                   highlights: Optional[List[Dict]] = None,
                   deep_thinking: Optional[List[Dict]] = None,
                   glossary: Optional[List[Dict]] = None,
                   rating: str = "",
                   chapters: Optional[List[Dict]] = None,
                   related_notes: Optional[List[Dict]] = None,
                   flashcards: Optional[List[Dict]] = None,
                   rating_detail: Optional[Dict] = None,
                   task_id: str = "",
                   transcript_text: Optional[str] = None,
                   include_transcript: bool = True):
    """Write hierarchical summary.md with all sections / 写入层级化Markdown"""
    transcript = transcript_text or ""
    if not transcript and transcript_path and transcript_path.exists():
        transcript = transcript_path.read_text(encoding="utf-8")

    duration_str = _format_duration(duration_sec) if duration_sec else ""

    # One renderer is used for every platform.  The old path pointed at a
    # development-only checkout and silently selected a different template.
    try:
        from scripts.assemble_md import assemble
        md = assemble(
            title=title, url=url, platform=platform, author=author,
            duration=duration_str, transcript=transcript,
            category=category, tags=tags or [],
            summary=summary, highlights=highlights,
            deep_thinking=deep_thinking, glossary=glossary,
            rating=rating, chapters=chapters,
            related_notes=related_notes, flashcards=flashcards, task_id=task_id,
            include_transcript=include_transcript,
        )
    except ImportError:
        # ── Built-in hierarchical template (no external deps) ──
        tag_list = tags or []
        tags_display = " ".join(f"#{t}" for t in tag_list) if tag_list else ""
        rating_val = float(rating) if rating else 0
        rating_stars = f"{'⭐' * int(round(rating_val))} ({rating}/5)" if rating else ""

        md = f"""---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration_str}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
tags: [{', '.join(f'"{t}"' for t in tag_list)}]
category: "{category}"
rating: {rating if rating else '""'}
---

# {title}

## 📊 快速概览

{summary if summary else '_(AI 总结准备中 / AI summary pending)_'}

{('> ' + rating_stars) if rating_stars else ''}
{_build_rating_detail_md(rating_detail)}

---

## 🧭 内容结构 / Content Structure

{_build_mindmap_md(title, chapters, highlights)}

---

## 📑 章节分解

{_build_chapters_md(chapters) or '_(章节分解准备中 / chapter breakdown pending)_'}

---

## ⭐ 核心亮点

{_build_highlights_md(highlights) or '_(亮点准备中 / highlights pending)_'}

---

## 📚 关键术语

{_build_glossary_md(glossary) or '_(术语准备中 / glossary pending)_'}

---

## 🃏 复习闪卡

{_build_qa_list_md(flashcards) or '_(闪卡准备中 / flashcards pending)_'}

---

## 🤔 深度思考

{_build_qa_list_md(deep_thinking) or '_(深度思考准备中 / deep thinking pending)_'}

---

## 🔗 相关笔记

{_build_related_md(related_notes) or '_(无相关笔记)'}

---

## 🤖 AI 分类

| 维度 | 值 |
|------|-----|
| **Category / 主题** | {category} |
| **Tags / 标签** | {tags_display} |

"""
        if include_transcript:
            md += f"""

## 📝 Transcript / 内容转录

{transcript if transcript else '(待转录 / pending transcription)'}
"""

    md_path.write_text(md, encoding="utf-8")
    print(f"  📄 已生成: {md_path}")


# ═══════════════════════════════════════════════════════════════════════════
# Import: SiYuan / Obsidian / Local / 导入目标
# ═══════════════════════════════════════════════════════════════════════════

def import_to_siyuan(md_path: Path, title: str) -> bool:
    """Import to SiYuan note / 导入思源笔记"""
    import requests
    md_content = md_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    notebook_path = f"/学习/{today}"

    try:
        resp = requests.post(
            f"{SIYUAN_API}/api/filetree/createDocWithMd",
            headers={"Authorization": f"Token {SIYUAN_TOKEN}"},
            json={"notebook": "学习", "path": notebook_path, "markdown": md_content},
            timeout=TIMEOUT_KB,
        )
        data = resp.json()
        if data.get("code") == 0:
            doc_id = data.get("data", {}).get("id", "")
            print(f"  ✅ 已导入思源: {notebook_path}/{title} (id={doc_id})")
            return True
        else:
            print(f"  ⚠ 思源 API 错误: {data.get('msg', 'unknown')}")
    except Exception as e:
        print(f"  ⚠ 思源连接失败: {e}")
    return False


def _safe_note_name(value: str, fallback: str = "untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:100] or fallback)


def _frontmatter_value(markdown: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:\s*["\']?(.*?)["\']?\s*$', markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


def export_to_obsidian(md_path: Path, vault_path: str) -> Optional[Path]:
    """Export to Obsidian vault / 导出到 Obsidian 库"""
    try:
        markdown = md_path.read_text(encoding="utf-8")
        source_id = _frontmatter_value(markdown, "task_id") or hashlib.sha256(str(md_path.resolve()).encode("utf-8")).hexdigest()[:12]
        title = _safe_note_name(_frontmatter_value(markdown, "title"), md_path.stem)
        platform = _safe_note_name(_frontmatter_value(markdown, "platform"), "video")
        now = datetime.now()
        dest_dir = Path(vault_path) / OBSIDIAN_LEARN_ROOT / str(now.year) / f"{now.year}-{now.month:02d}" / platform / f"{title}--{source_id}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        # A vault note needs only its Markdown and the images it references.
        # Source HTML, transcripts, metadata, media, and unused frames stay in
        # the task workspace and are removed after a verified import.
        source_root = md_path.parent.resolve()
        refs = re.findall(r"!\[[^\]]*\]\((?:<)?((?:frames|assets)/[^)\s>]+)", markdown)
        for ref in dict.fromkeys(refs):
            source = (source_root / ref).resolve()
            try:
                relative = source.relative_to(source_root)
            except ValueError:
                continue
            if source.is_file():
                destination = dest_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        dest = dest_dir / f"{title}.md"
        shutil.copy2(md_path, dest)
        print(f"  ✅ 已导出到 Obsidian: {dest}")
        return dest
    except Exception as e:
        print(f"  ⚠ Obsidian 导出失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Helpers / 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _extract_bvid(url: str) -> str:
    m = re.search(r"BV\w+", url)
    return m.group() if m else hashlib.md5(url.encode()).hexdigest()[:12]


def _srt_to_text(srt_path: Path) -> str:
    lines = []
    for line in srt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.isdigit():
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _format_duration(seconds: int) -> str:
    if not seconds:
        return ""
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _playwright_fallback_douyin(url: str, out_dir: Path, with_frames: bool = False) -> Optional[Path]:
    """Capture a Douyin media URL in Chromium, then reuse the local ASR path."""
    try:
        from scripts.douyin_playwright_extract import download_video, extract_video

        target_dir = out_dir / f"douyin_playwright_{hashlib.md5(url.encode()).hexdigest()[:12]}"
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ▶ Playwright 网络拦截兜底: {DOUYIN_PLAYWRIGHT.name}")
        metadata = extract_video(url, target_dir)
        (target_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        media_urls = [value for value in metadata.get("video_urls", []) or []
                      if isinstance(value, str) and value.startswith(("http://", "https://"))]
        audio_urls = [value for value in media_urls if "media-audio" in value]
        video_urls = [value for value in media_urls if "media-video" in value]
        video_urls.extend(value for value in media_urls if value not in video_urls and "media-audio" not in value)

        for video_url in video_urls:
            video_path = target_dir / "video.mp4"
            video_path.unlink(missing_ok=True)
            if not download_video(video_url, video_path):
                continue
            if not video_path.exists() or video_path.stat().st_size < 1024:
                video_path.unlink(missing_ok=True)
                continue
            media_path = video_path
            if "media-video" in video_url and audio_urls:
                merged_path = target_dir / "merged.mp4"
                merged_path.unlink(missing_ok=True)
                for audio_url in audio_urls:
                    audio_path = target_dir / "audio_source.mp4"
                    audio_path.unlink(missing_ok=True)
                    if not download_video(audio_url, audio_path):
                        continue
                    merge = subprocess.run(
                        ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
                         "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", str(merged_path)],
                        capture_output=True, text=True, timeout=TIMEOUT_WHISPER,
                    )
                    if merge.returncode == 0 and merged_path.exists() and merged_path.stat().st_size >= 1024:
                        media_path = merged_path
                        break
                    print(f"  ⚠ 音视频合并失败: {merge.stderr.strip()[-300:]}")
                    merged_path.unlink(missing_ok=True)
                if media_path == video_path:
                    print("  ⚠ Playwright 已捕获分离音频，但未能合并；尝试下一视频流")
                    continue

            transcript_path = _whisper_fallback(media_path, target_dir)
            if not transcript_path:
                print("  ⚠ 当前视频流转写失败，尝试下一候选流")
                continue
            video_info = metadata.get("video_element", {}) or {}
            visual_evidence = None
            if with_frames:
                from scripts.extract_douyin import extract_visual_evidence
                visual_evidence = extract_visual_evidence(media_path, target_dir)
            _write_summary(
                target_dir / "summary.md", url, "douyin",
                metadata.get("title", "Douyin video"), metadata.get("author", ""),
                int(video_info.get("duration") or 0), transcript_path,
            )
            if visual_evidence:
                with (target_dir / "summary.md").open("a", encoding="utf-8") as summary_file:
                    summary_file.write("\n## 🖼 Visual Evidence / 视觉证据\n\n")
                    for frame in visual_evidence.get("frames", []):
                        summary_file.write(
                            f"![{frame['timestamp']:.1f}s]({frame['path']})\n"
                        )
                    for entry in visual_evidence.get("ocr", []):
                        summary_file.write(
                            f"- [{_format_duration(int(entry['timestamp']))}] {entry['text']}\n"
                        )
            return target_dir / "summary.md"
        print("  ⚠ Playwright 未捕获到可下载的视频流")
        return None
    except Exception as e:
        print(f"  ⚠ Playwright 兜底失败: {e}")
        return None


def _whisper_fallback_douyin(url: str, out_dir: Path) -> Optional[Path]:
    """Douyin/TikTok fallback: yt-dlp download → whisper transcribe."""
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError as YtDlpError
        video_id = hashlib.md5(url.encode()).hexdigest()[:12]
        target_dir = out_dir / f"douyin_fb_{video_id}"
        target_dir.mkdir(parents=True, exist_ok=True)

        opts = {
            "outtmpl": str(target_dir / "video.%(ext)s"),
            "format": "best[vcodec=h264]/best",
            "merge_output_format": "mp4",
            "quiet": True, "no_warnings": True, "noprogress": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video_files = list(target_dir.glob("video.*"))
        if not video_files:
            return None
        video_path = video_files[0]
        title = info.get("title", "Untitled")
        author = info.get("uploader", "")

        # Audio → whisper
        audio_path = target_dir / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", "-vn", str(audio_path)],
            capture_output=True, text=True, timeout=TIMEOUT_WHISPER,
        )
        transcript_path = _whisper_fallback(video_path, target_dir)

        # Write summary
        md_path = target_dir / "summary.md"
        _write_summary(md_path, url, "douyin", title, author, info.get("duration", 0), transcript_path)
        return md_path
    except Exception as e:
        print(f"  ⚠ 抖音兜底失败: {e}")
        return None


def _whisper_fallback_bilibili(url: str, out_dir: Path) -> Optional[Path]:
    """Bilibili fallback: download via yt-dlp → whisper transcribe."""
    try:
        from yt_dlp import YoutubeDL
        bvid_match = re.search(r"BV\w+", url)
        bvid = bvid_match.group() if bvid_match else hashlib.md5(url.encode()).hexdigest()[:12]
        target_dir = out_dir / f"bili_fb_{bvid}"
        target_dir.mkdir(parents=True, exist_ok=True)

        opts = {
            "outtmpl": str(target_dir / "video.%(ext)s"),
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "quiet": True, "no_warnings": True, "noprogress": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video_files = list(target_dir.glob("video.*"))
        if not video_files:
            return None
        video_path = video_files[0]
        title = info.get("title", bvid)
        author = info.get("uploader", "")

        transcript_path = _whisper_fallback(video_path, target_dir)
        md_path = target_dir / "summary.md"
        _write_summary(md_path, url, "bilibili", title, author, info.get("duration", 0), transcript_path)
        return md_path
    except Exception as e:
        print(f"  ⚠ B站兜底失败: {e}")
        return None


def author_from_md(md_content: str) -> str:
    """Extract author from frontmatter or extractor metadata sections."""
    m = re.search(r"^author:\s*\"(.+?)\"", md_content, re.MULTILINE)
    if not m:
        m = re.search(r"^- \*\*Author / 作者\*\*:\s*(.+)$", md_content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def duration_from_md(md_content: str) -> int:
    """Extract duration (in seconds) from frontmatter or metadata sections."""
    m = re.search(r"^duration:\s*\"(.+?)\"", md_content, re.MULTILINE)
    if not m:
        m = re.search(r"^- \*\*Duration / 时长\*\*:\s*(.+)$", md_content, re.MULTILINE)
    if not m:
        return 0
    dur_str = m.group(1).strip()
    parts = [int(x) for x in dur_str.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def transcript_for_analysis(md_path: Path, md_content: str) -> str:
    """Prefer the raw task artifact; legacy summaries remain a compatibility fallback."""
    transcript_path = md_path.parent / "transcript.txt"
    if transcript_path.is_file():
        text = transcript_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return md_content.split("## 📝", 1)[-1].strip() if "## 📝" in md_content else md_content


def attach_visual_evidence(chapters: List[Dict], media_dir: Path) -> List[Dict]:
    """Attach extracted frame paths to chapters without changing chapter evidence text."""
    evidence_path = media_dir / "visual_evidence.json"
    if not chapters or not evidence_path.is_file():
        return chapters
    try:
        frames = json.loads(evidence_path.read_text(encoding="utf-8")).get("frames", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return chapters
    if not frames:
        return chapters
    enriched = [dict(chapter) for chapter in chapters]
    for index, chapter in enumerate(enriched):
        if not chapter.get("screenshot"):
            frame = frames[min(index, len(frames) - 1)]
            chapter["screenshot"] = str(frame.get("path", ""))
    return enriched


def _write_temp_cookie(cookie: str) -> str:
    """Write cookie to temp file for yt-dlp / 写入临时cookie文件"""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="bili_cookie_")
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for item in cookie.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                f.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
    return path


def cleanup_task_workspace(task_dir: Path, output_root: Path) -> bool:
    """Remove a completed task's local artifacts only after vault export succeeds."""
    try:
        task_dir = task_dir.resolve()
        expected_parent = (Path(output_root).resolve() / "_tasks").resolve()
        if task_dir.parent != expected_parent:
            raise ValueError(f"Refusing to clean unexpected task path: {task_dir}")
        shutil.rmtree(task_dir)
        print(f"  🧹 已清理本地任务工件: {task_dir}")
        return True
    except Exception as error:
        print(f"  ⚠ 本地任务清理失败: {error}")
        return False


def expand_douyin_profiles(
    raw_inputs: List[str], out_dir: Path, *, resolve_short_links: bool = True,
) -> Tuple[List[str], int]:
    """Expand profile inputs to canonical public video URLs and persist an audit report."""
    expanded: List[str] = []
    seen: set[str] = set()
    failures = 0
    for raw_input in raw_inputs:
        try:
            link = normalize_input(raw_input, resolve_short_links=resolve_short_links)
        except LinkNormalizationError:
            if raw_input not in seen:
                expanded.append(raw_input)
                seen.add(raw_input)
            continue
        if not is_profile_url(link.canonical_url):
            if raw_input not in seen:
                expanded.append(raw_input)
                seen.add(raw_input)
            continue
        print(f"👤 正在枚举抖音主页: {link.canonical_url}")
        try:
            result = enumerate_profile_videos(link.canonical_url)
            report_path = write_profile_report(result, out_dir)
        except Exception as error:
            failures += 1
            print(f"❌ 抖音主页枚举失败: {error}")
            continue
        print(
            f"   页面作品数: {result.displayed_count if result.displayed_count is not None else '未知'} | "
            f"本次公开可访问: {len(result.videos)} | 分页响应: {result.response_pages}"
        )
        if result.count_mismatch:
            print("   ⚠ 计数不一致，原因待核验；不推断为私密或删除")
        print(f"   枚举报告: {report_path}")
        if not result.videos:
            failures += 1
            continue
        for video in result.videos:
            if video.url not in seen:
                expanded.append(video.url)
                seen.add(video.url)
    return expanded, failures


# ═══════════════════════════════════════════════════════════════════════════
# Main / 主流程
# ═══════════════════════════════════════════════════════════════════════════

def process_single(raw_input: str, env: NetworkEnv, out_dir: Path,
                   with_frames: bool = False, no_import: bool = False,
                   extract_only: bool = False, resolve_short_links: bool = True,
                   keep_local: bool = False,
                   skill_state: Optional[SkillState] = None) -> bool:
    """Process one copied link/message after normalizing it to a content URL."""
    try:
        link = normalize_input(raw_input, resolve_short_links=resolve_short_links)
    except LinkNormalizationError as e:
        print(f"❌ 链接清洗失败: {e}")
        return False

    url = link.canonical_url
    if not link.is_local_path and (link.extracted_url != url or link.resolved_url):
        print(f"🔗 原始输入已清洗 → {url}")
        if link.removed_params:
            print(f"   已移除追踪参数: {', '.join(link.removed_params)}")
        if link.resolution_error:
            print(f"   ⚠ 短链未解析，继续使用原短链: {link.resolution_error}")
    task_id = hashlib.md5(url.encode()).hexdigest()[:12]
    consecutive_failures = 0  # 同一 URL 连续失败计数

    platform = detect_platform(url)
    if not platform:
        print(f"❌ 无法识别平台: {url}")
        return False

    # Check platform availability / 检查平台可用性
    status = env.platform_status.get(platform, "unknown")
    if status == "need_proxy":
        print(f"❌ {platform} 在当前网络环境不可用（需代理）")
        return False
    if status == "need_browser":
        print(f"❌ {platform} 需要浏览器（Edge/Chrome）→ 当前不可用，请安装 Edge 或 Chrome")
        return False
    if skill_state:
        missing = skill_state.missing_required(platform)
        if missing:
            print(f"❌ 必要依赖缺失: {', '.join(missing)}")
            return False

    task_store = TaskStore(out_dir)
    task = task_store.create_or_resume(
        task_id=task_id, raw_input=raw_input, canonical_url=url, platform=platform,
        metadata={"link_normalization": link.to_dict()},
    )
    if is_duplicate(url):
        if task.stage != TaskStage.COMPLETED:
            task_store.skip(task_id, "legacy_registry_completed")
        print(f"⏭ 跳过(已处理): {url}")
        return True

    task_dir = task_store.task_dir(task_id)
    douyin_provider = DouyinProvider()
    task_store.transition(task_id, TaskStage.NORMALIZED, data={"task_dir": str(task_dir)})
    if douyin_provider.supports(platform):
        douyin_provider.write_source_manifest(
            task_dir, raw_input=raw_input, canonical_url=url, normalized_link=link.to_dict(),
        )

    print(f"\n{'='*60}")
    print(f"🔍 [{platform}] {url}")
    print(f"{'='*60}")

    ensure_ffmpeg()
    save_progress(task_id, "extracting", {
        "url": url,
        "platform": platform,
        "link_normalization": link.to_dict(),
    })
    task_store.transition(task_id, TaskStage.EXTRACTING)

    # Extract / 提取——增强兜底链。已完成媒体阶段的任务直接复用工件，
    # 不因摘要或导入失败而再次触发抖音下载和 ASR。
    resumed_summary_value = str(task.metadata.get("summary_path", "") or "")
    resumed_summary = Path(resumed_summary_value) if resumed_summary_value else None
    md_path = resumed_summary if resumed_summary and resumed_summary.is_file() else None
    if md_path:
        print(f"  ↩ 复用已有提取工件: {md_path}")
    try:
        if not md_path and platform in ("douyin", "tiktok"):
            if skill_state:
                preferred = skill_state.preferred_method("douyin")
                md_path, extraction_method, cookie_issue, extraction_error = run_douyin_routed(
                    url, task_dir, with_frames, preferred_method=preferred,
                )
                skill_state.record_extraction(
                    "douyin", success=bool(md_path), method=extraction_method,
                    error=extraction_error, cookie_issue=cookie_issue,
                )
            else:
                md_path = run_douyin(url, task_dir, with_frames)
            # 抖音兜底：如果 extract_douyin 失败，用 yt-dlp + whisper 直接下载
            if not md_path:
                print(f"  ⚠ 抖音提取失败，尝试 yt-dlp + whisper 兜底...")
                md_path = _whisper_fallback_douyin(url, task_dir)
        elif not md_path and platform == "bilibili":
            md_path = run_bilibili(url, task_dir, env)
            # B站兜底：如果 yt-dlp 和 hearsay 都失败，尝试直接 whisper
            if not md_path:
                print(f"  ⚠ B站提取失败，尝试直接 whisper 兜底...")
                md_path = _whisper_fallback_bilibili(url, task_dir)
        elif not md_path and platform == "youtube":
            print("❌ YouTube 不可用，请使用代理")
            return False
        elif not md_path and platform in ("wechat", "xiaohongshu"):
            print(f"❌ {platform} 需要浏览器（Edge/Chrome），请安装后重试")
            return False
        elif not md_path and platform in ("podcast", "local"):
            md_path = run_hearsay(url, task_dir, is_local=(platform == "local"))
    except Exception as e:
        task_store.fail(task_id, str(e), data={"during": "extracting"})
        print(f"❌ 提取异常: {e}")
        return False

    if not md_path or not md_path.exists():
        task_store.fail(task_id, "content extraction returned no markdown", data={"during": "extracting"})
        print("❌ 内容提取失败")
        return False

    save_progress(task_id, "extracted", {"output": str(md_path)})
    artifact_data = {"summary_path": str(md_path)}
    if douyin_provider.supports(platform):
        artifact_data["artifacts"] = douyin_provider.build_artifact_manifest(task_dir, md_path)
    task_store.transition(task_id, TaskStage.MEDIA_READY, data=artifact_data)

    # Extract-only mode: stop here, let ZCode handle AI steps / 仅提取模式
    if extract_only:
        task_store.complete(task_id, data={"mode": "extract_only", "note_path": str(md_path)})
        print(f"✅ 提取完成 (extract-only) → {md_path}")
        return True

    # Read content / 读取内容
    md_content = md_path.read_text(encoding="utf-8")
    title_match = re.search(r"^title:\s*\"(.+?)\"", md_content, re.MULTILINE)
    if not title_match:
        title_match = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    # ── AI 分析：统一调用（取代旧的6步串行链）──
    save_progress(task_id, "ai_analysis")
    task_store.transition(task_id, TaskStage.ANALYZING)
    transcript_text = transcript_for_analysis(md_path, md_content)
    
    ai_result = generate_structured_analysis(title, transcript_text)
    save_progress(task_id, "ai_analysis", {"verification": ai_result.verification})
    analysis_path = md_path.parent / "analysis.json"
    analysis_path.write_text(json.dumps({
        "category": ai_result.category, "tags": ai_result.tags, "summary": ai_result.summary,
        "chapters": ai_result.chapters, "highlights": ai_result.highlights,
        "glossary": ai_result.glossary, "flashcards": ai_result.flashcards,
        "deep_questions": ai_result.deep_questions, "rating": ai_result.rating,
        "rating_detail": ai_result.rating_detail, "verification": ai_result.verification,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    task_store.transition(task_id, TaskStage.ANALYZED, data={"analysis_path": str(analysis_path)})
    
    # ── Knowledge Graph / 知识图谱 ──
    related_notes = build_related_notes(ai_result.tags, title)
    
    # ── 重新组装完整 Markdown ──
    try:
        _write_summary(
            md_path=md_path, url=url, platform=platform,
            title=title, author=author_from_md(md_content),
            duration_sec=duration_from_md(md_content),
            transcript_path=None,
            transcript_text=transcript_text,
            category=ai_result.category, tags=ai_result.tags,
            summary=ai_result.summary,
            chapters=attach_visual_evidence(ai_result.chapters, md_path.parent),
            highlights=ai_result.highlights,
            deep_thinking=ai_result.deep_questions,
            glossary=ai_result.glossary,
            rating=ai_result.rating,
            rating_detail=ai_result.rating_detail,
            flashcards=ai_result.flashcards,
            related_notes=related_notes,
            task_id=task_id,
            include_transcript=False,
        )
    except Exception as e:
        task_store.fail(task_id, str(e), data={"during": "markdown_render"})
        print(f"❌ Markdown 组装失败: {e}")
        return False

    # ── Import / 导入 ──
    imported = False
    vault_note_path: Optional[Path] = None
    if not no_import:
        save_progress(task_id, "importing")
        task_store.transition(task_id, TaskStage.EXPORTING)

        # Obsidian is the primary, portable Markdown vault for this pipeline.
        if env.obsidian_vault:
            vault_note_path = export_to_obsidian(md_path, env.obsidian_vault)
            imported = vault_note_path is not None

        # SiYuan remains an optional fallback for users who configure it.
        if not imported and env.has_siyuan:
            if not env.siyuan_running:
                env.siyuan_running = ensure_siyuan_running()
            if env.siyuan_running:
                imported = import_to_siyuan(md_path, title)

    # The task directory is the canonical local copy.  Do not flatten every
    # note into the output root, where identical summary.md names collide.
    if not imported:
        print(f"  💾 已保存本地: {md_path}")

    # Mark processed / 标记已处理（含评分和错误记录）
    final_note_path = str(vault_note_path or md_path)
    mark_processed(url, final_note_path, {
        "title": title,
        "platform": platform,
        "raw_input": raw_input,
        "resolved_url": link.resolved_url or "",
        "removed_tracking_params": list(link.removed_params),
        "verification": ai_result.verification,
        "category": ai_result.category,
        "tags": ai_result.tags,
        "rating": ai_result.rating,
        "consecutive_failures": 0,
        "has_highlights": bool(ai_result.highlights),
        "has_glossary": bool(ai_result.glossary),
        "has_chapters": bool(ai_result.chapters),
        "has_flashcards": bool(ai_result.flashcards),
    })
    cleaned = bool(imported and vault_note_path and not keep_local)
    task_store.complete(task_id, data={
        "note_path": final_note_path,
        "imported": imported,
        "vault_note_path": final_note_path if vault_note_path else "",
        "local_artifacts_cleaned": cleaned,
    })
    if cleaned:
        cleanup_task_workspace(task_dir, out_dir)

    print(f"✅ 完成 → {final_note_path}")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse flags / 解析参数
    urls = []
    with_frames = False; no_import = False; dry_run = False; extract_only = False; out_dir = DEFAULT_OUT
    resolve_short_links = True
    keep_local = False

    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--frames":
            with_frames = True
        elif a == "--no-import":
            no_import = True
        elif a == "--extract-only":
            extract_only = True
        elif a == "--dry-run":
            dry_run = True
        elif a == "--no-resolve-links":
            resolve_short_links = False
        elif a == "--keep-local":
            keep_local = True
        elif a == "--out" and i + 1 < len(sys.argv):
            i += 1; out_dir = Path(sys.argv[i])
        elif not a.startswith("--"):
            urls.append(a)
        i += 1

    if not urls:
        print("❌ 请提供至少一个链接")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    skill_state = SkillState(out_dir)
    environment_report = skill_state.check_environment()
    skill_state.print_environment_report(environment_report)
    print()

    # Detect environment / 检测环境
    print("🌐 正在检测网络环境...")
    env = detect_network()
    print(f"   国内网络: {'是' if env.is_china else '否'} | "
          f"YouTube: {'通' if env.youtube_ok else '堵'} | "
          f"B站: {'通' if env.bilibili_ok else '堵'} | "
          f"浏览器: {'有' if env.has_browser else '无'} | "
          f"思源: {'运行中' if env.siyuan_running else '已安装' if env.has_siyuan else '未安装'} | "
          f"Obsidian: {'已配置' if env.obsidian_vault else '未配置'}")
    print()

    if dry_run:
        for raw_input in urls:
            try:
                link = normalize_input(raw_input, resolve_short_links=resolve_short_links)
            except LinkNormalizationError as e:
                print(f"  [dry-run] 无效输入: {e}")
                continue
            platform = detect_platform(link.canonical_url) or "unknown"
            status = env.platform_status.get(platform, "unknown")
            print(f"  [dry-run] {platform} ({status}): {link.canonical_url}")
            if link.extracted_url != link.canonical_url or link.resolved_url:
                print(f"            原始: {link.extracted_url}")
            if link.removed_params:
                print(f"            移除追踪参数: {', '.join(link.removed_params)}")
        print("\n[dry-run] 未实际执行")
        sys.exit(0)

    urls, profile_failures = expand_douyin_profiles(
        urls, out_dir, resolve_short_links=resolve_short_links,
    )
    if not urls:
        print("❌ 没有可处理的视频链接")
        sys.exit(1)

    # Process all URLs / 批量处理
    success = 0; fail = 0
    for raw_input in urls:
        if process_single(
            raw_input, env, out_dir, with_frames, no_import, extract_only,
            resolve_short_links, keep_local, skill_state,
        ):
            success += 1
        else:
            fail += 1

    fail += profile_failures
    if fail > 0:
        print(f"    ⚠ 失败: {fail} 个 URL")
    print(f"\n{'='*60}")
    print(f"📊 处理完成: {success} 成功, {fail} 失败 (共 {len(urls)} 个)")
    print(f"📁 输出目录: {out_dir}")


if __name__ == "__main__":
    main()
