#!/usr/bin/env python3
"""
Knowledge Base Router — auto-detect installed note apps, import with fallback chain.

Priority: SiYuan (API) → Obsidian (copy) → Logseq (copy) → Joplin (API) → Trilium (API) → Local save

Usage:
    python kb_router.py --file "path/to/final.md"
    python kb_router.py --markdown "content" --title "Title"

Output (stdout): {"target": "siyuan", "path": "...", "success": true, "error": ""}
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Dotenv loader (lightweight, no dep) ──────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env from skill directory or cwd."""
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v


_load_dotenv()

_IS_WIN = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"


# ── Platform-aware path scanning ─────────────────────────────────────────────

def _scan_paths(base: Path, patterns: list[str]) -> list[Path]:
    """Scan a directory for files matching glob patterns."""
    results: list[Path] = []
    if not base.is_dir():
        return results
    for pat in patterns:
        results.extend(sorted(base.glob(pat)))
    return results


def _common_install_dirs() -> dict[str, list[Path]]:
    """Return platform-specific common install directories per app."""
    home = Path.home()
    if _IS_WIN:
        localappdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        program_files = Path("C:\\Program Files")
        program_files_x86 = Path("C:\\Program Files (x86)")
        return {
            "siyuan": [localappdata / "siyuan", program_files / "siyuan", program_files_x86 / "siyuan"],
            "obsidian": [localappdata / "obsidian", appdata / "obsidian"],
            "logseq": [localappdata / "Logseq", appdata / "Logseq"],
            "joplin": [localappdata / "joplin", appdata / "joplin"],
        }
    if _IS_MAC:
        return {
            "siyuan": [Path("/Applications/SiYuan.app")],
            "obsidian": [Path("/Applications/Obsidian.app"), home / "Library" / "Application Support" / "obsidian"],
            "logseq": [Path("/Applications/Logseq.app"), home / "Library" / "Application Support" / "Logseq"],
            "joplin": [home / "Library" / "Application Support" / "joplin"],
        }
    # Linux
    return {
        "siyuan": [Path("/opt/siyuan"), Path("/usr/bin")],
        "obsidian": [home / ".config" / "obsidian"],
        "logseq": [home / ".config" / "logseq"],
        "joplin": [home / ".config" / "joplin"],
    }


# ── SiYuan detection ─────────────────────────────────────────────────────────

def _siyuan_api_url() -> str:
    return os.environ.get("SIYUAN_API", "http://127.0.0.1:6806")


def _siyuan_token() -> str:
    return os.environ.get("SIYUAN_TOKEN", "")


def _is_siyuan_running() -> bool:
    try:
        req = urllib.request.Request(f"{_siyuan_api_url()}/api/system/version")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _find_siyuan_exe() -> Optional[Path]:
    override = os.environ.get("SIYUAN_EXE", "")
    if override:
        p = Path(override)
        if p.exists():
            return p
    for base_dir in _common_install_dirs().get("siyuan", []):
        if not base_dir.is_dir():
            continue
        for exe in base_dir.glob("**/SiYuan.exe" if _IS_WIN else "**/SiYuan*"):
            return exe
    return None


def _import_siyuan(md_content: str, title: str = "", notebook: str = "学习") -> Dict[str, Any]:
    """Import markdown into SiYuan via API."""
    try:
        import requests  # type: ignore
    except ImportError:
        return {"target": "siyuan", "success": False, "error": "requests library not installed"}

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        resp = requests.post(
            f"{_siyuan_api_url()}/api/filetree/createDocWithMd",
            headers={"Authorization": f"Token {_siyuan_token()}"},
            json={"notebook": notebook, "path": f"/{today}", "markdown": md_content},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0:
            doc_id = data.get("data", {}).get("id", "")
            return {"target": "siyuan", "success": True, "path": f"/{notebook}/{today}", "doc_id": doc_id, "error": ""}
        return {"target": "siyuan", "success": False, "error": data.get("msg", f"code={data.get('code')}")}
    except Exception as e:
        return {"target": "siyuan", "success": False, "error": str(e)}


# ── Obsidian detection ───────────────────────────────────────────────────────

def _find_obsidian_vault() -> Optional[Path]:
    override = os.environ.get("OBSIDIAN_VAULT", "")
    if override:
        p = Path(override)
        if p.is_dir():
            return p
    # Scan standard locations for .obsidian folder
    home = Path.home()
    candidates = [
        home / "Documents" / "Obsidian",
        home / "Documents" / "Obsidian Vault",
        home / "Obsidian",
        *[d for d in home.glob("**/.obsidian") if d.is_dir()],
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _import_obsidian(md_content: str, title: str) -> Dict[str, Any]:
    vault = _find_obsidian_vault()
    if not vault:
        return {"target": "obsidian", "success": False, "error": "Obsidian vault not found"}
    learn_dir = vault / "learn"
    learn_dir.mkdir(parents=True, exist_ok=True)
    slug = title.replace(" ", "_").replace("/", "_")[:64] or "学习笔记"
    # Preserve an existing AI-generated date suffix; otherwise add today's date.
    import re
    if not re.search(r"-\d{4}-\d{2}-\d{2}$", slug):
        slug = f"{slug}-{datetime.now().strftime('%Y-%m-%d')}"
    out_path = learn_dir / f"{slug}.md"
    out_path.write_text(md_content, encoding="utf-8")
    return {"target": "obsidian", "success": True, "path": str(out_path), "error": ""}


# ── Logseq detection ─────────────────────────────────────────────────────────

def _find_logseq_dir() -> Optional[Path]:
    override = os.environ.get("LOGSEQ_DIR", "")
    if override:
        p = Path(override)
        if p.is_dir():
            return p
    home = Path.home()
    candidates = [
        home / "Documents" / "Logseq",
        home / "Logseq",
        *[d for d in home.glob("**/logseq/pages") if d.is_dir()],
    ]
    for c in candidates:
        if c.is_dir():
            return c / "pages" if c.name != "pages" else c
    return None


def _import_logseq(md_content: str, title: str) -> Dict[str, Any]:
    logseq_dir = _find_logseq_dir()
    if not logseq_dir:
        return {"target": "logseq", "success": False, "error": "Logseq directory not found"}
    pages_dir = logseq_dir if logseq_dir.name == "pages" else logseq_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    slug = title.replace(" ", "_").replace("/", "_")[:64] or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = pages_dir / f"{slug}.md"
    out_path.write_text(md_content, encoding="utf-8")
    return {"target": "logseq", "success": True, "path": str(out_path), "error": ""}


# ── Joplin detection ─────────────────────────────────────────────────────────

def _joplin_api_url() -> str:
    return os.environ.get("JOPLIN_API", "http://127.0.0.1:41184")


def _joplin_token() -> str:
    return os.environ.get("JOPLIN_TOKEN", "")


def _import_joplin(md_content: str, title: str) -> Dict[str, Any]:
    token = _joplin_token()
    if not token:
        return {"target": "joplin", "success": False, "error": "JOPLIN_TOKEN not set"}
    try:
        import requests
    except ImportError:
        return {"target": "joplin", "success": False, "error": "requests library not installed"}
    try:
        resp = requests.post(
            f"{_joplin_api_url()}/notes?token={token}",
            json={"title": title, "body": md_content},
            timeout=10,
        )
        data = resp.json()
        note_id = data.get("id", "")
        return {"target": "joplin", "success": bool(note_id), "path": f"joplin://{note_id}", "error": ""}
    except Exception as e:
        return {"target": "joplin", "success": False, "error": str(e)}


# ── Trilium detection ────────────────────────────────────────────────────────

def _trilium_api_url() -> str:
    return os.environ.get("TRILIUM_API", "http://127.0.0.1:8080")


def _trilium_token() -> str:
    return os.environ.get("TRILIUM_TOKEN", "")


def _import_trilium(md_content: str, title: str) -> Dict[str, Any]:
    token = _trilium_token()
    if not token:
        return {"target": "trilium", "success": False, "error": "TRILIUM_TOKEN not set"}
    try:
        import requests
    except ImportError:
        return {"target": "trilium", "success": False, "error": "requests library not installed"}
    try:
        resp = requests.post(
            f"{_trilium_api_url()}/etapi/notes",
            headers={"Authorization": f"Token {token}"},
            json={"title": title, "content": md_content, "type": "text"},
            timeout=10,
        )
        data = resp.json()
        note_id = data.get("noteId", "")
        return {"target": "trilium", "success": bool(note_id), "path": f"trilium://{note_id}", "error": ""}
    except Exception as e:
        return {"target": "trilium", "success": False, "error": str(e)}


# ── Local save (universal fallback) ──────────────────────────────────────────

def _import_local(md_content: str, title: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    out_dir = (base_dir or Path.cwd() / "learn-output") / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = title.replace(" ", "_").replace("/", "_")[:64] or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{slug}.md"
    out_path.write_text(md_content, encoding="utf-8")
    return {"target": "local", "success": True, "path": str(out_path), "error": ""}


# ── Router ───────────────────────────────────────────────────────────────────

KB_PIPELINE: list[tuple[str, str, Any]] = [
    ("siyuan", "API import", _import_siyuan),
    ("obsidian", "file copy", _import_obsidian),
    ("logseq", "file copy", _import_logseq),
    ("joplin", "API import", _import_joplin),
    ("trilium", "API import", _import_trilium),
]


def import_content(
    md_content: str,
    title: str = "",
    *,
    force: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Try each KB in priority order; return first success or last failure.

    Args:
        md_content: Markdown content to import.
        title: Document title.
        force: Force a specific target (e.g. "obsidian", "local").
        base_dir: Base directory for local fallback.

    Returns:
        {"target": str, "success": bool, "path": str, "error": str, ...}
    """
    # Try SiYuan first (auto-start if needed)
    if not force or force == "siyuan":
        if _is_siyuan_running() or _ensure_siyuan_running():
            result = _import_siyuan(md_content, title)
            if result["success"] or force:
                return result

    # Try remaining KBs
    for kb_name, kb_method, kb_func in KB_PIPELINE:
        if force and force != kb_name:
            continue
        if force and force == kb_name:
            result = kb_func(md_content, title)
            if result["success"] or force:
                return result
        if not force:
            result = kb_func(md_content, title)
            if result["success"]:
                return result

    # Local fallback
    return _import_local(md_content, title, base_dir)


def _ensure_siyuan_running() -> bool:
    """Start SiYuan if not running. Returns True if running after attempt."""
    exe = _find_siyuan_exe()
    if not exe:
        return False
    try:
        kwargs: dict = {"cwd": str(exe.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if _IS_WIN:
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        subprocess.Popen([str(exe)], **kwargs)
        for _ in range(15):
            time.sleep(1)
            if _is_siyuan_running():
                return True
    except Exception:
        pass
    return False


def import_file(file_path: str, *, force: Optional[str] = None, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read a markdown file and import it."""
    path = Path(file_path)
    if not path.exists():
        return {"target": "local", "success": False, "path": "", "error": f"File not found: {file_path}"}
    md_content = path.read_text(encoding="utf-8")
    title = path.stem
    return import_content(md_content, title, force=force, base_dir=base_dir)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = ArgumentParser(description="Import markdown into detected knowledge base")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to Markdown file")
    group.add_argument("--markdown", help="Markdown content string")
    parser.add_argument("--title", default="", help="Document title")
    parser.add_argument("--force", default="", choices=["siyuan", "obsidian", "logseq", "joplin", "trilium", "local"],
                        help="Force a specific KB target")
    parser.add_argument("--base-dir", default="", help="Base directory for local fallback")
    args = parser.parse_args()

    if args.file:
        result = import_file(args.file, force=args.force or None,
                             base_dir=Path(args.base_dir) if args.base_dir else None)
    else:
        title = args.title or datetime.now().strftime("%H%M%S")
        result = import_content(args.markdown, title, force=args.force or None,
                                base_dir=Path(args.base_dir) if args.base_dir else None)

    print(json.dumps(result, ensure_ascii=False))
    if result["success"]:
        print(f"✅ Imported to {result['target']}: {result['path']}", file=sys.stderr)
    else:
        print(f"⚠ Import failed: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
