#!/usr/bin/env python3
"""
Knowledge Base Search — full-text and tag-based search across all learn-output entries.

Usage:
    python scripts/search_kb.py "search term"           # full-text search
    python scripts/search_kb.py --tag "深度学习"         # tag filter
    python scripts/search_kb.py "transformer" --tag "AI" # combined

Output (stdout): JSON array of matching entries with title, path, tags, date, snippet.

Index file: learn-output/index.json (auto-generated on first search)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _learn_output_dir() -> Path:
    override = os.environ.get("LEARN_OUTPUT", "")
    if override:
        return Path(override)
    return Path.cwd() / "learn-output"


INDEX_FILE = "index.json"


def build_index(base_dir: Path) -> List[Dict[str, Any]]:
    """Scan learn-output for all final.md files and build/refresh index."""
    entries: List[Dict[str, Any]] = []
    for final_md in sorted(base_dir.rglob("final.md")):
        try:
            content = final_md.read_text(encoding="utf-8")
        except Exception:
            continue

        # Parse YAML frontmatter (minimal, no dep)
        meta = _parse_frontmatter(content)
        if not meta.get("title"):
            continue

        # Extract a snippet from the summary or first content section
        snippet = _extract_snippet(content)
        tags_raw = meta.get("tags", "")
        if isinstance(tags_raw, str):
            tags = [t.strip().strip('"') for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        entries.append({
            "slug": final_md.parent.name,
            "title": meta.get("title", ""),
            "path": str(final_md),
            "tags": tags,
            "category": meta.get("category", ""),
            "date": meta.get("date", ""),
            "summary": snippet[:200],
            "rating": meta.get("rating", ""),
        })

    # Write index
    index_path = base_dir / INDEX_FILE
    index_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def _parse_frontmatter(content: str) -> Dict[str, str]:
    """Minimal frontmatter parser (no PyYAML dependency)."""
    meta: Dict[str, str] = {}
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return meta
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta


def _extract_snippet(content: str) -> str:
    """Extract first meaningful text block after frontmatter."""
    # Skip frontmatter
    body = re.sub(r"^---.*?---\s*", "", content, count=1, flags=re.DOTALL)
    # Remove headers
    body = re.sub(r"^#+\s+.*$", "", body, flags=re.MULTILINE)
    # Remove image references
    body = re.sub(r"!\[.*?\]\(.*?\)", "", body)
    body = re.sub(r"\[.*?\]\(.*?\)", "", body)
    # Clean up
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body[:300] if body else ""


def search(
    query: str = "",
    tag: str = "",
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Search entries. Returns matching entries sorted by date (newest first)."""
    base = base_dir or _learn_output_dir()
    if not base.is_dir():
        return []

    # Build or load index
    index_path = base / INDEX_FILE
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            entries = build_index(base)
    else:
        entries = build_index(base)

    results: List[Dict[str, Any]] = []
    q_lower = query.lower().strip() if query else ""
    tag_lower = tag.lower().strip() if tag else ""

    for e in entries:
        score = 0
        # Tag match
        if tag_lower:
            entry_tags = [t.lower() for t in e.get("tags", [])]
            if tag_lower in entry_tags:
                score += 10
            else:
                continue  # tag filter: must match

        # Full-text search
        if q_lower:
            title = e.get("title", "").lower()
            summary = e.get("summary", "").lower()
            if q_lower in title:
                score += 5
            if q_lower in summary:
                score += 3
            if q_lower not in title and q_lower not in summary:
                continue  # no text match

        results.append(e)

    # Sort: score desc, then date desc
    results.sort(key=lambda x: (-(x.get("score", 0) if query else 0), x.get("date", ""), x.get("title", "")), reverse=False)
    return results[:20]  # cap results


def main() -> int:
    parser = argparse.ArgumentParser(description="Search learn-output knowledge base")
    parser.add_argument("query", nargs="?", default="", help="Full-text search term")
    parser.add_argument("--tag", default="", help="Filter by tag")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild index")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    base = _learn_output_dir()
    if not base.is_dir():
        print("No learn-output directory found.", file=sys.stderr)
        return 1

    if args.rebuild:
        build_index(base)

    if not args.query and not args.tag:
        # List all entries
        index_path = base / INDEX_FILE
        if index_path.exists():
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            entries = build_index(base)
    else:
        entries = search(query=args.query, tag=args.tag, base_dir=base)

    if not entries:
        print("No matching entries found.")
        return 0

    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    # Pretty print
    print(f"\n{'='*60}")
    print(f"  📚 Knowledge Base ({len(entries)} entries)")
    print(f"{'='*60}\n")
    for e in entries:
        tags_str = " ".join(f"#{t}" for t in e.get("tags", []))
        date_str = e.get("date", "")
        rating_str = f" ⭐{e['rating']}" if e.get("rating") else ""
        print(f"  📄 {e['title']}{rating_str}")
        print(f"     📅 {date_str}  🏷 {tags_str}")
        print(f"     📁 {e['path']}")
        if e.get("summary"):
            print(f"     💡 {e['summary'][:120]}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
