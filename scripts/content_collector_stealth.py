#!/usr/bin/env python3
"""
Stealth 内容采集器 — 使用反检测技术绕过知乎/豆瓣/贴吧的反爬。
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


# 知乎的反爬检测脚本（绕过 webdriver 检测）
STEALTH_JS = """
// 覆盖 webdriver 属性
Object.defineProperty(navigator, 'webdriver', { get: () => false });
// 覆盖 chrome 对象
window.chrome = { runtime: {} };
// 覆盖 plugins
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
// 覆盖 languages
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
// 覆盖权限查询
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""


def collect(url: str, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"url": url, "title": "", "content": "", "platform": "", "success": False, "error": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            geolocation={"latitude": 39.9042, "longitude": 116.4074},
            permissions=[],
        )

        page = context.new_page()

        # 注入 stealth 脚本
        page.add_init_script(STEALTH_JS)

        try:
            print(f"🌐 正在访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)

            # 模拟人类行为：慢慢滚动
            for i in range(3):
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i+1}/4)")
                time.sleep(1.5)

            result["title"] = page.title()
            result["final_url"] = page.url
            print(f"  标题: {result['title']}")

            # 提取正文
            content = page.evaluate("""() => {
                // 尝试多种选择器
                const selectors = [
                    '.Post-RichText', '.RichText.ztext',
                    '.AnswerCard .RichText',
                    '.note-content', '.article-doc',
                    'article', '.content', '#content',
                    '.post-content', '.entry-content', 'main'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.length > 200) return el.innerText;
                }
                return document.body.innerText;
            }""")

            result["content"] = content.strip()
            result["word_count"] = len(content)
            result["success"] = len(content) > 200

            # 截图
            page.screenshot(path=str(output_dir / "screenshot.png"), full_page=True)

            if result["success"]:
                print(f"  ✅ {result['word_count']} 字")
            else:
                print(f"  ⚠️ 仅 {result['word_count']} 字，可能被拦截")
                # 保存 HTML 以便分析
                page.content()
                (output_dir / "page.html").write_text(page.content(), encoding="utf-8")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ {e}")
        finally:
            context.close()
            browser.close()

    return result


def main():
    parser = argparse.ArgumentParser(description="Stealth 内容采集器")
    parser.add_argument("url", help="目标URL")
    parser.add_argument("--output", "-o", type=Path, default=Path("collected"), help="输出目录")
    args = parser.parse_args()

    result = collect(args.url, args.output)

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

    print(f"\n📝  标题: {result.get('title', '—')}")
    print(f"  字数: {result['word_count']} | {'✅' if result['success'] else '❌'} | {out_file}")


if __name__ == "__main__":
    main()
