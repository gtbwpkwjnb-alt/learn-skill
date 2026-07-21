#!/usr/bin/env python3
"""
Extract Douyin video URL via Playwright, then download with requests.
Usage: python scripts/douyin_playwright_extract.py <url> [--out DIR]
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

def extract_video(url: str, output_dir: Path) -> dict:
    """Navigate to Douyin video, intercept network, extract metadata and video URL."""
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)

    found_urls = []
    page_content = None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = context.new_page()

        def on_response(response):
            nonlocal page_content
            url_r = response.url
            ctype = response.headers.get("content-type", "")
            # Look for actual video streams
            if "video" in ctype and any(t in ctype for t in ["mp4", "mpeg"]):
                if url_r not in found_urls:
                    found_urls.append(url_r)
                    print(f"[VIDEO] {response.status} {url_r} ({ctype})")
            # Douyin VOD URLs do not consistently expose a .mp4 suffix or a
            # video content type, so keep its video stream endpoints as well.
            if (
                (re.search(r"\.mp4", url_r) and "byte" in url_r)
                or "douyinvod.com" in url_r
            ) and url_r not in found_urls:
                found_urls.append(url_r)
                print(f"[MP4] {url_r}")

        page.on("response", on_response)

        print(f"Navigating to {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        title = page.title()
        current_url = page.url
        print(f"Title: {title}")
        print(f"Final URL: {current_url}")

        # Get video element info
        video_info = page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (!v) return { found: false };
                return {
                    found: true,
                    src: v.src || '',
                    currentSrc: v.currentSrc || '',
                    poster: v.poster || '',
                    duration: v.duration || 0,
                };
            }"""
        )
        print(f"Video element: {json.dumps(video_info, ensure_ascii=False)}")
        for candidate in (video_info.get("currentSrc"), video_info.get("src")):
            if candidate and candidate not in found_urls:
                found_urls.append(candidate)

        # Try to trigger video playback
        page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    v.muted = true;
                    v.play().catch(() => {});
                }
            }"""
        )
        time.sleep(5)

        # Check for more URLs after playback
        print(f"Found {len(found_urls)} video URLs after playback")

        # Get page HTML for further analysis
        page_content = page.content()

        page_metadata = page.evaluate(
            """() => {
                const text = (selector) => {
                    const el = document.querySelector(selector);
                    return el ? (el.textContent || '').trim() : '';
                };
                const meta = (selector) => {
                    const el = document.querySelector(selector);
                    return el ? (el.content || '').trim() : '';
                };
                let jsonLd = {};
                for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const value = JSON.parse(el.textContent || '{}');
                        if (value && typeof value === 'object') { jsonLd = value; break; }
                    } catch (_) {}
                }
                const creator = jsonLd.author || jsonLd.creator || {};
                const authorLink = Array.from(document.links).find((el) => {
                    const value = (el.innerText || el.textContent || '').trim();
                    return el.href.includes('/user/') && /(^|\\s)作者(\\s|$)/.test(value);
                });
                const linkedAuthor = authorLink
                    ? (authorLink.innerText || authorLink.textContent || '').replace(/(^|\\s)作者(\\s|$)/g, ' ').trim()
                    : '';
                return {
                    title: meta('meta[property="og:title"]') || jsonLd.name || '',
                    description: meta('meta[property="og:description"]') || jsonLd.description || '',
                    author: text('[data-e2e="video-author-name"]') ||
                            text('[data-e2e="user-title"]') ||
                            text('.account-name') ||
                            meta('meta[name="author"]') ||
                            linkedAuthor ||
                            (typeof creator === 'string' ? creator : (creator.name || '')) || '',
                };
            }"""
        )

        # Collect metadata
        metadata = {
            "title": page_metadata.get("title") or title,
            "author": page_metadata.get("author") or "",
            "description": page_metadata.get("description") or "",
            "url": current_url,
            "video_urls": found_urls,
            "video_element": video_info,
        }

        # Try to extract JSON-LD or RENDER_DATA
        render_data = page.evaluate(
            """() => {
                try {
                    const el = document.getElementById('RENDER_DATA');
                    if (el) return el.textContent;
                    return null;
                } catch(e) { return null; }
            }"""
        )
        if render_data:
            metadata["render_data_found"] = True
            (output_dir / "render_data.json").write_text(render_data, encoding="utf-8")

        context.close()
        browser.close()

    # Save page HTML for debugging
    if page_content:
        (output_dir / "page.html").write_text(page_content, encoding="utf-8")

    return metadata


def download_video(url: str, output_path: Path) -> bool:
    """Download video using yt-dlp or requests."""
    import requests as req

    print(f"Downloading {url} to {output_path}...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }

    try:
        resp = req.get(url, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        total = 0
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        print(f"Downloaded {total / 1024 / 1024:.1f} MB")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Extract Douyin video via Playwright")
    parser.add_argument("url", help="Douyin video URL")
    parser.add_argument("--out", type=Path, default=Path("learn-output"), help="Output dir")
    args = parser.parse_args()

    # Extract video ID from URL
    match = re.search(r"/video/(\d+)", args.url)
    if not match:
        # Try short URL
        print("Resolving short URL...")
    video_id = None

    metadata = extract_video(args.url, args.out)

    # Save metadata
    meta_path = args.out / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nMetadata saved to {meta_path}")

    # Try to download found video URLs
    if metadata.get("video_urls"):
        for i, vu in enumerate(metadata["video_urls"]):
            ext = Path(vu).suffix or ".mp4"
            out_path = args.out / f"video_{i}{ext}"
            if download_video(vu, out_path):
                print(f"Saved to {out_path}")
                break
    else:
        print("No video URLs found via intercept. Trying yt-dlp as fallback...")
        # Try with yt-dlp and cookies if available
        result = subprocess.run(
            [
                "yt-dlp",
                "--cookies", "/tmp/douyin_cookies2.txt",
                "-o", str(args.out / "video.%(ext)s"),
                args.url,
            ],
            capture_output=True, text=True, timeout=120,
        )
        print(result.stdout[-500:] if result.stdout else "")
        if result.returncode != 0:
            print(f"yt-dlp also failed: {result.stderr[-300:]}")


if __name__ == "__main__":
    main()
