"""Enumerate public videos from a Douyin profile without guessing missing items."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:ies)?douyin\.com/(?:share/)?user/", re.I
)


@dataclass
class ProfileVideo:
    aweme_id: str
    url: str
    title: str = ""
    author: str = ""
    create_time: int = 0


@dataclass
class ProfileEnumeration:
    profile_url: str
    final_url: str
    author: str
    displayed_count: int | None
    videos: list[ProfileVideo] = field(default_factory=list)
    response_attempts: int = 0
    response_pages: int = 0
    api_has_more: bool | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def count_mismatch(self) -> bool:
        return self.displayed_count is not None and self.displayed_count != len(self.videos)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["accessible_count"] = len(self.videos)
        payload["count_mismatch"] = self.count_mismatch
        payload["captured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return payload


def is_profile_url(url: str) -> bool:
    return bool(PROFILE_PATTERN.search(url)) and "modal_id=" not in url.lower()


def _post_payload(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("aweme_list"), list):
            return payload
        for value in payload.values():
            found = _post_payload(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _post_payload(value)
            if found:
                return found
    return None


def parse_aweme_payload(payload: Any) -> tuple[list[ProfileVideo], bool | None]:
    page = _post_payload(payload)
    if not page:
        return [], None
    videos: list[ProfileVideo] = []
    for item in page.get("aweme_list", []):
        if not isinstance(item, dict):
            continue
        aweme_id = str(item.get("aweme_id") or item.get("id") or "").strip()
        if not aweme_id:
            continue
        author_data = item.get("author") if isinstance(item.get("author"), dict) else {}
        videos.append(ProfileVideo(
            aweme_id=aweme_id,
            url=f"https://www.douyin.com/video/{aweme_id}",
            title=str(item.get("desc") or item.get("title") or "").strip(),
            author=str(author_data.get("nickname") or author_data.get("unique_id") or "").strip(),
            create_time=int(item.get("create_time") or 0),
        ))
    has_more = page.get("has_more")
    return videos, bool(has_more) if has_more is not None else None


def _count_value(raw: str) -> int | None:
    raw = raw.replace(",", "").strip()
    try:
        if raw.endswith("万"):
            return int(float(raw[:-1]) * 10000)
        return int(raw)
    except ValueError:
        return None


def displayed_work_count(page_text: str) -> int | None:
    for pattern in (r"作品\s*([\d,.]+万?)", r"([\d,.]+万?)\s*作品"):
        match = re.search(pattern, page_text)
        if match:
            value = _count_value(match.group(1))
            if value is not None:
                return value
    return None


def _launch_chromium(playwright):
    try:
        return playwright.chromium.launch(channel="msedge", headless=True)
    except Exception as first_error:
        try:
            return playwright.chromium.launch(headless=True)
        except Exception:
            raise RuntimeError(f"Playwright Chromium/Edge 启动失败: {first_error}") from first_error


def enumerate_profile_videos(profile_url: str, *, max_scrolls: int = 80) -> ProfileEnumeration:
    """Scroll a public profile and combine paginated API responses with DOM links."""
    from playwright.sync_api import sync_playwright

    api_found: dict[str, ProfileVideo] = {}
    dom_found: dict[str, ProfileVideo] = {}
    response_pages = 0
    response_attempts = 0
    api_has_more: bool | None = None

    with sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()

        def on_response(response) -> None:
            nonlocal response_attempts, response_pages, api_has_more
            if "/aweme/post" not in response.url:
                return
            response_attempts += 1
            try:
                videos, has_more = parse_aweme_payload(response.json())
            except Exception:
                return
            response_pages += 1
            if has_more is not None:
                api_has_more = has_more
            for video in videos:
                api_found.setdefault(video.aweme_id, video)

        page.on("response", on_response)
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        route_scroll = page.locator(".route-scroll-container").first
        use_route_scroll = route_scroll.count() > 0

        stagnant = 0
        for _ in range(max_scrolls):
            before = len(api_found) if api_found else len(dom_found)
            for href in page.locator('a[href*="/video/"]').evaluate_all(
                "els => els.map(el => el.href)"
            ):
                match = re.search(r"/video/(\d+)", href)
                if match:
                    aweme_id = match.group(1)
                    dom_found.setdefault(aweme_id, ProfileVideo(aweme_id, f"https://www.douyin.com/video/{aweme_id}"))
            if use_route_scroll:
                route_scroll.evaluate("element => { element.scrollTop = element.scrollHeight; }")
            else:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(900)
            current_count = len(api_found) if api_found else len(dom_found)
            stagnant = stagnant + 1 if current_count == before else 0
            if response_pages > 0 and api_has_more is False and stagnant >= 2:
                break
            if stagnant >= 12:
                break

        page_text = page.locator("body").inner_text(timeout=5000)
        author = ""
        for selector in ("[data-e2e='user-title']", ".account-name", "h1"):
            locator = page.locator(selector).first
            try:
                text = locator.inner_text(timeout=500).strip()
            except Exception:
                text = ""
            if text:
                author = text
                break
        result = ProfileEnumeration(
            profile_url=profile_url,
            final_url=page.url,
            author=author,
            displayed_count=displayed_work_count(page_text),
            videos=list((api_found or dom_found).values()),
            response_attempts=response_attempts,
            response_pages=response_pages,
            api_has_more=api_has_more,
        )
        context.close()
        browser.close()

    if result.count_mismatch:
        result.warnings.append(
            "页面作品计数与本次公开可访问条数不一致；可能涉及页面缓存、非视频、私密、删除或访问限制，当前证据不足以判定。"
        )
    if not result.videos:
        result.warnings.append("未枚举到公开可访问视频。")
    if result.response_attempts and not result.response_pages:
        result.warnings.append("分页接口返回空响应或无可解析 JSON；结果仅来自当前页面 DOM，不视为完整列表。")
    return result


def write_profile_report(result: ProfileEnumeration, output_root: Path) -> Path:
    report_dir = Path(output_root) / "_profiles"
    report_dir.mkdir(parents=True, exist_ok=True)
    identity = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", result.author).strip(" .-") or "douyin-profile"
    path = report_dir / f"{identity}.json"
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
