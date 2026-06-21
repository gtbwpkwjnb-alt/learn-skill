#!/usr/bin/env python3
"""
Markdown 组装脚本 — 将所有组件拼接为标准化的学习笔记 Markdown。

用法:
    python assemble_md.py \
      --title "标题" --url "原始链接" --platform "bilibili" \
      --author "作者" --duration "12:34" \
      --transcript-file "path/to/transcript.txt" \
      --category "AI技术" --tags "AI,机器学习,教程" \
      --flashcards-file "path/to/flashcards.json" \
      --out "path/to/output.md"

也可作为模块导入:
    from assemble_md import assemble
    md = assemble(title="...", url="...", ...)
"""

import sys, os, json, re, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

# ── Constants / 常量 ────────────────────────────────────────────────────────

MARKDOWN_TEMPLATE = """---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration}"
date: "{date}"
tags: [{tags_yaml}]
category: "{category}"
---

# {title}

## 📋 Metadata / 元数据
- **Platform / 平台**: {platform}
- **Author / 作者**: {author}
- **Duration / 时长**: {duration}
- **Source / 来源**: [Original Link / 原始链接]({url})
- **Extracted / 提取时间**: {extract_time}

{classification_section}

{transcript_section}

{flashcards_section}
"""

CLASSIFICATION_TEMPLATE = """## 🤖 AI Classification / AI 分类
- **Category / 主题**: {category}
- **Tags / 标签**: {tags_display}
"""

TRANSCRIPT_TEMPLATE = """## 📝 Transcript / 内容转录

{transcript}
"""

FLASHCARDS_TEMPLATE = """## 🃏 Flashcards / 闪卡

{cards}
"""


def assemble(
    title: str,
    url: str,
    platform: str,
    transcript: str = "",
    transcript_file: Optional[str] = None,
    category: str = "未分类",
    tags: Optional[List[str]] = None,
    author: str = "",
    duration: str = "",
    flashcards: Optional[List[Dict[str, str]]] = None,
    flashcards_file: Optional[str] = None,
    out: Optional[str] = None,
) -> str:
    """组装标准化学习笔记 Markdown。

    Args:
        title: 标题
        url: 原始链接
        platform: 平台标识 (douyin/bilibili/youtube/...)
        transcript: 转录文本 (与 transcript_file 二选一)
        transcript_file: 转录文本文件路径
        category: AI 分类结果
        tags: 标签列表
        author: 作者
        duration: 时长
        flashcards: 闪卡列表 (与 flashcards_file 二选一)
        flashcards_file: 闪卡 JSON 文件路径
        out: 输出文件路径（可选）

    Returns:
        组装后的 Markdown 字符串
    """
    now = datetime.now()

    # 处理转录
    if transcript_file:
        transcript = Path(transcript_file).read_text(encoding="utf-8")

    # 处理闪卡
    fc_list = flashcards or []
    if flashcards_file:
        try:
            fc_data = json.loads(Path(flashcards_file).read_text(encoding="utf-8"))
            if isinstance(fc_data, list):
                fc_list = fc_data
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # 标签
    tag_list = tags or []
    tags_yaml = ", ".join(f'"{t}"' for t in tag_list)
    tags_display = " ".join(f"#{t}" for t in tag_list) if tag_list else "_(无)_"

    # 分类 section
    classification_section = CLASSIFICATION_TEMPLATE.format(
        category=category,
        tags_display=tags_display,
    )

    # 转录 section
    transcript_section = TRANSCRIPT_TEMPLATE.format(
        transcript=transcript if transcript else "_(待转录 / pending transcription)_"
    )

    # 闪卡 section
    flashcards_section = ""
    if fc_list:
        cards_md = ""
        for i, fc in enumerate(fc_list, 1):
            q = fc.get("q", "?")
            a = fc.get("a", "?")
            cards_md += f"**Q{i}**: {q}\n\n**A{i}**: {a}\n\n"
        flashcards_section = FLASHCARDS_TEMPLATE.format(cards=cards_md)

    # 组装
    md = MARKDOWN_TEMPLATE.format(
        title=title,
        url=url,
        platform=platform,
        author=author,
        duration=duration,
        date=now.strftime("%Y-%m-%d"),
        extract_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        tags_yaml=tags_yaml,
        category=category,
        classification_section=classification_section,
        transcript_section=transcript_section,
        flashcards_section=flashcards_section,
    )

    # 写入文件
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")

    return md


def main():
    parser = argparse.ArgumentParser(description="组装学习笔记 Markdown")
    parser.add_argument("--title", required=True, help="标题")
    parser.add_argument("--url", required=True, help="原始链接")
    parser.add_argument("--platform", required=True, help="平台")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--duration", default="", help="时长 (HH:MM:SS)")
    parser.add_argument("--category", default="未分类", help="AI 分类")
    parser.add_argument("--tags", default="", help="标签 (逗号分隔)")

    transcript_group = parser.add_mutually_exclusive_group()
    transcript_group.add_argument("--transcript", default="", help="转录文本")
    transcript_group.add_argument("--transcript-file", default="", help="转录文件路径")

    flashcards_group = parser.add_mutually_exclusive_group()
    flashcards_group.add_argument("--flashcards", default="", help="闪卡 JSON 字符串")
    flashcards_group.add_argument("--flashcards-file", default="", help="闪卡 JSON 文件路径")

    parser.add_argument("--out", required=True, help="输出文件路径")
    args = parser.parse_args()

    # 解析标签
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    # 解析闪卡
    flashcards = None
    if args.flashcards:
        try:
            flashcards = json.loads(args.flashcards)
        except json.JSONDecodeError:
            print(f"⚠ 闪卡 JSON 解析失败，已忽略", file=sys.stderr)

    md = assemble(
        title=args.title,
        url=args.url,
        platform=args.platform,
        transcript=args.transcript or None,
        transcript_file=args.transcript_file or None,
        category=args.category,
        tags=tags,
        author=args.author,
        duration=args.duration,
        flashcards=flashcards,
        flashcards_file=args.flashcards_file or None,
        out=args.out,
    )

    print(f"✅ Markdown 已组装: {args.out}", file=sys.stderr)
    # 输出路径到 stdout，方便 SKILL.md 捕获
    print(args.out)


if __name__ == "__main__":
    main()
