# Platform Extraction Reference / 平台提取参考

> Per-platform extraction methods, cookie configuration, fallback strategies, and known limitations.

## Table of Contents

- [Douyin / TikTok](#douyin)
- [Bilibili](#bilibili)
- [Podcasts / RSS](#podcast)
- [Local Audio/Video Files](#local)
- [WeChat (Weixin)](#wechat)
- [Xiaohongshu (XHS)](#xiaohongshu)
- [YouTube](#youtube)

---

## Douyin / TikTok {#douyin}

### Extraction Methods

**Method A (recommended)**: Use tiktok-extractor tool if available.

**Method B**: Use `learn.py`:
```bash
python learn.py "<url>" --extract-only
```

### Supported Link Formats

- `https://v.douyin.com/xxxxx/` — Short link (most common)
- `https://www.douyin.com/video/xxxxx` — Video page
- `https://www.iesdouyin.com/share/video/xxxxx` — Share link
- `https://www.douyin.com/user/xxx?modal_id=xxxxx` — User page video
- `https://www.tiktok.com/@user/video/xxxxx` — TikTok
- `https://vm.tiktok.com/xxxxx/` — TikTok short link

### Output

After extraction, in `learn-output/<id>/`:
- `summary.md` — Metadata + transcript
- `video.mp4` — Watermark-free video (douyin)
- `frames/` — Keyframes (if `--frames` used)

### Limitations

- Requires network access to Douyin/TikTok servers
- Private/deleted videos cannot be extracted
- TikTok may be blocked in some regions

---

## Bilibili {#bilibili}

### Extraction Method

```bash
python learn.py "https://www.bilibili.com/video/BVxxxxxx" --extract-only
```

### Extraction Flow (Two-stage)

**Stage 1: Subtitle download**
- Uses yt-dlp to download official subtitles (prefers `zh-Hans, zh-CN, zh, en`)
- Auto-downloads AI-generated subtitles as fallback (`ai-zh`)
- Subtitle format: SRT

**Stage 2: Whisper fallback**
- If no subtitles available, uses whisper for audio transcription
- Command: `python -m hearsay ingest "<url>" -o <dir>/hearsay.md --transcribe`

### Cookie Configuration (for full subtitle access)

Some Bilibili videos require login cookies for subtitle access. Configure in `.env`:

```env
# Option 1: Full cookie string
BILI_COOKIE="SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx; ..."

# Option 2: SESSDATA only
BILI_SESSDATA="xxx"
```

### Known Limitations

- Member-only videos cannot be extracted
- Cookies expire and need refreshing
- Very long videos (>2h) may timeout on subtitle download

---

## Podcasts / RSS {#podcast}

### Extraction Method

Using hearsay or equivalent tool:
```bash
python -m hearsay ingest "<podcast_rss_url>" -o <output_dir>/podcast.md
```

### Supported Formats

- RSS 2.0 / Atom feeds
- Standard podcast XML
- Direct audio links (`.mp3`, `.m4a`)
- BBC Sounds, Apple Podcasts links

### Output

- `podcast.md` — Title, description, chapters, transcript

---

## Local Audio/Video Files {#local}

### Extraction Method

```bash
python -m hearsay ingest "<file_path>" -o <output_dir>/local.md --transcribe
```

### Supported Formats

- Video: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`
- Audio: `.mp3`, `.wav`, `.flac`, `.m4a`

### Prerequisites

- ffmpeg installed and available in PATH
- Install: `winget install Gyan.FFmpeg` (Windows), `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux)

### Time Estimates

- 1 hour audio → ~5-10 minutes (hardware dependent)

---

## WeChat (Weixin) {#wechat}

### Prerequisites

- A Chromium-based browser (Edge or Chrome)
- feedgrab tool configured

### Extraction Method

Use feedgrab with browser automation. Configure browser User-Agent in `.env`.

### Known Limitations

- Some articles require opening within the WeChat app
- Enterprise WeChat articles may be restricted
- Images/rich media may be lost

---

## Xiaohongshu (XHS) {#xiaohongshu}

### Prerequisites

- Chromium-based browser
- feedgrab tool

### Known Limitations

- Strong anti-scraping measures, success rate varies
- Consider using other platforms when possible

---

## YouTube {#youtube}

### Availability

YouTube may be blocked in some network environments (e.g., mainland China).

### Workarounds

1. **Proxy**: Configure HTTP/HTTPS proxy, then yt-dlp works normally
2. **Manual download**: Download video/subtitle files via proxy, then process as local file
3. **Alternative sources**: Check if the content exists on other platforms

### Proxy Configuration

```env
# In .env file or environment
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```
