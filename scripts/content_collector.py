#!/usr/bin/env python3
"""
通用中文内容采集器（Playwright + 多平台）
Usage:
    python scripts/content_collector.py <url> [--output DIR]

支持的平台：
    - 知乎 zhuanlan.zhihu.com / www.zhihu.com
    - 豆瓣 movie.douban.com / www.douban.com
    - 百度贴吧 tieba.baidu.com
    - 通用网页（fallback）
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


def collect_article(url: str, output_dir: Path) -> dict:
    """Collect article content from a URL using Playwright."""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"url": url, "title": "", "author": "", "content": "", "platform": "", "success": False, "error": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # 识别平台
        if "zhuanlan.zhihu.com" in url:
            result["platform"] = "zhihu_zhuanlan"
        elif "zhihu.com" in url:
            result["platform"] = "zhihu"
        elif "douban.com" in url:
            result["platform"] = "douban"
        elif "tieba.baidu.com" in url:
            result["platform"] = "tieba"
        else:
            result["platform"] = "web"

        try:
            print(f"🌐 正在访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)  # 等待动态内容加载

            result["title"] = page.title()
            result["final_url"] = page.url
            print(f"  标题: {result['title']}")
            print(f"  URL: {result['final_url']}")

            # 按平台提取内容
            if result["platform"] == "zhihu_zhuanlan":
                extracted = extract_zhihu_zhuanlan(page)
            elif result["platform"] == "zhihu":
                extracted = extract_zhihu_qa(page)
            elif result["platform"] == "douban":
                extracted = extract_douban(page)
            elif result["platform"] == "tieba":
                extracted = extract_tieba(page)
            else:
                extracted = extract_generic(page)

            result.update(extracted)

            # 保存页面截图和HTML
            page.screenshot(path=str(output_dir / "screenshot.png"), full_page=True)
            html = page.content()
            (output_dir / "page.html").write_text(html, encoding="utf-8")

            result["success"] = True
            print(f"  ✅ 采集成功: {len(result.get('content', ''))} 字")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ 采集失败: {e}")

        finally:
            context.close()
            browser.close()

    return result


def extract_zhihu_zhuanlan(page) -> dict:
    """提取知乎专栏文章内容"""
    result = {}

    # 标题
    title_el = page.query_selector("h1.Post-Title, h1.ArticleItem-title, .PostIndex-title h1")
    if title_el:
        result["title"] = title_el.inner_text().strip()

    # 作者
    author_el = page.query_selector(".AuthorInfo-name, .AuthorInfo a, .article-author")
    if author_el:
        result["author"] = author_el.inner_text().strip()

    # 正文 - 尝试多个选择器
    content_selectors = [
        ".Post-RichText, .RichText.ztext, .Post-RichTextContainer",
        ".article-content, .content",
        "article",
    ]
    for sel in content_selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 100:
                result["content"] = text
                break

    # 如果没找到，回退到全页面文本提取
    if not result.get("content"):
        body = page.query_selector("body")
        if body:
            result["content"] = body.inner_text().strip()[:10000]

    # 字数统计
    result["word_count"] = len(result.get("content", ""))

    return result


def extract_zhihu_qa(page) -> dict:
    """提取知乎问答内容"""
    result = {}

    # 问题标题
    q_el = page.query_selector("h1.QuestionHeader-title")
    if q_el:
        result["title"] = q_el.inner_text().strip()

    # 回答内容
    answers = page.query_selector_all(".AnswerCard .RichText")
    if answers:
        texts = [a.inner_text().strip() for a in answers if len(a.inner_text().strip()) > 50]
        result["content"] = "\n\n---\n\n".join(texts[:5])  # 前5个回答

    # 字数统计
    result["word_count"] = len(result.get("content", ""))

    return result


def extract_douban(page) -> dict:
    """提取豆瓣内容（文章/日记/讨论）"""
    result = {}

    # 笔记/日记
    title_el = page.query_selector("h1, .note-header h1, .article h1")
    if title_el:
        result["title"] = title_el.inner_text().strip()

    # 正文
    content_selectors = [".note-content", ".article-doc", ".post-content", "#content", "article"]
    for sel in content_selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 50:
                result["content"] = text
                break

    result["word_count"] = len(result.get("content", ""))
    return result


def extract_tieba(page) -> dict:
    """提取百度贴吧帖子内容"""
    result = {}

    title_el = page.query_selector("h1.thread_title, .core_title_txt, .tb_title")
    if title_el:
        result["title"] = title_el.inner_text().strip()

    content_selectors = [
        ".d_post_content, .p_content_text, .j_d_post_content",
        ".l_post .p_content",
        "#j_p_post_content",
    ]
    texts = []
    for sel in content_selectors:
        els = page.query_selector_all(sel)
        for el in els:
            t = el.inner_text().strip()
            if len(t) > 20:
                texts.append(t)
    if texts:
        result["content"] = "\n\n---\n\n".join(texts)

    result["word_count"] = len(result.get("content", ""))
    return result


def extract_generic(page) -> dict:
    """通用网页内容提取"""
    result = {}

    # 尝试多种标题选择器
    for sel in ["h1", "article h1", ".article-title", ".post-title", ".entry-title", "title"]:
        el = page.query_selector(sel)
        if el:
            result["title"] = el.inner_text().strip()
            break

    # 正文提取（优先语义标签）
    content_selectors = [
        "article", ".article", ".post-content", ".entry-content",
        ".content", "#content", "main", ".main-content",
    ]
    for sel in content_selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 100:
                result["content"] = text
                break

    # fallback: body全文
    if not result.get("content"):
        body = page.query_selector("body")
        if body:
            result["content"] = body.inner_text().strip()[:10000]

    result["word_count"] = len(result.get("content", ""))
    return result


def main():
    parser = argparse.ArgumentParser(description="中文内容采集器")
    parser.add_argument("url", help="目标文章URL")
    parser.add_argument("--output", "-o", type=Path, default=Path("collected"), help="输出目录")
    args = parser.parse_args()

    result = collect_article(args.url, args.output)

    # 保存结果
    out_file = args.output / "result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 保存纯文本
    if result.get("content"):
        txt_file = args.output / "content.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(f"标题: {result.get('title', '')}\n")
            f.write(f"作者: {result.get('author', '')}\n")
            f.write(f"来源: {result.get('url', '')}\n")
            f.write(f"平台: {result.get('platform', '')}\n")
            f.write(f"采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(result["content"])

    print(f"\n📝 结果摘要:")
    print(f"  标题: {result.get('title', '—')}")
    print(f"  作者: {result.get('author', '—')}")
    print(f"  字数: {result.get('word_count', 0)}")
    print(f"  状态: {'✅ 成功' if result.get('success') else '❌ 失败'}")
    if result.get("error"):
        print(f"  错误: {result['error']}")
    print(f"  保存: {out_file}")


if __name__ == "__main__":
    main()
