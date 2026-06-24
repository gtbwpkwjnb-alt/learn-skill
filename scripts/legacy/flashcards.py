#!/usr/bin/env python3
"""
Flashcard generation script — calls LLM API to generate Q&A cards from transcripts.

Usage:
    python flashcards.py --transcript "Transcript text..."
    python flashcards.py --transcript-file "path/to/transcript.txt"

Output (stdout): [{"q": "Question 1", "a": "Answer 1"}, ...]

Importable:
    from flashcards import generate_flashcards, should_generate
    cards = generate_flashcards("Transcript text...")

Note: When used as an AI skill, flashcard generation is done by the AI model
itself (inline, zero config). This script exists for standalone CLI usage.
"""

import sys, os, json, re, argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


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
MAX_API_CALLS_PER_DAY = 200
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


FLASHCARD_PROMPT = """Based on the following transcript, generate 5 question-answer flashcards.
Each should test understanding of a key concept, not trivia.
Keep questions concise and answers informative but brief.

Transcript:
{transcript}

Reply ONLY in JSON array format, no extra text: [{{"q": "question", "a": "answer"}}, ...]"""

# Fast-path threshold: skip flashcards for short content
FAST_PATH_THRESHOLD = 500  # characters


def should_generate(transcript: str) -> bool:
    """Check if content is long enough for meaningful flashcards."""
    return len(transcript.strip()) >= FAST_PATH_THRESHOLD


def generate_flashcards(transcript: str, count: int = 5) -> List[Dict[str, str]]:
    """Call LLM API to generate Q&A flashcards.

    Args:
        transcript: Transcript text (first ~3000 chars recommended)
        count: Number of cards to generate (default 5)

    Returns:
        [{"q": str, "a": str}, ...]
        Returns empty list on failure or if content too short.
    """
    import requests

    if not DEEPSEEK_KEY:
        print("⚠ DEEPSEEK_API_KEY not configured — skipping flashcards", file=sys.stderr)
        return []

    if not should_generate(transcript):
        print(f"ℹ Content too short ({len(transcript)} chars < {FAST_PATH_THRESHOLD}) — skipping flashcards",
              file=sys.stderr)
        return []

    if not _check_legacy_api_safety():
        return []

    prompt = FLASHCARD_PROMPT.format(transcript=transcript[:3000])

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
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

        # Extract JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            cards = json.loads(match.group())
            if isinstance(cards, list):
                return cards[:count]

        print(f"⚠ Flashcards returned non-JSON: {text[:100]}", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"⚠ Flashcards request failed: {e}", file=sys.stderr)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"⚠ Flashcards parse failed: {e}", file=sys.stderr)

    return []


def main():
    parser = argparse.ArgumentParser(description="Flashcard generation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--transcript", help="Transcript text")
    group.add_argument("--transcript-file", help="Path to transcript text file")
    parser.add_argument("--count", type=int, default=5, help="Number of cards (default 5)")
    args = parser.parse_args()

    transcript = args.transcript
    if args.transcript_file:
        transcript = Path(args.transcript_file).read_text(encoding="utf-8")

    cards = generate_flashcards(transcript, args.count)
    print(json.dumps(cards, ensure_ascii=False))


if __name__ == "__main__":
    main()
