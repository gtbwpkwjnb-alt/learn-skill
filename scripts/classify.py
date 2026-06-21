#!/usr/bin/env python3
"""
AI 分类脚本 — 调用 DeepSeek API 对内容进行主题分类和标签生成。

用法:
    python classify.py --title "标题" --summary "摘要前2000字"
    python classify.py --title "标题" --summary-file "path/to/summary.txt"

输出 (stdout): {"category": "主题分类", "tags": ["标签1", "标签2", "标签3"]}

也可作为模块导入:
    from classify import classify_content
    result = classify_content("标题", "摘要...")
"""

import sys, os, json, re, argparse
from pathlib import Path
from typing import Dict, List, Optional

# ── Config / 配置 ──────────────────────────────────────────────────────────
# 从 tools/.env 加载（与 learn.py 共用配置）
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

CLASSIFY_PROMPT = """Analyze this content and provide:
1. A topic category (10 words max, in Chinese preferred)
2. 3-5 relevant tags (comma separated, in Chinese or English)

Title: {title}
Summary: {summary}

Reply ONLY in JSON format, no extra text: {{"category": "...", "tags": ["...", "..."]}}"""


def classify_content(title: str, summary: str) -> Dict[str, any]:
    """调用 DeepSeek API 进行内容分类。

    Args:
        title: 内容标题
        summary: 内容摘要（建议取前 2000 字）

    Returns:
        {"category": str, "tags": [str, ...]}
        API 失败时返回 {"category": "未分类", "tags": []}
    """
    import requests

    if not DEEPSEEK_KEY:
        print("⚠ DEEPSEEK_API_KEY 未配置，使用默认分类", file=sys.stderr)
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

        # 提取第一个 JSON 对象
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return {
                "category": result.get("category", "未分类"),
                "tags": result.get("tags", []),
            }

        print(f"⚠ AI 分类返回非 JSON: {content[:100]}", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"⚠ AI 分类请求失败: {e}", file=sys.stderr)
    except (KeyError, IndexError) as e:
        print(f"⚠ AI 分类解析失败: {e}", file=sys.stderr)

    return {"category": "未分类", "tags": []}


def main():
    parser = argparse.ArgumentParser(description="AI 内容分类")
    parser.add_argument("--title", required=True, help="内容标题")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--summary", help="摘要文本")
    group.add_argument("--summary-file", help="摘要文本文件路径")
    args = parser.parse_args()

    summary = args.summary
    if args.summary_file:
        summary = Path(args.summary_file).read_text(encoding="utf-8")

    result = classify_content(args.title, summary)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
