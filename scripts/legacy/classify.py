#!/usr/bin/env python3
"""
AI classification script — calls LLM API to classify content by topic and tags.

Usage:
    python classify.py --title "Title" --summary "First 2000 chars..."
    python classify.py --title "Title" --summary-file "path/to/summary.txt"

Output (stdout): {"category": "Topic", "tags": ["tag1", "tag2", "tag3"]}

Importable:
    from classify import classify_content
    result = classify_content("Title", "Summary...")

Note: When used as an AI skill, classification is done by the AI model itself
(inline, zero config). This script exists for standalone CLI usage.
"""

import sys, os, json, re, argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ── Config loading ─────────────────────────────────────────────────────────
def _load_dotenv() -> None:
    """Load .env from skill directory, cwd, or env vars (universal)."""
    env_files = [
        Path(__file__).resolve().parent.parent / ".env",   # <skill_dir>/.env
        Path.cwd() / ".env",                                # cwd/.env
    ]
    for env_file in env_files:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

_load_dotenv()

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ── Safety guard / 安全防护 ─────────────────────────────────────────────────
MAX_API_CALLS_PER_DAY = 200       # 每日最大 API 调用次数
API_CALL_LOG = (Path(__file__).resolve().parent.parent.parent / "learn-output" / ".api_call_legacy.json")


def _check_legacy_api_safety() -> bool:
    """Check daily API call budget / 检查每日 API 调用额度"""
    if "LEARN_SKIP_SAFETY" in os.environ:
        return True
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = API_CALL_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = {"daily": {}}
    if log_path.exists():
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.setdefault("daily", {})
    used = log["daily"].get(today, 0)
    if used >= MAX_API_CALLS_PER_DAY:
        print(f"⚠ 安全拦截：今日 API 调用已达上限 ({MAX_API_CALLS_PER_DAY})，设置 LEARN_SKIP_SAFETY=1 绕过",
              file=sys.stderr)
        return False
    log["daily"][today] = used + 1
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


CLASSIFY_PROMPT = """Analyze this content and provide:
1. A topic category (10 words max)
2. 3-5 relevant tags

Title: {title}
Summary: {summary}

Reply ONLY in JSON format, no extra text: {{"category": "...", "tags": ["...", "..."]}}"""


def classify_content(title: str, summary: str) -> Dict[str, any]:
    """Call LLM API for content classification.

    Args:
        title: Content title
        summary: Content summary (first ~2000 chars recommended)

    Returns:
        {"category": str, "tags": [str, ...]}
        Falls back to {"category": "未分类", "tags": []} on failure.
    """
    import requests

    if not DEEPSEEK_KEY:
        print("⚠ DEEPSEEK_API_KEY not configured — using default classification", file=sys.stderr)
        return {"category": "未分类", "tags": []}

    if not _check_legacy_api_safety():
        return {"category": "未分类", "tags": []}

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
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Extract first JSON object
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return {
                "category": result.get("category", "未分类"),
                "tags": result.get("tags", []),
            }

        print(f"⚠ Classification returned non-JSON: {content[:100]}", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"⚠ Classification request failed: {e}", file=sys.stderr)
    except (KeyError, IndexError) as e:
        print(f"⚠ Classification parse failed: {e}", file=sys.stderr)

    return {"category": "未分类", "tags": []}


def main():
    parser = argparse.ArgumentParser(description="AI content classification")
    parser.add_argument("--title", required=True, help="Content title")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--summary", help="Summary text")
    group.add_argument("--summary-file", help="Path to summary text file")
    args = parser.parse_args()

    summary = args.summary
    if args.summary_file:
        summary = Path(args.summary_file).read_text(encoding="utf-8")

    result = classify_content(args.title, summary)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
