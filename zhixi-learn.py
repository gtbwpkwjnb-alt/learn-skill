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

# ── Unified Timeouts / 统一超时 ──────────────────────────────────────────────
TIMEOUT_LLM = 45          # DeepSeek API 调用（秒）
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

# DeepSeek AI — set DEEPSEEK_API_KEY in env or .env file
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ── API Safety Guard / 安全防护 ──────────────────────────────────────────────
# 防止意外批量调用导致 API 费用超支
API_CALL_LOG = DEFAULT_OUT / ".api_call_log.json"
MAX_API_CALLS_PER_RUN = 50       # 单次运行最大 API 调用次数
MAX_API_CALLS_PER_DAY = 200      # 每日最大 API 调用次数
MAX_API_CALLS_PER_MINUTE = 15    # 每分钟最大 API 调用次数（新增限流）
BATCH_CONFIRM_THRESHOLD = 3      # 超过此数量的 URL 需确认后才执行
MAX_CONSECUTIVE_FAILURES = 3     # 连续失败上限，超限自动跳过
API_CALL_INTERVAL = 0.5          # 同一 URL 各 API 调用间延迟（秒）
URL_INTERVAL = 1.0               # 各 URL 处理间延迟（秒）

# Obsidian (international users / 国际用户)
OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")

# ═══════════════════════════════════════════════════════════════════════════
# API 重试 & 错误分类 / API Retry & Error Classification
# ═══════════════════════════════════════════════════════════════════════════

def _classify_api_error(e: Exception) -> str:
    """Classify an API error into categories for retry decision.
    
    Returns: "transient" | "rate_limit" | "auth" | "permanent"
    """
    import requests
    if isinstance(e, requests.exceptions.Timeout):
        return "transient"
    if isinstance(e, requests.exceptions.ConnectionError):
        return "transient"
    if isinstance(e, requests.exceptions.HTTPError):
        status = e.response.status_code if e.response is not None else 0
        if status == 429:
            return "rate_limit"
        if status in (401, 403):
            return "auth"
        if status >= 500:
            return "transient"
        return "permanent"
    if isinstance(e, requests.exceptions.RequestException):
        return "transient"
    # JSON / parsing errors — permanent
    if isinstance(e, (json.JSONDecodeError, KeyError, IndexError, TypeError)):
        return "permanent"
    return "transient"


def _api_call_with_retry(
    func,
    max_retries: int = 3,
    retry_delays: tuple = (1, 2, 4),
    label: str = "API",
) -> tuple:
    """Call an API function with exponential backoff retry.
    
    Args:
        func: Callable that returns (response_json, ...) or raises
        max_retries: Max retry attempts
        retry_delays: Delay in seconds between retries (exponential)
        label: Human-readable label for logging
        
    Returns:
        (response_json, other_values...) on success
        Raises the last exception on permanent failure.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = func()
            return result
        except Exception as e:
            last_error = e
            err_type = _classify_api_error(e)
            
            if err_type == "auth":
                print(f"  ⚠ {label}: API 认证失败（{e}），停止重试")
                raise
            if err_type == "permanent":
                print(f"  ⚠ {label}: 不可恢复错误（{e}），停止重试")
                raise
            if attempt < max_retries:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                print(f"  ⚠ {label}: 第{attempt+1}次失败（{err_type}），{delay}s 后重试...")
                time.sleep(delay)
            else:
                print(f"  ❌ {label}: 已重试 {max_retries} 次仍失败: {e}")
                raise
    raise last_error  # unreachable, but satisfies type checker


# ── Rate Limiting / 速率限制 ──────────────────────────────────────────────────

_rate_limit_window: List[float] = []  # timestamps of recent API calls (seconds)


def _check_rate_limit() -> bool:
    """Check and enforce per-minute rate limit. Returns True if allowed."""
    global _rate_limit_window
    now = time.time()
    # Purge entries older than 60s
    _rate_limit_window = [ts for ts in _rate_limit_window if now - ts < 60]
    if len(_rate_limit_window) >= MAX_API_CALLS_PER_MINUTE:
        sleep_time = 60 - (now - _rate_limit_window[0])
        if sleep_time > 0:
            print(f"  ⏳ 达每分钟上限 ({MAX_API_CALLS_PER_MINUTE})，等待 {sleep_time:.0f}s...")
            time.sleep(sleep_time)
        _rate_limit_window.clear()
    _rate_limit_window.append(time.time())
    return True


# ── Token Tracking / Token 追踪 ───────────────────────────────────────────────

def _extract_usage(resp_json: dict) -> dict:
    """Extract token usage from DeepSeek API response."""
    usage = resp_json.get("usage", {}) or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _estimate_cost(usage: dict) -> float:
    """Estimate cost in USD from token usage (DeepSeek pricing)."""
    # DeepSeek: ~$0.5/M input tokens, ~$2/M output tokens
    prompt_cost = usage.get("prompt_tokens", 0) * 0.5 / 1_000_000
    completion_cost = usage.get("completion_tokens", 0) * 2.0 / 1_000_000
    return round(prompt_cost + completion_cost, 6)


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
    "douyin":      [r"(?:v\.douyin\.com|www\.douyin\.com/video|www\.iesdouyin\.com/share/video|douyin\.com/user/.*\bmodal_id=)"],
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

STRUCTURED_ANALYSIS_PROMPT = """You are a professional learning analyst. Analyze the following transcript and return a comprehensive structured JSON.

Rules:
1. Detect natural topic boundaries as chapters, each with an estimated start time (MM:SS).
2. For each chapter, extract 3-5 key points and a 1-sentence summary.
3. Generate a hierarchical 3-paragraph overall summary (first=TL;DR, second=detail, third=implications).
4. Extract 5-8 timestamped highlights (MM:SS format where possible).
5. Identify 3-8 key terms with clear definitions.
6. Rate on three 1-5 scales: information_density, practicality, clarity, plus overall.
7. Generate 5 Q&A flashcards testing conceptual understanding.
8. Generate 2-3 deep reflection questions with thoughtful answers.
9. Suggest a category (≤10 words) and 3-5 tags.

Return valid JSON only (no markdown wrappers):
{
  "category": "...",
  "tags": ["..."],
  "summary": "TL;DR paragraph.\n\nDetail paragraph covering key arguments and evidence.\n\nImplications paragraph: why this matters.",
  "chapters": [
    {"title": "...", "time": "MM:SS", "points": ["...", "..."], "summary": "..."}
  ],
  "highlights": [
    {"time": "MM:SS", "text": "..."}
  ],
  "glossary": [
    {"term": "...", "definition": "..."}
  ],
  "rating": {"information_density": 4.0, "practicality": 4.0, "clarity": 4.0, "overall": 4.0},
  "flashcards": [
    {"q": "...", "a": "..."}
  ],
  "deep_questions": [
    {"q": "...", "a": "..."}
  ]
}

Title: {title}

Transcript:
{transcript}"""


FLASHCARD_THRESHOLD = 500


def _call_deepseek(prompt: str, temperature: float = 0.3, max_tokens: int = 800,
                   call_type: str = "api", label: str = "API") -> tuple:
    """Unified DeepSeek API call with retry, rate limiting, and token tracking.
    
    Returns:
        (response_text, usage_dict)
    Raises on permanent failure.
    """
    import requests
    
    _check_rate_limit()
    
    def _do_call():
        resp = requests.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=TIMEOUT_LLM,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        usage = _extract_usage(data)
        return text, usage
    
    return _api_call_with_retry(_do_call, max_retries=3, label=label)


# ═══════════════════════════════════════════════════════════════════════════
# Unified Structured Analysis — 1 API call replaces old 6 calls
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StructuredAnalysis:
    """Result of a single unified AI analysis call."""
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


def generate_structured_analysis(title: str, transcript: str) -> StructuredAnalysis:
    """Single unified AI call that produces all analysis sections.
    
    Replaces: classify_content + generate_highlights + generate_deep_thinking
              + generate_glossary + generate_rating + generate_flashcards
    """
    result = StructuredAnalysis()
    
    if not DEEPSEEK_KEY:
        print("  ⚠ DEEPSEEK_API_KEY 未配置，跳过 AI 分析")
        return result
    
    text = transcript[:5000]  # enough context for most content
    if len(transcript.strip()) < FLASHCARD_THRESHOLD:
        text = transcript[:4000]  # shorter content needs less
    
    prompt = STRUCTURED_ANALYSIS_PROMPT.format(title=title, transcript=text)
    
    try:
        resp_text, usage = _call_deepseek(
            prompt, temperature=0.3, max_tokens=2048,
            call_type="structured_analysis", label="AI综合分析"
        )
        _record_api_call("structured_analysis", title, "deepseek-chat", usage)
        
        # Parse JSON from response (find first { ... })
        match = re.search(r"\{[\s\S]*\}", resp_text)
        if not match:
            print(f"  ⚠ AI 返回格式异常，尝试提取 JSON 失败")
            print(f"  原始响应(前200字): {resp_text[:200]}")
            return result
        
        data = json.loads(match.group())
        
        result.category = data.get("category", "未分类")
        result.tags = data.get("tags", []) or []
        result.summary = data.get("summary", "") or ""
        result.chapters = data.get("chapters", []) or []
        result.highlights = data.get("highlights", []) or []
        result.glossary = data.get("glossary", []) or []
        result.flashcards = data.get("flashcards", []) or []
        result.deep_questions = data.get("deep_questions", []) or []
        
        rd = data.get("rating", {}) or {}
        if isinstance(rd, dict):
            result.rating_detail = rd
            overall = rd.get("overall", 0)
            result.rating = str(overall)
        
        print(f"  🏷 分类: {result.category} | 标签: {', '.join(result.tags)}")
        if result.chapters:
            print(f"  📑 章节: {len(result.chapters)} 个")
        if result.highlights:
            print(f"  ⭐ 亮点: {len(result.highlights)} 条")
        if result.glossary:
            print(f"  📚 术语: {len(result.glossary)} 条")
        if result.flashcards:
            print(f"  🃏 闪卡: {len(result.flashcards)} 张")
        if result.deep_questions:
            print(f"  🤔 深度思考: {len(result.deep_questions)} 组")
        if result.rating:
            print(f"  🌟 综合评分: {result.rating}/5")
        
    except json.JSONDecodeError as e:
        print(f"  ⚠ AI JSON 解析失败: {e}")
    except Exception as e:
        print(f"  ⚠ AI 综合分析失败: {e}")
    
    return result


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
        texts = [seg.text.strip() for seg in segments_iter]
        transcript_path = out_dir / "transcript.txt"
        transcript_path.write_text(" ".join(texts), encoding="utf-8")
        print(f"  ✅ Whisper 兜底转写完成 ({len(texts)} 段)")
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

def run_douyin(url: str, out_dir: Path, with_frames: bool = False) -> Optional[Path]:
    """Douyin/TikTok via tiktok-extractor / 抖音/TikTok 提取"""
    cmd = [PYTHON, str(DOUYIN2MD), url, "--out", str(out_dir)]
    if with_frames:
        cmd.append("--frames")
    print(f"  ▶ 抖音提取: {DOUYIN2MD.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SUBPROCESS)
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
                md += f"      {pt.replace('"', "'")[:40]}\n"
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
    return md


def _build_glossary_md(glossary: Optional[List[Dict]]) -> str:
    """Build glossary definition list markdown."""
    if not glossary:
        return ""
    return "\n".join(f"- **{g.get('term', '')}**: {g.get('definition', '')}"
                     for g in glossary) + "\n"


def _build_qa_list_md(items: Optional[List[Dict]], label_q: str = "Q",
                      label_a: str = "A") -> str:
    """Build Q&A formatted markdown (for flashcards and deep thinking)."""
    if not items:
        return ""
    md = ""
    for i, item in enumerate(items, 1):
        md += f"**{label_q}{i}:** {item.get('q', '')}\n"
        md += f"**{label_a}{i}:** {item.get('a', '')}\n\n"
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
                   rating_detail: Optional[Dict] = None):
    """Write hierarchical summary.md with all sections / 写入层级化Markdown"""
    transcript = ""
    if transcript_path and transcript_path.exists():
        transcript = transcript_path.read_text(encoding="utf-8")

    duration_str = _format_duration(duration_sec) if duration_sec else ""

    # Try external assemble module first
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "repos" / "learn-skill" / "scripts"))
        from assemble_md import assemble
        md = assemble(
            title=title, url=url, platform=platform, author=author,
            duration=duration_str, transcript=transcript,
            category=category, tags=tags or [],
            summary=summary, highlights=highlights,
            deep_thinking=deep_thinking, glossary=glossary,
            rating=rating, chapters=chapters,
            related_notes=related_notes, flashcards=flashcards,
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

---

## 📝 完整转录

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
    """Extract author from markdown frontmatter."""
    m = re.search(r"^author:\s*\"(.+?)\"", md_content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def duration_from_md(md_content: str) -> int:
    """Extract duration (in seconds) from markdown frontmatter."""
    m = re.search(r"^duration:\s*\"(.+?)\"", md_content, re.MULTILINE)
    if not m:
        return 0
    dur_str = m.group(1).strip()
    parts = [int(x) for x in dur_str.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


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


# ── API Safety Guard functions ───────────────────────────────────────────────
# 安全防护函数：API 调用计数、批量确认、调用日志

def _api_call_log_path() -> Path:
    API_CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    return API_CALL_LOG


def _load_api_call_log() -> dict:
    """加载 API 调用日志，按日期统计调用次数"""
    path = _api_call_log_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"calls": [], "daily_count": {}}


def _save_api_call_log(log: dict) -> None:
    path = _api_call_log_path()
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_api_call(call_type: str, url: str = "", model: str = "deepseek-chat",
                     usage: Optional[dict] = None) -> None:
    """记录一次 API 调用到本地日志（含 Token 消耗）"""
    today = datetime.now().strftime("%Y-%m-%d")
    log = _load_api_call_log()
    log.setdefault("calls", []).append({
        "time": datetime.now().isoformat(),
        "type": call_type,
        "url": url,
        "model": model,
        "usage": usage or {},
    })
    log.setdefault("daily_count", {})
    log["daily_count"][today] = log["daily_count"].get(today, 0) + 1
    # 累计 token
    if usage:
        log.setdefault("total_tokens", 0)
        log["total_tokens"] += usage.get("total_tokens", 0)
        log.setdefault("total_cost", 0.0)
        log["total_cost"] += _estimate_cost(usage)
    _save_api_call_log(log)


def _check_api_safety(urls_count: int) -> bool:
    """检查 API 调用是否在安全限额内，超限则报错退出"""
    today = datetime.now().strftime("%Y-%m-%d")
    log = _load_api_call_log()
    daily_used = log.get("daily_count", {}).get(today, 0)

    # 每个 URL 预计 1 次调用（统一结构化分析取代旧6步链）
    estimated_calls = urls_count * 1

    if estimated_calls > MAX_API_CALLS_PER_RUN:
        print(f"⚠ 安全拦截：本次预计 {estimated_calls} 次 API 调用，超过单次运行上限 {MAX_API_CALLS_PER_RUN}")
        print(f"  如需继续请设置环境变量 LEARN_SKIP_SAFETY=1 或减少 URL 数量")
        return False

    if daily_used + estimated_calls > MAX_API_CALLS_PER_DAY:
        print(f"⚠ 安全拦截：今日已用 {daily_used} 次 API 调用，"
              f"加上本次预计 {estimated_calls} 次将超过每日上限 {MAX_API_CALLS_PER_DAY}")
        print(f"  如需继续请设置环境变量 LEARN_SKIP_SAFETY=1，或明天再试")
        return False

    if urls_count > BATCH_CONFIRM_THRESHOLD and "LEARN_SKIP_SAFETY" not in os.environ:
        print(f"⚠ 批量处理警告：即将处理 {urls_count} 个链接，预计产生约 {estimated_calls} 次 API 调用")
        print(f"  按 Enter 继续，或 Ctrl+C 取消...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            print("\n❌ 已取消")
            return False

    return True


# ═══════════════════════════════════════════════════════════════════════════
# Main / 主流程
# ═══════════════════════════════════════════════════════════════════════════

def process_single(url: str, env: NetworkEnv, out_dir: Path,
                   with_frames: bool = False, no_import: bool = False,
                   extract_only: bool = False) -> bool:
    """Process a single URL / 处理单个链接"""
    task_id = hashlib.md5(url.encode()).hexdigest()[:12]
    consecutive_failures = 0  # 同一 URL 连续失败计数

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
    if status == "need_browser":
        print(f"❌ {platform} 需要浏览器（Edge/Chrome）→ 当前不可用，请安装 Edge 或 Chrome")
        return False

    print(f"\n{'='*60}")
    print(f"🔍 [{platform}] {url}")
    print(f"{'='*60}")

    ensure_ffmpeg()
    save_progress(task_id, "extracting", {"url": url, "platform": platform})

    # Extract / 提取——增强兜底链
    md_path = None
    try:
        if platform in ("douyin", "tiktok"):
            md_path = run_douyin(url, out_dir, with_frames)
            # 抖音兜底：如果 extract_douyin 失败，用 yt-dlp + whisper 直接下载
            if not md_path and DEEPSEEK_KEY:
                print(f"  ⚠ 抖音提取失败，尝试 yt-dlp + whisper 兜底...")
                md_path = _whisper_fallback_douyin(url, out_dir)
        elif platform == "bilibili":
            md_path = run_bilibili(url, out_dir, env)
            # B站兜底：如果 yt-dlp 和 hearsay 都失败，尝试直接 whisper
            if not md_path:
                print(f"  ⚠ B站提取失败，尝试直接 whisper 兜底...")
                md_path = _whisper_fallback_bilibili(url, out_dir)
        elif platform == "youtube":
            print("❌ YouTube 不可用，请使用代理")
            return False
        elif platform in ("wechat", "xiaohongshu"):
            print(f"❌ {platform} 需要浏览器（Edge/Chrome），请安装后重试")
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

    # Extract-only mode: stop here, let ZCode handle AI steps / 仅提取模式
    if extract_only:
        print(f"✅ 提取完成 (extract-only) → {md_path}")
        return True

    # Read content / 读取内容
    md_content = md_path.read_text(encoding="utf-8")
    title_match = re.search(r"^title:\s*\"(.+?)\"", md_content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    # ── AI 分析：统一调用（取代旧的6步串行链）──
    save_progress(task_id, "ai_analysis")
    transcript_text = md_content.split("## 📝")[-1].strip() if "## 📝" in md_content else md_content
    
    ai_result = generate_structured_analysis(title, transcript_text)
    
    # ── Knowledge Graph / 知识图谱 ──
    related_notes = build_related_notes(ai_result.tags, title)
    
    # ── 重新组装完整 Markdown ──
    _write_summary(
        md_path=md_path, url=url, platform=platform,
        title=title, author=author_from_md(md_content),
        duration_sec=duration_from_md(md_content),
        transcript_path=None,
        category=ai_result.category, tags=ai_result.tags,
        summary=ai_result.summary,
        chapters=ai_result.chapters,
        highlights=ai_result.highlights,
        deep_thinking=ai_result.deep_questions,
        glossary=ai_result.glossary,
        rating=ai_result.rating,
        rating_detail=ai_result.rating_detail,
        flashcards=ai_result.flashcards,
        related_notes=related_notes,
    )

    # ── Import / 导入 ──
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

    # Mark processed / 标记已处理（含评分和错误记录）
    mark_processed(url, str(md_path), {
        "title": title,
        "platform": platform,
        "category": ai_result.category,
        "tags": ai_result.tags,
        "rating": ai_result.rating,
        "consecutive_failures": 0,
        "has_highlights": bool(ai_result.highlights),
        "has_glossary": bool(ai_result.glossary),
        "has_chapters": bool(ai_result.chapters),
        "has_flashcards": bool(ai_result.flashcards),
    })

    print(f"✅ 完成 → {md_path}")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse flags / 解析参数
    urls = []
    with_frames = False; no_import = False; dry_run = False; extract_only = False; out_dir = DEFAULT_OUT

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
          f"浏览器: {'有' if env.has_browser else '无'} | "
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

    # ── API 安全防护检查 ──────────────────────────────────────────────────────
    if not _check_api_safety(len(urls)):
        sys.exit(1)

    # Process all URLs / 批量处理
    success = 0; fail = 0
    for url in urls:
        if process_single(url, env, out_dir, with_frames, no_import, extract_only):
            success += 1
        else:
            fail += 1

    # 输出本次 API 调用统计（含 Token 和费用）
    log = _load_api_call_log()
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = log.get("daily_count", {}).get(today, 0)
    total_count = sum(log.get("daily_count", {}).values())
    total_tokens = log.get("total_tokens", 0)
    total_cost = log.get("total_cost", 0.0)
    print(f"\n  📊 API 调用统计:")
    print(f"    今日: {today_count} 次 / 累计: {total_count} 次")
    if total_tokens:
        print(f"    Token: {total_tokens:,} (≈ ${total_cost:.4f})")
    if fail > 0:
        print(f"    ⚠ 失败: {fail} 个 URL")
    print(f"  📋 详情见: {API_CALL_LOG}")

    print(f"\n{'='*60}")
    print(f"📊 处理完成: {success} 成功, {fail} 失败 (共 {len(urls)} 个)")
    print(f"📁 输出目录: {out_dir}")


if __name__ == "__main__":
    main()
