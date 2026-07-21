#!/usr/bin/env python3
"""
Markdown 组装脚本 v3.5 — 将所有组件拼接为增强版学习笔记 Markdown。

新模板含：元数据 → AI分类 → AI总结 → 内容亮点 → 深度思考 → 术语解释
         → 内容评分 → 知识图谱 → 章节总结 → 闪卡

用法:
    python assemble_md.py \
      --title "标题" --url "原始链接" --platform "bilibili" \
      --author "作者" --duration "12:34" \
      --transcript-file "path/to/transcript.txt" \
      --category "AI技术" --tags "AI,机器学习,教程" \
      --flashcards-file "path/to/flashcards.json" \
      --summary "AI生成的3-5句摘要" \
      --highlights "亮点JSON" \
      --deep-thinking "深度思考JSON" \
      --glossary "术语JSON" \
      --rating "4.5" \
      --chapters "章节JSON" \
      --related-notes "相关笔记JSON" \
      --out "path/to/output.md"

也可作为模块导入:
    from assemble_md import assemble
    md = assemble(title="...", url="...", ...)
"""

import sys, os, json, re, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any


# ── Section Templates / 各区域模板 ────────────────────────────────────────────

MARKDOWN_TEMPLATE = """---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration}"
date: "{date}"
tags: [{tags_yaml}]
category: "{category}"
rating: {rating}
related: [{related_yaml}]
task_id: "{task_id}"
pipeline_version: "{pipeline_version}"
---

# {title}

## 📋 Metadata / 元数据
- **Platform / 平台**: {platform}
- **Author / 作者**: {author}
- **Duration / 时长**: {duration}
- **Source / 来源**: [Original Link / 原始链接]({url})
- **Extracted / 提取时间**: {extract_time}
- **Rating / 评分**: {rating_display}

{classification_section}

{summary_section}

{highlights_section}

{deep_thinking_section}

{glossary_section}

{rating_section}

{knowledge_graph_section}

{chapter_summary_section}

{transcript_section}

{flashcards_section}
"""

CLASSIFICATION_TEMPLATE = """## 🤖 AI Classification / AI 分类
- **Category / 主题**: {category}
- **Tags / 标签**: {tags_display}
"""

SUMMARY_TEMPLATE = """## 💡 AI Summary / AI 总结

{summary}
"""

HIGHLIGHTS_TEMPLATE = """## ⭐ Highlights / 内容亮点

{highlights}
"""

DEEP_THINKING_TEMPLATE = """## 🤔 Deep Thinking / 深度思考

{thinking}
"""

GLOSSARY_TEMPLATE = """## 📚 Glossary / 术语解释

{glossary}
"""

RATING_TEMPLATE = """## 🌟 Rating / 内容评分

| Dimension / 维度 | Score / 分数 |
|---|---|
{rating_rows}
"""
RATING_FOOTER = """
> AI-generated score (1-5) / AI 自动评分（1-5 星）
> Your feedback: _____ / 5 （请手动填写你的评分）
"""

KNOWLEDGE_GRAPH_TEMPLATE = """## 🧭 Knowledge Graph / 知识图谱

```mermaid
{graph}
```
"""

CHAPTER_SUMMARY_TEMPLATE = """## 🖼 Chapter Summary / 章节总结

{chapters}
"""

TRANSCRIPT_TEMPLATE = """## 📝 Transcript / 内容转录

{transcript}
"""

FLASHCARDS_TEMPLATE = """## 🃏 Flashcards / 闪卡

{cards}
"""


# ── Helper: format Mermaid graph ──────────────────────────────────────────────

def _build_mermaid_graph(related_notes: List[Dict[str, str]], current_title: str) -> str:
    """Build a Mermaid graph LR from related notes list."""
    if not related_notes:
        return ""
    lines = ["graph LR"]
    # Sanitize node IDs and labels
    import re as _re
    def _safe_id(title: str) -> str:
        tid = _re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_]', '_', title[:20])
        return tid if tid else f"node_{hash(title) % 10000}"
    def _safe_label(title: str) -> str:
        return title.replace('"', "'")[:30]

    current_id = _safe_id(current_title)
    current_label = _safe_label(current_title)
    lines.append(f'  {current_id}["{current_label}"]')

    for note in related_notes:
        nid = _safe_id(note.get("title", ""))
        nlabel = _safe_label(note.get("title", ""))
        tag = _safe_label(note.get("relation", "related"))
        lines.append(f'  {nid}["{nlabel}"]')
        lines.append(f'  {current_id} -->|{tag}| {nid}')

    return "\n".join(lines)


# ── Main assemble function ────────────────────────────────────────────────────

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
    summary: str = "",
    highlights: Optional[List[Dict[str, str]]] = None,
    deep_thinking: Optional[List[Dict[str, str]]] = None,
    glossary: Optional[List[Dict[str, str]]] = None,
    rating: str = "",
    chapters: Optional[List[Dict[str, Any]]] = None,
    related_notes: Optional[List[Dict[str, str]]] = None,
    flashcards: Optional[List[Dict[str, str]]] = None,
    flashcards_file: Optional[str] = None,
    task_id: str = "",
    pipeline_version: str = "5.2.0",
    include_transcript: bool = False,
    out: Optional[str] = None,
) -> str:
    """组装增强版学习笔记 Markdown。

    Args:
        title: 标题
        url: 原始链接
        platform: 平台标识
        transcript: 转录文本 (与 transcript_file 二选一)
        transcript_file: 转录文本文件路径
        category: AI 分类结果
        tags: 标签列表
        author: 作者
        duration: 时长
        summary: AI 总结文本
        highlights: 亮点列表 [{"time": "05:07", "text": "..."}, ...]
        deep_thinking: 深度思考列表 [{"q": "...", "a": "..."}, ...]
        glossary: 术语列表 [{"term": "...", "definition": "..."}, ...]
        rating: 评分 (如 "4.5")
        chapters: 章节总结列表 [{"time": "00:00", "title": "...", "text": "...", "screenshot": "..."}, ...]
        related_notes: 相关笔记列表 [{"title": "...", "relation": "tag_name"}, ...]
        flashcards: 闪卡列表 (与 flashcards_file 二选一)
        flashcards_file: 闪卡 JSON 文件路径
        include_transcript: 是否在最终 Markdown 中嵌入全文转录（默认不嵌入）
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

    # 相关笔记
    related_list = related_notes or []
    related_yaml = ", ".join(f'"{r.get("title", "")}"' for r in related_list)

    # ── 分类 section ──
    classification_section = CLASSIFICATION_TEMPLATE.format(
        category=category,
        tags_display=tags_display,
    )

    # ── AI summary section ──
    summary_section = SUMMARY_TEMPLATE.format(summary=summary) if summary else ""

    # ── Highlights section ──
    highlights_section = ""
    if highlights:
        hl_lines = []
        for h in highlights:
            time_str = h.get("time", "")
            text = h.get("text", "")
            if time_str:
                hl_lines.append(f"- **[{time_str}]** {text}")
            else:
                hl_lines.append(f"- {text}")
            if h.get("evidence"):
                hl_lines.append(f"  > 证据：{h['evidence']}")
        highlights_section = HIGHLIGHTS_TEMPLATE.format(
            highlights="\n".join(hl_lines)
        )

    # ── Deep Thinking section ──
    deep_thinking_section = ""
    if deep_thinking:
        dt_lines = []
        for i, dt in enumerate(deep_thinking, 1):
            q = dt.get("q", "?")
            a = dt.get("a", "?")
            dt_lines.append(f"**Q{i}:** {q}\n\n**A{i}:** {a}\n")
            if dt.get("evidence"):
                dt_lines.append(f"> 证据：{dt['evidence']}\n")
        deep_thinking_section = DEEP_THINKING_TEMPLATE.format(
            thinking="\n".join(dt_lines)
        )

    # ── Glossary section ──
    glossary_section = ""
    if glossary:
        gl_lines = []
        for g in glossary:
            term = g.get("term", g.get("t", ""))
            definition = g.get("definition", g.get("d", ""))
            gl_lines.append(f"- **{term}**: {definition}")
            if g.get("evidence"):
                gl_lines.append(f"  > 证据：{g['evidence']}")
        glossary_section = GLOSSARY_TEMPLATE.format(
            glossary="\n".join(gl_lines)
        )

    # ── Rating section ──
    rating_section = ""
    if rating:
        try:
            rating_float = float(rating)
            rating_display = f"{'⭐' * int(round(rating_float))} ({rating_float}/5)"
        except (ValueError, TypeError):
            rating_display = f"{rating}/5"
        rating_rows = "\n".join(
            f"  | {dim} | {score} |"
            for dim, score in [
                ("Information Density / 信息密度", rating),
                ("Practicality / 实用价值", rating),
                ("Clarity / 清晰度", rating),
            ]
        )
        rating_section = RATING_TEMPLATE.format(rating_rows=rating_rows) + RATING_FOOTER
    else:
        rating_display = "_(待评分 / pending)_"

    # ── Knowledge Graph section ──
    knowledge_graph_section = ""
    if related_list:
        graph = _build_mermaid_graph(related_list, title)
        if graph:
            knowledge_graph_section = KNOWLEDGE_GRAPH_TEMPLATE.format(graph=graph)

    # ── Chapter Summary section ──
    chapter_summary_section = ""
    if chapters:
        ch_lines = []
        for ch in chapters:
            ch_time = ch.get("time", "")
            ch_title = ch.get("title", "")
            ch_text = ch.get("text", ch.get("summary", ""))
            ch_screenshot = ch.get("screenshot", "")
            ch_lines.append(f"### [{ch_time}] {ch_title}\n")
            if ch_screenshot:
                ch_lines.append(f"![{ch_title}]({ch_screenshot})\n")
            if ch_text:
                ch_lines.append(f"{ch_text}\n")
            if ch.get("evidence"):
                ch_lines.append(f"> 证据：{ch['evidence']}\n")
        chapter_summary_section = CHAPTER_SUMMARY_TEMPLATE.format(
            chapters="\n".join(ch_lines)
        )

    # ── Transcript section ──
    transcript_section = ""
    if include_transcript:
        transcript_section = TRANSCRIPT_TEMPLATE.format(
            transcript=transcript if transcript else "_(待转录 / pending transcription)_"
        )

    # ── Flashcards section ──
    flashcards_section = ""
    if fc_list:
        cards_md = ""
        for i, fc in enumerate(fc_list, 1):
            q = fc.get("q", "?")
            a = fc.get("a", "?")
            cards_md += f"**Q{i}**: {q}\n\n**A{i}**: {a}\n\n"
            if fc.get("evidence"):
                cards_md += f"> 证据：{fc['evidence']}\n\n"
        flashcards_section = FLASHCARDS_TEMPLATE.format(cards=cards_md)

    # ── 组装 ──
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
        rating=rating if rating else '""',
        rating_display=rating_display,
        related_yaml=related_yaml,
        task_id=task_id,
        pipeline_version=pipeline_version,
        classification_section=classification_section,
        summary_section=summary_section,
        highlights_section=highlights_section,
        deep_thinking_section=deep_thinking_section,
        glossary_section=glossary_section,
        rating_section=rating_section,
        knowledge_graph_section=knowledge_graph_section,
        chapter_summary_section=chapter_summary_section,
        transcript_section=transcript_section,
        flashcards_section=flashcards_section,
    )

    # 写入文件
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")

    return md


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_json_arg(raw: str, label: str) -> Any:
    """Parse a JSON string argument, with error handling."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠ {label} JSON 解析失败: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="组装增强版学习笔记 Markdown v3.5")
    parser.add_argument("--title", required=True, help="标题")
    parser.add_argument("--url", required=True, help="原始链接")
    parser.add_argument("--platform", required=True, help="平台")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--duration", default="", help="时长 (HH:MM:SS)")
    parser.add_argument("--category", default="未分类", help="AI 分类")
    parser.add_argument("--tags", default="", help="标签 (逗号分隔)")
    parser.add_argument("--summary", default="", help="AI 总结文本")
    parser.add_argument("--rating", default="", help="AI 评分 (如 4.5)")

    # JSON complex args / 复杂参数以 JSON 字符串传入
    parser.add_argument("--highlights", default="", help="亮点 JSON 数组")
    parser.add_argument("--deep-thinking", default="", help="深度思考 JSON 数组")
    parser.add_argument("--glossary", default="", help="术语 JSON 数组")
    parser.add_argument("--chapters", default="", help="章节总结 JSON 数组")
    parser.add_argument("--related-notes", default="", help="相关笔记 JSON 数组")

    transcript_group = parser.add_mutually_exclusive_group()
    transcript_group.add_argument("--transcript", default="", help="转录文本")
    transcript_group.add_argument("--transcript-file", default="", help="转录文件路径")
    parser.add_argument(
        "--include-transcript", action="store_true",
        help="在最终 Markdown 中嵌入全文转录（默认仅保留在任务工件）",
    )

    flashcards_group = parser.add_mutually_exclusive_group()
    flashcards_group.add_argument("--flashcards", default="", help="闪卡 JSON 字符串")
    flashcards_group.add_argument("--flashcards-file", default="", help="闪卡 JSON 文件路径")

    parser.add_argument("--out", required=True, help="输出文件路径")
    args = parser.parse_args()

    # 解析标签
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    # 解析复杂 JSON 参数
    highlights = _parse_json_arg(args.highlights, "亮点") if args.highlights else None
    deep_thinking = _parse_json_arg(args.deep_thinking, "深度思考") if args.deep_thinking else None
    glossary = _parse_json_arg(args.glossary, "术语") if args.glossary else None
    chapters = _parse_json_arg(args.chapters, "章节总结") if args.chapters else None
    related_notes = _parse_json_arg(args.related_notes, "相关笔记") if args.related_notes else None

    # 解析闪卡
    flashcards = None
    if args.flashcards:
        flashcards = _parse_json_arg(args.flashcards, "闪卡")

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
        summary=args.summary,
        highlights=highlights,
        deep_thinking=deep_thinking,
        glossary=glossary,
        rating=args.rating,
        chapters=chapters,
        related_notes=related_notes,
        flashcards=flashcards,
        flashcards_file=args.flashcards_file or None,
        include_transcript=args.include_transcript,
        out=args.out,
    )

    print(f"✅ Markdown 已组装: {args.out}", file=sys.stderr)
    print(args.out)


if __name__ == "__main__":
    main()
