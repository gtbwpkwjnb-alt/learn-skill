#!/usr/bin/env python3
"""
思源笔记导入脚本 — 自动检测思源状态、启动、导入 Markdown 文档。

用法:
    python import_siyuan.py --file "path/to/final.md"
    python import_siyuan.py --markdown "markdown内容" --title "文档标题"

输出 (stdout): {"success": true, "doc_id": "20240621...", "path": "/学习/2024-06-21"}

也可作为模块导入:
    from import_siyuan import ensure_siyuan_running, import_markdown
    ensure_siyuan_running()
    import_markdown(md_content, "标题")
"""

import sys, os, json, time, subprocess, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

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

SIYUAN_API = os.environ.get("SIYUAN_API", "http://127.0.0.1:6806")
SIYUAN_TOKEN = os.environ.get("SIYUAN_TOKEN", "")
SIYUAN_STARTUP_WAIT = 15  # seconds

# 思源可能的安装路径
SIYUAN_PATHS = [
    r"D:\Program Files\siyuan\SiYuan.exe",
    r"C:\Program Files\siyuan\SiYuan.exe",
    r"D:\SiYuan\SiYuan.exe",
]


def find_siyuan_exe() -> Optional[Path]:
    """查找思源可执行文件。"""
    for p in SIYUAN_PATHS:
        path = Path(p)
        if path.exists():
            return path
    return None


def is_siyuan_running() -> bool:
    """检测思源是否正在运行。"""
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"{SIYUAN_API}/api/system/version")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def ensure_siyuan_running() -> bool:
    """确保思源运行中：已运行返回True，否则启动并等待就绪。"""
    if is_siyuan_running():
        return True

    exe = find_siyuan_exe()
    if not exe:
        print("⚠ 未找到思源安装路径", file=sys.stderr)
        return False

    print(f"🔧 正在启动思源笔记: {exe}", file=sys.stderr)
    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        for i in range(SIYUAN_STARTUP_WAIT):
            time.sleep(1)
            if is_siyuan_running():
                print(f"✅ 思源已启动 (耗时 {i+1}s)", file=sys.stderr)
                return True

        print(f"⚠ 思源启动超时 ({SIYUAN_STARTUP_WAIT}s)", file=sys.stderr)
    except Exception as e:
        print(f"⚠ 启动思源失败: {e}", file=sys.stderr)

    return False


def import_markdown(md_content: str, title: str = "",
                    notebook: str = "学习") -> Dict:
    """导入 Markdown 到思源笔记。

    Args:
        md_content: Markdown 内容
        title: 文档标题（用于路径）
        notebook: 笔记本名称，默认"学习"

    Returns:
        {"success": bool, "doc_id": str, "path": str, "error": str}
    """
    import requests

    today = datetime.now().strftime("%Y-%m-%d")
    safe_title = title or datetime.now().strftime("%H%M%S")
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
    """从文件导入 Markdown 到思源。

    Args:
        file_path: Markdown 文件路径
        notebook: 笔记本名称
    """
    md_path = Path(file_path)
    if not md_path.exists():
        return {"success": False, "doc_id": "", "path": "",
                "error": f"文件不存在: {file_path}"}

    md_content = md_path.read_text(encoding="utf-8")
    title = md_path.stem
    return import_markdown(md_content, title, notebook)


def main():
    parser = argparse.ArgumentParser(description="思源笔记导入")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Markdown 文件路径")
    group.add_argument("--markdown", help="Markdown 文本内容")
    parser.add_argument("--title", default="", help="文档标题")
    parser.add_argument("--notebook", default="学习", help="笔记本名称 (默认: 学习)")
    parser.add_argument("--no-start", action="store_true",
                        help="不自动启动思源")
    args = parser.parse_args()

    # 确保思源运行
    if not args.no_start:
        if not ensure_siyuan_running():
            print(json.dumps({
                "success": False,
                "doc_id": "",
                "path": "",
                "error": "思源笔记不可用：未安装或无法启动",
            }, ensure_ascii=False))
            sys.exit(1)

    # 导入
    if args.file:
        md_content = Path(args.file).read_text(encoding="utf-8")
        title = args.title or Path(args.file).stem
    else:
        md_content = args.markdown
        title = args.title or datetime.now().strftime("%H%M%S")

    result = import_markdown(md_content, title, args.notebook)
    print(json.dumps(result, ensure_ascii=False))

    if result["success"]:
        print(f"✅ 已导入思源: {result['path']}", file=sys.stderr)
    else:
        print(f"⚠ 导入失败: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
