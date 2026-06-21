#!/usr/bin/env python3
"""
闪卡生成脚本 — 调用 DeepSeek API 基于转录内容生成 Q&A 闪卡。

用法:
    python flashcards.py --transcript "转录文本..."
    python flashcards.py --transcript-file "path/to/transcript.txt"

输出 (stdout): [{"q": "问题1", "a": "答案1"}, ...]

也可作为模块导入:
    from flashcards import generate_flashcards
    cards = generate_flashcards("转录文本...")
"""

import sys, os, json, re, argparse
from pathlib import Path
from typing import List, Dict, Optional

# ── Config / 配置 ──────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).resolve().parents[4] / "ZCodeProject" / "tools" / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k not in os.environ:
                os.environ[_k] = _v

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

FLASHCARD_PROMPT = """Based on the following transcript, generate 5 question-answer flashcards.
Each should test understanding of a key concept, not trivia.
Keep questions concise and answers informative but brief.

Transcript:
{transcript}

Reply ONLY in JSON array format, no extra text: [{{"q": "question", "a": "answer"}}, ...]"""

# 快速路径阈值：转录短于此值跳过闪卡生成
FAST_PATH_THRESHOLD = 500  # 字符数


def should_generate(transcript: str) -> bool:
    """判断是否应生成闪卡（短内容跳过）。"""
    return len(transcript.strip()) >= FAST_PATH_THRESHOLD


def generate_flashcards(transcript: str, count: int = 5) -> List[Dict[str, str]]:
    """调用 DeepSeek API 生成 Q&A 闪卡。

    Args:
        transcript: 转录文本（建议取前 3000 字）
        count: 生成数量，默认 5

    Returns:
        [{"q": str, "a": str}, ...]
        API 失败时返回空列表
    """
    import requests

    if not DEEPSEEK_KEY:
        print("⚠ DEEPSEEK_API_KEY 未配置，跳过闪卡生成", file=sys.stderr)
        return []

    if not should_generate(transcript):
        print(f"ℹ 内容过短 ({len(transcript)}字 < {FAST_PATH_THRESHOLD})，跳过闪卡生成", file=sys.stderr)
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

        # 提取 JSON 数组
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            cards = json.loads(match.group())
            if isinstance(cards, list):
                return cards[:count]

        print(f"⚠ 闪卡生成返回非 JSON: {text[:100]}", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"⚠ 闪卡生成请求失败: {e}", file=sys.stderr)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"⚠ 闪卡生成解析失败: {e}", file=sys.stderr)

    return []


def main():
    parser = argparse.ArgumentParser(description="闪卡生成")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--transcript", help="转录文本")
    group.add_argument("--transcript-file", help="转录文本文件路径")
    parser.add_argument("--count", type=int, default=5, help="生成数量 (默认5)")
    args = parser.parse_args()

    transcript = args.transcript
    if args.transcript_file:
        transcript = Path(args.transcript_file).read_text(encoding="utf-8")

    cards = generate_flashcards(transcript, args.count)
    print(json.dumps(cards, ensure_ascii=False))


if __name__ == "__main__":
    main()
