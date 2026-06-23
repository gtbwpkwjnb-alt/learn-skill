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
      --summary "AI生成的3-5句摘要" \
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

COVER_IMAGE_TEMPLATE = """![]({url})
"""

SUMMARY_TEMPLATE = """## 💡 AI Summary / AI 总结

{summary}
"""

MARKDOWN_TEMPLATE = """---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration}"
date: "{date}"
tags: [{tags_yaml}]
category: "{category}"
rating: {rating_yaml}
related: [{related_yaml}]{cover_frontmatter}
---

{cover_image_section}

# {title}

## 📋 Metadata / 元数据
- **Platform / 平台**: {platform}
- **Author / 作者**: {author}
- **Duration / 时长**: {duration}
- **Source / 来源**: [Original Link / 原始链接]({url})
- **Extracted / 提取时间**: {extract_time}

{summary_section}

{highlights_section}

{deep_thinking_section}

{glossary_section}

{rating_section}

{classification_section}

{transcript_section}

{chapter_summary_section}

{knowledge_graph_section}

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

HIGHLIGHTS_TEMPLATE = """## ⭐ Highlights / 内容亮点

{items}
"""

DEEP_THINKING_TEMPLATE = """## 🤔 Deep Thinking / 深度思考

{items}
"""

GLOSSARY_TEMPLATE = """## 📚 Glossary / 术语解释

{items}
"""

RATING_TEMPLATE = """## 🌟 Rating / 内容评分

| Dimension / 维度 | Score / 分数 |
|---|---|
| 信息密度 | {info_density} |
| 实用价值 | {practicality} |
| 清晰度 | {clarity} |

> AI 自动评分（1-5 星）/ 你的评分: _____ / 5
"""

KNOWLEDGE_GRAPH_TEMPLATE = """## 🧭 Knowledge Graph / 知识图谱

```mermaid
graph LR{links}
```
"""

CHAPTER_SUMMARY_TEMPLATE = """## 🖼 Chapter Summary / 章节总结

{items}
"""


def _parse_json_arg(raw: str):
    """Parse a JSON string argument, return parsed value or None."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_highlights(data) -> str:
    if not data:
        return ""
    items = []
    for h in data if isinstance(data, list) else [data]:
        t = h.get("time", "")
        desc = h.get("description", str(h))
        items.append(f"- **[{t}]** {desc}" if t else f"- {desc}")
    return HIGHLIGHTS_TEMPLATE.format(items="\n".join(items))


def _build_deep_thinking(data) -> str:
    if not data:
        return ""
    items = []
    for i, d in enumerate(data if isinstance(data, list) else [data], 1):
        q = d.get("q", "")
        a = d.get("a", "")
        items.append(f"**Q{i}:** {q}\n\n**A{i}:** {a}\n")
    return DEEP_THINKING_TEMPLATE.format(items="\n\n".join(items))


def _build_glossary(data) -> str:
    if not data:
        return ""
    items = []
    for g in data if isinstance(data, list) else [data]:
        term = g.get("term", "")
        definition = g.get("definition", str(g))
        items.append(f"- **{term}**: {definition}" if term else f"- {definition}")
    return GLOSSARY_TEMPLATE.format(items="\n".join(items))


def _build_rating(data) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        data = _parse_json_arg(data)
    if not isinstance(data, dict):
        return ""
    return RATING_TEMPLATE.format(
        info_density=data.get("info_density", data.get("信息密度", "—")),
        practicality=data.get("practicality", data.get("实用价值", "—")),
        clarity=data.get("clarity", data.get("清晰度", "—")),
    )


def _build_knowledge_graph(data, title: str = "") -> str:
    if not data:
        return ""
    links = []
    for r in data if isinstance(data, list) else [data]:
        note_title = r.get("title", "相关笔记")
        tag = r.get("tag", "related")
        links.append(f'\n  A["{title or "当前笔记" }"] -->|{tag}| B["{note_title}"]')
    return KNOWLEDGE_GRAPH_TEMPLATE.format(links="".join(links))


def _build_chapters(data) -> str:
    if not data:
        return ""
    items = []
    for c in data if isinstance(data, list) else [data]:
        t = c.get("time", "")
        ct = c.get("title", "")
        ss = c.get("screenshot", "")
        summary = c.get("summary", "")
        header = f"### [{t}] {ct}" if t and ct else f"### {ct or t}"
        items.append(header)
        if ss:
            items.append(f"![截图]({ss})")
        if summary:
            items.append(summary)
        items.append("")
    return CHAPTER_SUMMARY_TEMPLATE.format(items="\n".join(items))


def assemble(
    title: str,
    url: str,
    platform: str,
    cover_image: str = "",
    transcript: str = "",
    transcript_file: Optional[str] = None,
    category: str = "未分类",
    tags: Optional[List[str]] = None,
    author: str = "",
    duration: str = "",
    summary: str = "",
    highlights: Optional[list] = None,
    deep_thinking: Optional[list] = None,
    glossary: Optional[list] = None,
    rating: Optional[dict] = None,
    chapters: Optional[list] = None,
    related_notes: Optional[list] = None,
    flashcards: Optional[List[Dict[str, str]]] = None,
    flashcards_file: Optional[str] = None,
    out: Optional[str] = None,
) -> str:
    """组装标准化学习笔记 Markdown（v3.5 增强版）。

    Args:
        title: 标题
        url: 原始链接
        platform: 平台标识 (douyin/bilibili/youtube/...)
        cover_image: 封面图 URL
        transcript: 转录文本 (与 transcript_file 二选一)
        transcript_file: 转录文本文件路径
        category: AI 分类结果
        tags: 标签列表
        author: 作者
        duration: 时长
        summary: AI 总结文本
        highlights: 亮点列表 [{"time": "MM:SS", "description": "..."}, ...]
        deep_thinking: 深度思考 Q&A 列表 [{"q": "...", "a": "..."}, ...]
        glossary: 术语列表 [{"term": "...", "definition": "..."}, ...]
        rating: 评分字典 {"info_density": 4.0, "practicality": 4.5, "clarity": 4.0}
        chapters: 章节列表 [{"time": "MM:SS", "title": "...", "screenshot": "...", "summary": "一段完整解释..."}, ...]
        related_notes: 相关笔记列表 [{"title": "...", "tag": "...", "url": "..."}, ...]
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

    # Rating YAML（front matter）
    if rating and isinstance(rating, dict):
        avg = (float(rating.get("info_density", 0)) + float(rating.get("practicality", 0)) + float(rating.get("clarity", 0))) / 3
        rating_yaml = f"{avg:.1f}"
    else:
        rating_yaml = ""

    # Related notes YAML（front matter）
    rl = related_notes or []
    related_yaml = ", ".join(f'{{"title": "{r.get("title", "")}", "tag": "{r.get("tag", "")}"}}' for r in rl)

    # Cover image front matter + section
    cover_frontmatter = f'\ncover_image: "{cover_image}"' if cover_image else ""
    cover_image_section = COVER_IMAGE_TEMPLATE.format(url=cover_image) if cover_image else ""

    # 分类 section
    classification_section = CLASSIFICATION_TEMPLATE.format(
        category=category,
        tags_display=tags_display,
    )

    # AI summary section
    summary_section = SUMMARY_TEMPLATE.format(summary=summary) if summary else ""

    # Highlights section
    highlights_section = _build_highlights(highlights)

    # Deep Thinking section
    deep_thinking_section = _build_deep_thinking(deep_thinking)

    # Glossary section
    glossary_section = _build_glossary(glossary)

    # Rating section
    rating_section = _build_rating(rating)

    # 转录 section
    transcript_section = TRANSCRIPT_TEMPLATE.format(
        transcript=transcript if transcript else "_(待转录 / pending transcription)_"
    )

    # Chapter Summary section
    chapter_summary_section = _build_chapters(chapters)

    # Knowledge Graph section
    knowledge_graph_section = _build_knowledge_graph(related_notes, title=title)

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
        rating_yaml=rating_yaml,
        related_yaml=related_yaml,
        cover_frontmatter=cover_frontmatter,
        cover_image_section=cover_image_section,
        classification_section=classification_section,
        summary_section=summary_section,
        highlights_section=highlights_section,
        deep_thinking_section=deep_thinking_section,
        glossary_section=glossary_section,
        rating_section=rating_section,
        transcript_section=transcript_section,
        chapter_summary_section=chapter_summary_section,
        knowledge_graph_section=knowledge_graph_section,
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
    parser.add_argument("--summary", default="", help="AI 总结文本")
    parser.add_argument("--cover-image", default="", help="封面图 URL")
    parser.add_argument("--highlights", default="", help="亮点 JSON 字符串 [{\"time\":\"MM:SS\",\"description\":\"...\"}]")
    parser.add_argument("--deep-thinking", default="", help="深度思考 JSON 字符串 [{\"q\":\"...\",\"a\":\"...\"}]")
    parser.add_argument("--glossary", default="", help="术语 JSON 字符串 [{\"term\":\"...\",\"definition\":\"...\"}]")
    parser.add_argument("--rating", default="", help="评分 JSON 字符串 {\"info_density\":4.0,\"practicality\":4.5,\"clarity\":4.0}")
    parser.add_argument("--chapters", default="", help="章节 JSON 字符串 [{\"time\":\"MM:SS\",\"title\":\"...\",\"screenshot\":\"...\",\"summary\":\"一段完整解释...\"}]")
    parser.add_argument("--related-notes", default="", help="相关笔记 JSON 字符串 [{\"title\":\"...\",\"tag\":\"...\",\"url\":\"...\"}]")

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
    flashcards = _parse_json_arg(args.flashcards)

    md = assemble(
        title=args.title,
        url=args.url,
        platform=args.platform,
        cover_image=args.cover_image,
        transcript=args.transcript or None,
        transcript_file=args.transcript_file or None,
        category=args.category,
        tags=tags,
        author=args.author,
        duration=args.duration,
        summary=args.summary,
        highlights=_parse_json_arg(args.highlights),
        deep_thinking=_parse_json_arg(args.deep_thinking),
        glossary=_parse_json_arg(args.glossary),
        rating=_parse_json_arg(args.rating),
        chapters=_parse_json_arg(args.chapters),
        related_notes=_parse_json_arg(args.related_notes),
        flashcards=flashcards,
        flashcards_file=args.flashcards_file or None,
        out=args.out,
    )

    print(f"✅ Markdown 已组装: {args.out}", file=sys.stderr)
    # 输出路径到 stdout，方便 SKILL.md 捕获
    print(args.out)


if __name__ == "__main__":
    main()
