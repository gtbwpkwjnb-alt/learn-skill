#!/usr/bin/env python3
"""
连接到正在运行的 Edge 浏览器，利用已有登录态采集内容。
先手动打开 Edge → 按 F12 → 转到控制台可以看到 "DevTools listening on ws://..."
或者用 --remote-debugging-port 启动 Edge。

用法:
    1. 关闭所有 Edge
    2. 以调试模式启动: "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:/Users/Administrator/AppData/Local/Microsoft/Edge/User Data"
    3. 在打开的 Edge 中手动登录 知乎/豆瓣/贴吧
    4. 运行本脚本
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


def collect_with_auth(url: str, output_dir: Path, cdp_url: str = "http://127.0.0.1:9222") -> dict:
    """通过 CDP 连接到已登录的 Edge，利用 cookie 采集内容"""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"url": url, "title": "", "content": "", "platform": "", "success": False, "error": ""}

    with sync_playwright() as p:
        try:
            # 连接到已运行的 Edge
            browser = p.chromium.connect_over_cdp(cdp_url)
            print(f"🔗 已连接到 Edge (CDP: {cdp_url})")
        except Exception as e:
            result["error"] = f"无法连接到 Edge: {e}"
            print(f"❌ {result['error']}")
            return result

        # 使用已有 context（保留所有登录 cookie）
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        try:
            print(f"🌐 正在访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

            result["title"] = page.title()
            result["final_url"] = page.url
            print(f"  标题: {result['title']}")

            # 通用内容提取
            content = extract_main_content(page)
            result["content"] = content
            result["word_count"] = len(content)
            result["success"] = len(content) > 100

            # 截图
            page.screenshot(path=str(output_dir / "screenshot.png"), full_page=True)

            if result["success"]:
                print(f"  ✅ 采集成功: {result['word_count']} 字")
            else:
                print(f"  ⚠️ 内容较少 ({result['word_count']}字)，可能被拦截")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ 采集异常: {e}")
        finally:
            page.close()

    return result


def extract_main_content(page) -> str:
    """从页面提取正文，尝试多种策略"""
    strategies = []

    # 策略1: 知乎专栏
    strategies.append(("zhuanlan", lambda: page.eval_on_selector(
        ".Post-RichText", "el => el.innerText"
    )))

    # 策略2: 知乎问答
    strategies.append(("zhihu_answer", lambda: page.eval_on_selector(
        ".AnswerCard .RichText", "el => el.innerText"
    )))

    # 策略3: 豆瓣日记/笔记
    strategies.append(("douban_note", lambda: page.eval_on_selector(
        ".note-content", "el => el.innerText"
    )))

    # 策略4: 通用 article
    strategies.append(("article", lambda: page.eval_on_selector(
        "article", "el => el.innerText"
    )))

    # 策略5: 通用 .content / #content
    for sel in [".content", "#content", ".post-content", ".entry-content", "main"]:
        strategies.append((sel, lambda s=sel: page.eval_on_selector(s, "el => el.innerText")))

    # 策略6: 全 body（兜底）
    strategies.append(("body", lambda: page.evaluate("() => document.body.innerText")))

    best = ""
    for name, fn in strategies:
        try:
            text = fn()
            if text and len(text) > len(best):
                best = text
                print(f"  📄 策略 '{name}' -> {len(text)} 字")
        except Exception:
            continue

    return best.strip()


def main():
    parser = argparse.ArgumentParser(description="已登录Edge采集器")
    parser.add_argument("url", help="目标URL")
    parser.add_argument("--cdp", default="http://127.0.0.1:9222", help="Edge CDP地址")
    parser.add_argument("--output", "-o", type=Path, default=Path("collected"), help="输出目录")
    args = parser.parse_args()

    result = collect_with_auth(args.url, args.output, args.cdp)

    # 保存结果
    out_file = args.output / "result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if result.get("content"):
        txt_file = args.output / "content.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(f"标题: {result.get('title', '')}\n")
            f.write(f"来源: {result.get('url', '')}\n")
            f.write(f"采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(result["content"])

    print(f"\n📝 结果:")
    print(f"  标题: {result.get('title', '—')}")
    print(f"  字数: {result.get('word_count', 0)}")
    print(f"  状态: {'✅' if result.get('success') else '❌'} | 保存: {out_file}")


if __name__ == "__main__":
    main()
