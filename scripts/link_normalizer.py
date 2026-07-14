"""Normalize copied links before the learn extraction pipeline consumes them.

The module deliberately keeps the original input separate from the canonical
content URL.  A copied share message can include emojis, promotional links,
short links, and tracking parameters; downstream extractors must only receive
the canonical URL, while callers can still persist the original value for
audit/debugging.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import ipaddress
from pathlib import Path
import re
import socket
from typing import Callable, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。；：！？、（）()【】\[\]{}《》]+", re.IGNORECASE)

TRACKING_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "igsh", "igshid", "si",
    "spm", "spm_id_from", "from_spmid", "from", "source", "src",
    "ref", "refer", "referer", "scene", "share", "share_id",
    "share_token", "share_source", "share_medium", "share_plat",
    "share_session_id", "is_copy_url", "timestamp", "vd_source",
    "feature",
}
TRACKING_PREFIXES = ("utm_", "share_", "spm_", "mc_")
TRAILING_PUNCTUATION = ".,;:!?，。；：！？、"

SHORT_LINK_HOSTS = {
    "v.douyin.com",
    "b23.tv",
    "bili2233.cn",
    "youtu.be",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "xhslink.com",
}

SUPPORTED_HOST_SUFFIXES = {
    "douyin": ("douyin.com", "iesdouyin.com"),
    "tiktok": ("tiktok.com",),
    "bilibili": ("bilibili.com", "b23.tv", "bili2233.cn"),
    "youtube": ("youtube.com", "youtu.be"),
    "wechat": ("mp.weixin.qq.com",),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "podcast": ("spotify.com", "podcasts.apple.com", "music.apple.com"),
}


class LinkNormalizationError(ValueError):
    """Raised when no usable URL or local media path can be extracted."""


@dataclass
class NormalizedLink:
    raw_input: str
    extracted_url: str
    canonical_url: str
    resolved_url: Optional[str] = None
    platform_hint: Optional[str] = None
    removed_params: tuple[str, ...] = ()
    resolution_error: Optional[str] = None
    is_local_path: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _strip_trailing_punctuation(url: str) -> str:
    """Remove copy-message punctuation without damaging valid URL content."""
    candidate = url.strip()
    while candidate and candidate[-1] in TRAILING_PUNCTUATION:
        candidate = candidate[:-1]
    pairs = {')': '(', ']': '[', '}': '{'}
    while candidate and candidate[-1] in pairs:
        closing = candidate[-1]
        if candidate.count(closing) > candidate.count(pairs[closing]):
            candidate = candidate[:-1]
        else:
            break
    return candidate


def extract_urls(value: str) -> list[str]:
    """Extract de-duplicated HTTP(S) URLs from arbitrary copied text."""
    text = html.unescape(value or "").replace("\u200b", "").replace("\ufeff", "")
    matches = [_strip_trailing_punctuation(item) for item in URL_PATTERN.findall(text)]
    seen: set[str] = set()
    urls: list[str] = []
    for item in matches:
        if item and item not in seen:
            seen.add(item)
            urls.append(item)
    return urls


def platform_hint(url: str) -> Optional[str]:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    for platform, suffixes in SUPPORTED_HOST_SUFFIXES.items():
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
            return platform
    return None


def _is_tracking_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_KEYS or lowered.startswith(TRACKING_PREFIXES)


def _clean_query(items: Iterable[tuple[str, str]]) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    cleaned: list[tuple[str, str]] = []
    removed: list[str] = []
    for key, value in items:
        if _is_tracking_key(key):
            removed.append(key)
        else:
            cleaned.append((key, value))
    return cleaned, tuple(removed)


def canonicalize_url(url: str) -> tuple[str, tuple[str, ...]]:
    """Strip tracking noise and normalize known content URL shapes."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise LinkNormalizationError(f"不是可读取的 HTTP(S) 链接: {url}")
    if parts.username or parts.password:
        raise LinkNormalizationError("不接受包含用户名或密码的链接")

    host = parts.hostname.lower().rstrip(".")
    path = parts.path or "/"
    query_items, removed = _clean_query(parse_qsl(parts.query, keep_blank_values=True))
    fragment = ""

    # YouTube short/share links become one canonical watch URL.
    if host == "youtu.be":
        video_id = path.strip("/").split("/", 1)[0]
        if video_id:
            keep = [(key, value) for key, value in query_items if key in {"t", "start", "list", "index"}]
            return urlunsplit(("https", "www.youtube.com", "/watch", urlencode([("v", video_id), *keep]), "")), removed

    if host == "youtube.com" or host.endswith(".youtube.com"):
        short_match = re.match(r"^/shorts/([^/?#]+)", path)
        if short_match:
            keep = [(key, value) for key, value in query_items if key in {"t", "start"}]
            return urlunsplit(("https", "www.youtube.com", "/watch", urlencode([("v", short_match.group(1)), *keep]), "")), removed
        if path == "/watch":
            keep_keys = {"v", "t", "start", "list", "index"}
            query_items = [(key, value) for key, value in query_items if key in keep_keys]
            return urlunsplit(("https", "www.youtube.com", "/watch", urlencode(query_items), "")), removed

    # Bilibili video URLs only need the video identity, page, and timestamp.
    bvid_match = re.search(r"/video/(BV[\w]+)", path, re.IGNORECASE)
    if host.endswith("bilibili.com") and bvid_match:
        keep = [(key, value) for key, value in query_items if key in {"p", "t"}]
        return urlunsplit(("https", "www.bilibili.com", f"/video/{bvid_match.group(1)}", urlencode(keep), "")), removed

    # A Douyin profile share with modal_id is equivalent to a video page.
    modal_id = next((value for key, value in query_items if key == "modal_id" and value), "")
    if (host == "douyin.com" or host.endswith(".douyin.com")) and modal_id and "/user/" in path:
        return urlunsplit(("https", "www.douyin.com", f"/video/{modal_id}", "", "")), removed
    if host == "douyin.com" or host.endswith(".douyin.com"):
        video_match = re.match(r"^/video/(\d+)", path)
        if video_match:
            return urlunsplit(("https", "www.douyin.com", f"/video/{video_match.group(1)}", "", "")), removed

    # Preserve the essential signed query for WeChat/Xiaohongshu/Apple podcasts,
    # while dropping known tracking keys above.
    return urlunsplit(("https", host, path, urlencode(query_items, doseq=True), fragment)), removed


def _is_public_host(url: str) -> bool:
    """Reject localhost/private targets before following an external redirect."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)


def _request_without_redirect(url: str, method: str, timeout: float) -> tuple[int, Optional[str]]:
    opener = build_opener(_NoRedirect())
    request = Request(
        url,
        method=method,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; zhixi-learn/5.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Range": "bytes=0-0",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.headers.get("Location")
    except HTTPError as error:
        return error.code, error.headers.get("Location")


def resolve_short_url(url: str, *, timeout: float = 8.0, max_redirects: int = 5) -> str:
    """Resolve a known short link with bounded, public-only redirects."""
    current = url
    for _ in range(max_redirects):
        if not _is_public_host(current):
            raise LinkNormalizationError("短链重定向目标不是公网地址")
        status, location = _request_without_redirect(current, "HEAD", timeout)
        if status in {405, 403}:
            status, location = _request_without_redirect(current, "GET", timeout)
        if status not in {301, 302, 303, 307, 308}:
            return current
        if not location:
            raise LinkNormalizationError("短链返回重定向但未提供目标地址")
        current = urljoin(current, location)
    raise LinkNormalizationError(f"短链重定向超过 {max_redirects} 次")


def _is_local_media(value: str) -> bool:
    candidate = value.strip().strip('"\'')
    if not candidate or "\n" in candidate or "\r" in candidate:
        return False
    if Path(candidate).exists():
        return True
    return bool(re.search(r"\.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$", candidate, re.IGNORECASE))


def _candidate_score(url: str) -> int:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host in SHORT_LINK_HOSTS:
        return 90
    return 100 if platform_hint(url) else 0


def normalize_input(
    value: str,
    *,
    resolve_short_links: bool = True,
    resolver: Callable[[str], str] = resolve_short_url,
) -> NormalizedLink:
    """Return one canonical learn input from a copied share message or path."""
    raw_input = value or ""
    if _is_local_media(raw_input) and not extract_urls(raw_input):
        local = raw_input.strip().strip('"\'')
        return NormalizedLink(raw_input, local, local, is_local_path=True, platform_hint="local")

    urls = extract_urls(raw_input)
    if not urls:
        raise LinkNormalizationError("未在输入中发现 HTTP(S) 链接或本地媒体路径")

    # Prefer supported content links over marketing/landing links in the same text.
    ordered = sorted(enumerate(urls), key=lambda item: (-_candidate_score(item[1]), item[0]))
    first_result: Optional[NormalizedLink] = None
    for _, extracted in ordered:
        resolved_url: Optional[str] = None
        resolution_error: Optional[str] = None
        candidate = extracted
        host = (urlsplit(candidate).hostname or "").lower().rstrip(".")
        if resolve_short_links and host in SHORT_LINK_HOSTS:
            try:
                resolved_url = resolver(candidate)
                candidate = resolved_url
            except (LinkNormalizationError, URLError, OSError, ValueError) as error:
                resolution_error = str(error)

        try:
            canonical, removed = canonicalize_url(candidate)
        except LinkNormalizationError:
            continue
        result = NormalizedLink(
            raw_input=raw_input,
            extracted_url=extracted,
            canonical_url=canonical,
            resolved_url=resolved_url,
            platform_hint=platform_hint(canonical),
            removed_params=removed,
            resolution_error=resolution_error,
        )
        if first_result is None:
            first_result = result
        if result.platform_hint:
            return result

    if first_result is None:
        raise LinkNormalizationError("链接格式无法规范化")
    return first_result
