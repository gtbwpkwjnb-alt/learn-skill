#!/usr/bin/env python3
"""
通用网页内容提取器 — 用于微信/小红书/通用文章。

用法:
    python scripts/extract_webpage.py <url> [--out PATH]

输出 (learn-compatible):
    <out>/<slug>/summary.md

依赖（均可选，缺失时降级）:
    requests, readability-lxml, markdownify, beautifulsoup4
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _install_hint(pkg: str) -> str:
    return f"pip install {pkg}"


def extract(url: str, out_dir: Path) -> Path:
    """Fetch and extract webpage content. Returns path to summary.md."""
    out_dir = Path(out_dir)
    slug = hashlib.md5(url.encode()).hexdigest()[:10]
    summary_path = out_dir / slug / "summary.md"

    if summary_path.exists():
        print(f"[skip] Already extracted: {summary_path}")
        return summary_path

    # ── 尝试 readability + markdownify ──────────────────────────────────────
    title, html, text = _fetch_readability(url)

    # ── 降级：纯 requests + 正则 ────────────────────────────────────────────
    if not text:
        text = _fetch_fallback(url)

    # ── 写入 summary.md ────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 📋 Metadata / 元数据")
    lines.append(f"- **Platform / 平台**: webpage")
    lines.append(f"- **Source / 来源**: [{url}]({url})")
    lines.append(f"- **Extracted / 提取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Method / 提取方式**: {'readability+markdownify' if title != url else 'fallback'}")
    lines.append("")
    lines.append("## 📝 Transcript / 内容转录")
    lines.append(text if text else "_(提取失败 / extraction failed)_")
    lines.append("")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def _fetch_readability(url: str) -> tuple[str, str, str]:
    """Try readability-lxml + markdownify pipeline."""
    try:
        import requests
        from readability import Document
        import markdownify
    except ImportError:
        return url, "", ""

    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36"),
        })
        resp.raise_for_status()
        html = resp.text
        doc = Document(html)
        title = doc.title() or url
        summary_html = doc.summary()
        text = markdownify.markdownify(summary_html, heading_style="ATX")
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return title, html, text
    except Exception as e:
        print(f"[warn] readability extraction failed: {e}", file=sys.stderr)
        return url, "", ""


def _fetch_fallback(url: str) -> str:
    """Fallback: plain requests + basic text extraction."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36"),
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:20000]  # 截断过长内容
    except Exception as e:
        print(f"[warn] fallback extraction failed: {e}", file=sys.stderr)
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract webpage content")
    parser.add_argument("url", help="Webpage URL")
    parser.add_argument("--out", type=Path, default=Path("learn-output"), help="Output directory")
    args = parser.parse_args()

    try:
        path = extract(args.url, args.out)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Done: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
