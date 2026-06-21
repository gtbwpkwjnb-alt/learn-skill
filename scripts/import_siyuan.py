#!/usr/bin/env python3
"""
SiYuan note import script — auto-detect, launch, and import Markdown documents.

Usage:
    python import_siyuan.py --file "path/to/final.md"
    python import_siyuan.py --markdown "content" --title "Doc Title"

Output (stdout): {"success": true, "doc_id": "20240621...", "path": "/notebook/2024-06-21"}

Importable:
    from import_siyuan import ensure_siyuan_running, import_markdown
    ensure_siyuan_running()
    import_markdown(md_content, "Title")
"""

import sys, os, json, time, subprocess, argparse, platform
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


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

SIYUAN_API = os.environ.get("SIYUAN_API", "http://127.0.0.1:6806")
SIYUAN_TOKEN = os.environ.get("SIYUAN_TOKEN", "")
SIYUAN_STARTUP_WAIT = int(os.environ.get("SIYUAN_STARTUP_WAIT", "15"))

# Cross-platform SiYuan paths — override with SIYUAN_EXE env var
_IS_WIN = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"

SIYUAN_PATHS: List[str] = []
if _IS_WIN:
    SIYUAN_PATHS = [
        r"D:\Program Files\siyuan\SiYuan.exe",
        r"C:\Program Files\siyuan\SiYuan.exe",
        r"D:\SiYuan\SiYuan.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\siyuan\SiYuan.exe"),
    ]
elif _IS_MAC:
    SIYUAN_PATHS = [
        "/Applications/SiYuan.app/Contents/MacOS/SiYuan",
        os.path.expanduser("~/Applications/SiYuan.app/Contents/MacOS/SiYuan"),
    ]
else:  # Linux
    SIYUAN_PATHS = [
        "/opt/siyuan/siyuan",
        "/usr/bin/siyuan",
        os.path.expanduser("~/.local/bin/siyuan"),
    ]


def find_siyuan_exe() -> Optional[Path]:
    """Find SiYuan executable, respecting SIYUAN_EXE override."""
    custom = os.environ.get("SIYUAN_EXE", "")
    if custom and Path(custom).exists():
        return Path(custom)

    for p in SIYUAN_PATHS:
        path = Path(p)
        if path.exists():
            return path
    return None


def is_siyuan_running() -> bool:
    """Check if SiYuan is currently running."""
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"{SIYUAN_API}/api/system/version")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def ensure_siyuan_running() -> bool:
    """Ensure SiYuan is running; start it if not."""
    if is_siyuan_running():
        return True

    exe = find_siyuan_exe()
    if not exe:
        print("⚠ SiYuan executable not found. Set SIYUAN_EXE env var or install SiYuan.", file=sys.stderr)
        return False

    print(f"🔧 Starting SiYuan: {exe}", file=sys.stderr)
    try:
        kwargs = dict(
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if _IS_WIN:
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        subprocess.Popen([str(exe)], **kwargs)

        for i in range(SIYUAN_STARTUP_WAIT):
            time.sleep(1)
            if is_siyuan_running():
                print(f"✅ SiYuan started (took {i+1}s)", file=sys.stderr)
                return True

        print(f"⚠ SiYuan startup timed out ({SIYUAN_STARTUP_WAIT}s)", file=sys.stderr)
    except Exception as e:
        print(f"⚠ Failed to start SiYuan: {e}", file=sys.stderr)

    return False


def import_markdown(md_content: str, title: str = "",
                    notebook: str = "学习") -> Dict:
    """Import Markdown content to SiYuan.

    Args:
        md_content: Markdown content string
        title: Document title (used in path)
        notebook: Notebook name (default "学习")

    Returns:
        {"success": bool, "doc_id": str, "path": str, "error": str}
    """
    import requests

    today = datetime.now().strftime("%Y-%m-%d")
    notebook_path = f"/{today}"

    try:
        resp = requests.post(
            f"{SIYUAN_API}/api/filetree/createDocWithMd",
            headers={"Authorization": f"Token {SIYUAN_TOKEN}"},
            json={
                "notebook": notebook,
                "path": notebook_path,
                "markdown": md_content,
            },
            timeout=15,
        )
        data = resp.json()

        if data.get("code") == 0:
            doc_id = data.get("data", {}).get("id", "")
            return {
                "success": True,
                "doc_id": doc_id,
                "path": f"/{notebook}{notebook_path}",
                "error": "",
            }
        else:
            return {
                "success": False,
                "doc_id": "",
                "path": "",
                "error": data.get("msg", f"API code={data.get('code')}"),
            }
    except requests.exceptions.RequestException as e:
        return {"success": False, "doc_id": "", "path": "", "error": str(e)}


def import_file(file_path: str, notebook: str = "学习") -> Dict:
    """Import a Markdown file to SiYuan.

    Args:
        file_path: Path to Markdown file
        notebook: Notebook name
    """
    md_path = Path(file_path)
    if not md_path.exists():
        return {"success": False, "doc_id": "", "path": "",
                "error": f"File not found: {file_path}"}

    md_content = md_path.read_text(encoding="utf-8")
    title = md_path.stem
    return import_markdown(md_content, title, notebook)


def main():
    parser = argparse.ArgumentParser(description="SiYuan note import")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to Markdown file")
    group.add_argument("--markdown", help="Markdown content string")
    parser.add_argument("--title", default="", help="Document title")
    parser.add_argument("--notebook", default="学习", help="Notebook name (default: 学习)")
    parser.add_argument("--no-start", action="store_true",
                        help="Do not auto-start SiYuan")
    args = parser.parse_args()

    # Ensure SiYuan is running
    if not args.no_start:
        if not ensure_siyuan_running():
            print(json.dumps({
                "success": False,
                "doc_id": "",
                "path": "",
                "error": "SiYuan unavailable: not installed or cannot start",
            }, ensure_ascii=False))
            sys.exit(1)

    # Import
    if args.file:
        md_content = Path(args.file).read_text(encoding="utf-8")
        title = args.title or Path(args.file).stem
    else:
        md_content = args.markdown
        title = args.title or datetime.now().strftime("%H%M%S")

    result = import_markdown(md_content, title, args.notebook)
    print(json.dumps(result, ensure_ascii=False))

    if result["success"]:
        print(f"✅ Imported to SiYuan: {result['path']}", file=sys.stderr)
    else:
        print(f"⚠ Import failed: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
