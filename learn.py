#!/usr/bin/env python3
"""
Learn Skill — Universal Video/Audio → Knowledge Base Import
═══════════════════════════════════════════════════════════
One command: URL → extract → AI classify → import to your note system.

Usage:
    python learn.py "<url>" [<url2> ...] [--frames] [--out DIR] [--no-import] [--dry-run]

Supports: Douyin, TikTok, Bilibili, YouTube, podcasts, local files (auto-detects network).
Outputs: SiYuan (auto-start), Obsidian vault, or plain local markdown.

学习 Skill — 通用视频/音频 → 知识库导入
════════════════════════════════════════
一条命令：链接 → 内容提取 → AI 分类 → 导入笔记系统。

    用法: python learn.py "<链接>" [<链接2> ...] [--frames] [--out 目录] [--no-import] [--dry-run]

    支持: 抖音、TikTok、B站、YouTube、播客、本地文件（自动检测网络环境）。
    输出: 思源笔记（自动启动）、Obsidian、或纯本地 Markdown。
"""

import sys, os, re, json, time, shutil, hashlib, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

# Load .env file if present / 加载 .env 文件
_ENV_FILE = Path(__file__).parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k not in os.environ:
                os.environ[_k] = _v

# ═══════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════
PYTHON = r"C:\Python312\python.exe"
FFMPEG_BIN = r"C:\Tools\ffmpeg-8.1.1-essentials_build\bin"
TOOLS_DIR = Path(__file__).parent.resolve()
DOUYIN2MD = TOOLS_DIR / "douyin2md.py"
PROJECT_ROOT = TOOLS_DIR.parent
DEFAULT_OUT = PROJECT_ROOT / "learn-output"
REGISTRY_FILE = DEFAULT_OUT / ".registry.json"
PROGRESS_FILE = DEFAULT_OUT / ".progress.json"

# SiYuan / 思源
SIYUAN_PATHS = [
    r"D:\Program Files\siyuan\SiYuan.exe",
    r"C:\Program Files\siyuan\SiYuan.exe",
    r"D:\SiYuan\SiYuan.exe",
]
SIYUAN_API = os.environ.get("SIYUAN_API", "http://127.0.0.1:6806")
SIYUAN_TOKEN = os.environ.get("SIYUAN_TOKEN", "")
SIYUAN_STARTUP_WAIT = 15  # seconds / 秒

# DeepSeek AI — set DEEPSEEK_API_KEY in env or .env file
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Obsidian (international users / 国际用户)
OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")

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
    has_chrome: bool = False       # Chrome browser? / Chrome 浏览器
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
            "wechat":      "ok" if self.has_chrome else "need_chrome",
            "xiaohongshu": "ok" if self.has_chrome else "need_chrome",
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
    env.bilibili_ok = _check("https://www.bilibili.com", 5)
    env.youtube_ok = _check("https://www.youtube.com", 5)
    env.github_ok = _check("https://github.com", 5)
    env.jina_ok = _check("https://r.jina.ai", 5)
    env.is_china = env.bilibili_ok and not env.youtube_ok

    # Chrome / Chrome 检测
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    env.has_chrome = any(Path(p).exists() for p in chrome_paths)

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
    "douyin":      [r"(?:v\.douyin\.com|www\.douyin\.com/video)"],
    "tiktok":      [r"(?:tiktok\.com|vm\.tiktok\.com)"],
    "bilibili":    [r"bilibili\.com/video/"],
    "youtube":     [r"(?:youtube\.com/watch|youtu\.be/)"],
    "wechat":      [r"mp\.weixin\.qq\.com"],
    "xiaohongshu": [r"xiaohongshu\.com"],
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
        urllib.request.urlopen(req, timeout=3)
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
                urllib.request.urlopen(req, timeout=2)
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
    progress[task_id] = {"step": step, "data": data or {}, "time": datetime.now().isoformat()}
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
    """Clean transcript: dedup, fix all-caps, merge fragments / 清洗字幕"""
    lines = text.splitlines()
    cleaned = []
    prev = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Remove speaker labels like "Speaker 1:" / 去掉说话人标签
        line = re.sub(r'^\s*(?:Speaker\s*\d+|SPEAKER\s*\d+)\s*[:：]\s*', '', line, flags=re.IGNORECASE)

        # Fix ALL CAPS lines (>80% uppercase) / 修正全大写行
        alpha_chars = [c for c in line if c.isalpha()]
        if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.8:
            line = line.lower().capitalize()

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
# Flashcard Generation / 闪卡生成
# ═══════════════════════════════════════════════════════════════════════════

FLASHCARD_PROMPT = """Based on the following transcript, generate 5 question-answer flashcards.
Each should test understanding of a key concept, not trivia.
Format as JSON array: [{"q": "...", "a": "..."}, ...]

Transcript:
{transcript}"""


def generate_flashcards(transcript: str) -> List[Dict[str, str]]:
    """Generate Q&A flashcards from transcript / 从转录生成闪卡"""
    import requests
    text = transcript[:3000]  # limit / 限制长度
    prompt = FLASHCARD_PROMPT.format(transcript=text)

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 800,
            },
            timeout=30,
        )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON array / 提取JSON数组
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"  ⚠ 闪卡生成失败: {e}")
    return []


# ═══════════════════════════════════════════════════════════════════════════
# AI Classification / AI 分类
# ═══════════════════════════════════════════════════════════════════════════

CLASSIFY_PROMPT = """Analyze this content and provide:
1. A topic category (10 words max)
2. 3-5 tags (comma separated)

Title: {title}
Summary: {summary}

Reply in JSON: {{"category": "...", "tags": ["...", "..."]}}"""


def classify_content(title: str, summary: str) -> Dict:
    """Call DeepSeek for topic classification / 调用DeepSeek分类"""
    import requests
    prompt = CLASSIFY_PROMPT.format(title=title, summary=summary[:2000])

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 200,
            },
            timeout=30,
        )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return {"category": result.get("category", "未分类"),
                    "tags": result.get("tags", [])}
    except Exception as e:
        print(f"  ⚠ AI 分类失败: {e}")
    return {"category": "未分类", "tags": []}


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

def run_douyin(url: str, out_dir: Path, with_frames: bool = False) -> Optional[Path]:
    """Douyin/TikTok via tiktok-extractor / 抖音/TikTok 提取"""
    cmd = [PYTHON, str(DOUYIN2MD), url, "--out", str(out_dir)]
    if with_frames:
        cmd.append("--frames")
    print(f"  ▶ 抖音提取: {DOUYIN2MD.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"  ❌ 提取失败: {result.stderr.strip()}", file=sys.stderr)
        return None
    for line in result.stdout.splitlines():
        if "完成" in line and "→" in line:
            p = Path(line.split("→")[-1].strip())
            if p.exists():
                return p
    candidates = list(out_dir.rglob("summary.md"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def run_bilibili(url: str, out_dir: Path, env: NetworkEnv) -> Optional[Path]:
    """Bilibili: yt-dlp subtitles → hearsay whisper fallback / B站提取"""
    import yt_dlp

    bvid = _extract_bvid(url)
    video_dir = out_dir / f"bilibili_{bvid}"
    video_dir.mkdir(parents=True, exist_ok=True)
    srt_path = video_dir / "subtitle.srt"
    txt_path = video_dir / "transcript.txt"

    # Step 1: yt-dlp download subtitles / 下载字幕
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
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
# Summary writer — unified template / 统一模板
# ═══════════════════════════════════════════════════════════════════════════

def _write_summary(md_path: Path, url: str, platform: str,
                   title: str, author: str, duration_sec: int,
                   transcript_path: Optional[Path] = None):
    """Write standardized summary.md with YAML frontmatter / 写入标准化Markdown"""
    transcript = ""
    if transcript_path and transcript_path.exists():
        transcript = transcript_path.read_text(encoding="utf-8")

    duration_str = _format_duration(duration_sec) if duration_sec else ""

    md = f"""---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration_str}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
tags: []
category: "未分类"
---

# {title}

## 📋 Metadata / 元数据
- **Platform / 平台**: {platform}
- **Author / 作者**: {author}
- **Duration / 时长**: {duration_str}
- **Source / 来源**: [Original Link / 原始链接]({url})
- **Extracted / 提取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

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
            timeout=10,
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


def export_to_obsidian(md_path: Path, vault_path: str) -> bool:
    """Export to Obsidian vault / 导出到 Obsidian 库"""
    try:
        dest = Path(vault_path) / "learn" / md_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md_path, dest)
        print(f"  ✅ 已导出到 Obsidian: {dest}")
        return True
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


# ═══════════════════════════════════════════════════════════════════════════
# Main / 主流程
# ═══════════════════════════════════════════════════════════════════════════

def process_single(url: str, env: NetworkEnv, out_dir: Path,
                   with_frames: bool = False, no_import: bool = False) -> bool:
    """Process a single URL / 处理单个链接"""
    task_id = hashlib.md5(url.encode()).hexdigest()[:12]

    # Dedup check / 去重检查
    if is_duplicate(url):
        print(f"⏭ 跳过(已处理): {url}")
        return True

    platform = detect_platform(url)
    if not platform:
        print(f"❌ 无法识别平台: {url}")
        return False

    # Check platform availability / 检查平台可用性
    status = env.platform_status.get(platform, "unknown")
    if status == "need_proxy":
        print(f"❌ {platform} 在当前网络环境不可用（需代理）")
        return False
    if status == "need_chrome":
        print(f"❌ {platform} 需要 Chrome 浏览器（当前未安装）")
        return False

    print(f"\n{'='*60}")
    print(f"🔍 [{platform}] {url}")
    print(f"{'='*60}")

    ensure_ffmpeg()
    save_progress(task_id, "extracting", {"url": url, "platform": platform})

    # Extract / 提取
    md_path = None
    try:
        if platform in ("douyin", "tiktok"):
            md_path = run_douyin(url, out_dir, with_frames)
        elif platform == "bilibili":
            md_path = run_bilibili(url, out_dir, env)
        elif platform == "youtube":
            print("❌ YouTube 不可用，请使用代理")
            return False
        elif platform in ("wechat", "xiaohongshu"):
            print(f"❌ {platform} 需要 Chrome 浏览器")
            return False
        elif platform in ("podcast", "local"):
            md_path = run_hearsay(url, out_dir, is_local=(platform == "local"))
    except Exception as e:
        print(f"❌ 提取异常: {e}")
        return False

    if not md_path or not md_path.exists():
        print("❌ 内容提取失败")
        return False

    save_progress(task_id, "extracted", {"output": str(md_path)})

    # Read content / 读取内容
    md_content = md_path.read_text(encoding="utf-8")
    title_match = re.search(r"^title:\s*\"(.+?)\"", md_content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    # AI classify / AI分类
    save_progress(task_id, "classifying")
    summary = md_content.split("## 📝")[-1].strip()[:2000] if "## 📝" in md_content else md_content[:2000]
    classification = classify_content(title, summary)
    print(f"  🏷 AI 分类: {classification['category']} | 标签: {', '.join(classification['tags'])}")

    # Flashcards / 闪卡
    if not no_import and len(md_content) > 500:
        flashcards = generate_flashcards(md_content)
        if flashcards:
            fc_section = "\n\n## 🃏 Flashcards / 闪卡\n\n"
            for i, fc in enumerate(flashcards, 1):
                fc_section += f"**Q{i}**: {fc.get('q', '?')}\n\n**A{i}**: {fc.get('a', '?')}\n\n"
            md_content += fc_section
            print(f"  🃏 已生成 {len(flashcards)} 张闪卡")

    # Update frontmatter / 更新frontmatter
    tags_yml = ", ".join(f'"{t}"' for t in classification["tags"])
    md_content = re.sub(r"^tags:\s*\[.*?\]", f"tags: [{tags_yml}]", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^category:\s*\".*?\"",
                        f'category: "{classification["category"]}"', md_content, flags=re.MULTILINE)

    if "## 🤖 AI 分类" not in md_content:
        ai_section = f"""
## 🤖 AI Classification / AI 分类
- **Category / 主题**: {classification['category']}
- **Tags / 标签**: {' #'.join(classification['tags'])}
"""
        md_content = md_content.replace("## 📝", ai_section + "\n## 📝")
    md_path.write_text(md_content, encoding="utf-8")

    # Import / 导入
    imported = False
    if not no_import:
        save_progress(task_id, "importing")

        # Try SiYuan first / 优先思源
        if env.has_siyuan:
            if not env.siyuan_running:
                env.siyuan_running = ensure_siyuan_running()
            if env.siyuan_running:
                imported = import_to_siyuan(md_path, title)

        # Fallback to Obsidian / Obsidian备选
        if not imported and env.obsidian_vault:
            imported = export_to_obsidian(md_path, env.obsidian_vault)

    # Always save local copy / 总是保存本地副本
    if not imported:
        local_copy = out_dir / md_path.name
        if local_copy != md_path:
            shutil.copy2(md_path, local_copy)
        print(f"  💾 已保存本地: {local_copy}")

    # Mark processed / 标记已处理
    mark_processed(url, str(md_path), {
        "title": title,
        "platform": platform,
        "category": classification["category"],
        "tags": classification["tags"],
    })

    print(f"✅ 完成 → {md_path}")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse flags / 解析参数
    urls = []
    with_frames = False; no_import = False; dry_run = False; out_dir = DEFAULT_OUT

    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--frames":
            with_frames = True
        elif a == "--no-import":
            no_import = True
        elif a == "--dry-run":
            dry_run = True
        elif a == "--out" and i + 1 < len(sys.argv):
            i += 1; out_dir = Path(sys.argv[i])
        elif not a.startswith("--"):
            urls.append(a)
        i += 1

    if not urls:
        print("❌ 请提供至少一个链接")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Detect environment / 检测环境
    print("🌐 正在检测网络环境...")
    env = detect_network()
    print(f"   国内网络: {'是' if env.is_china else '否'} | "
          f"YouTube: {'通' if env.youtube_ok else '堵'} | "
          f"B站: {'通' if env.bilibili_ok else '堵'} | "
          f"Chrome: {'有' if env.has_chrome else '无'} | "
          f"思源: {'运行中' if env.siyuan_running else '已安装' if env.has_siyuan else '未安装'} | "
          f"Obsidian: {'已配置' if env.obsidian_vault else '未配置'}")
    print()

    if dry_run:
        for url in urls:
            platform = detect_platform(url) or "unknown"
            status = env.platform_status.get(platform, "unknown")
            print(f"  [dry-run] {platform} ({status}): {url}")
        print("\n[dry-run] 未实际执行")
        sys.exit(0)

    # Process all URLs / 批量处理
    success = 0; fail = 0
    for url in urls:
        if process_single(url, env, out_dir, with_frames, no_import):
            success += 1
        else:
            fail += 1

    print(f"\n{'='*60}")
    print(f"📊 处理完成: {success} 成功, {fail} 失败 (共 {len(urls)} 个)")
    print(f"📁 输出目录: {out_dir}")


if __name__ == "__main__":
    main()
