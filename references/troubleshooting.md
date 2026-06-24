# Troubleshooting / 故障排查

> Common issues and solutions for content extraction and import.

## Table of Contents

- [Environment Issues](#environment)
- [Extraction Issues](#extraction)
- [AI Classification / Flashcards](#ai)
- [SiYuan Import Issues](#siyuan)
- [Common Error Codes](#errors)

---

## Environment Issues {#environment}

### ffmpeg not found

**Symptom**: `ffmpeg: command not found` or `'ffmpeg' is not recognized`

**Solution**:
```bash
# Check if installed
which ffmpeg        # Linux/macOS
where ffmpeg        # Windows

# Install if missing
# Windows: winget install Gyan.FFmpeg
#   Or download from https://www.gyan.dev/ffmpeg/builds/
# macOS:   brew install ffmpeg
# Linux:   sudo apt install ffmpeg
```

### DeepSeek API key not configured

**Symptom**: `⚠ DEEPSEEK_API_KEY not configured`

**Note**: Classification, flashcards and summary are done by the AI model inline — no API key needed for normal use. Only relevant if running scripts standalone.

**Solution**: Add to `.env`:
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### SiYuan Token not configured

**Symptom**: SiYuan import returns 401 error

**Solution**:
1. Open SiYuan → Settings → About → API Token
2. Copy token to `.env`: `SIYUAN_TOKEN=xxxxxxxx`

---

## Extraction Issues {#extraction}

### Bilibili subtitle download failed

**Symptom**: yt-dlp errors, no subtitle file generated

**Troubleshooting steps**:
1. Verify cookie is valid — log into Bilibili in a browser, copy cookie to `.env`
2. Verify video exists — open the link manually to confirm it plays
3. Try AI subtitles — enable AI subtitles on Bilibili web player and retry
4. Fallback to Whisper — the script auto-switches to whisper transcription

### Douyin link not recognized

**Symptom**: `❌ Unable to identify platform`

**Check**:
- Confirm link contains `douyin.com/video/`, `v.douyin.com/`, or `iesdouyin.com/share/video/`
- Confirm it's not a `tiktok.com` link (international version, different handling)

### Transcription timeout

**Symptom**: hearsay/whisper runs for >15 minutes without completing

**Cause**: Long audio (1h+) requires significant transcription time

**Solution**:
- Wait for completion (normal behavior)
- If timeout fails, split into shorter segments manually

### YouTube not accessible

**Symptom**: Connection errors when accessing YouTube links

**Solution**:
1. Configure proxy in `.env`: `HTTP_PROXY=http://127.0.0.1:7890`
2. Or download video manually and process as local file

---

## AI Classification / Flashcards / Summary

### Classification result is wrong

**Symptom**: Tech video classified as "Cooking" etc.

**Handling**:
1. Retry once (temporary API instability)
2. Manually specify the correct category
3. Check if transcript contains noise/garbage text

### Flashcards unrelated to content

**Symptom**: Generated Q&A doesn't match video topic

**Handling**:
1. Discard current flashcards and regenerate
2. Use a more focused transcript segment
3. Content too short → auto-skipped (< 500 chars)

### AI output quality issues

**Symptom**: Classification, summary or flashcards don't match content

**Handling**:
1. The model re-analyzes the transcript directly — no API involved
2. If quality is low, retry once with a longer transcript excerpt
3. Very short content (< 500 chars) auto-skips flashcard generation

### Highlights / Deep Thinking / Glossary generation failed

**Symptom**: `⚠ 亮点生成失败` / `⚠ 深度思考生成失败` / `⚠ 术语生成失败`

**Cause**: API call failure (timeout, rate limit, or parsing error)

**Handling**:
1. Check network connection and API key (`DEEPSEEK_API_KEY`)
2. Retry — the script auto-retries up to 3 times with exponential backoff
3. These are optional features — the document is still generated without them
4. If consistently failing, check `.api_call_log.json` in `learn-output/` for details

### API rate limit reached

**Symptom**: `⚠ 安全拦截：今日 API 调用已达上限` or `⏳ 达每分钟上限`

**Cause**: Exceeded safety limits (200 calls/day or 15 calls/minute)

**Handling**:
1. Wait until next day for daily limit reset
2. Or set `LEARN_SKIP_SAFETY=1` in environment to bypass (not recommended)
3. Check API call usage in `.api_call_log.json`
4. Reduce batch size — each URL now uses up to 5 API calls (classify + highlights + deep thinking + glossary + rating + flashcards)

### Consecutive failures auto-stop

**Symptom**: `⚠ 连续失败 N 次，跳过后续 AI 步骤`

**Cause**: 3+ consecutive API failures for the same URL

**Handling**:
1. Check network stability
2. Verify API key is valid and has sufficient quota
3. The script will continue processing remaining URLs
4. The partially-processed document is still saved locally

### Mermaid knowledge graph empty

**Symptom**: Knowledge graph section shows no related notes

**Cause**: No matching tags found in registry, or processing first content

**Handling**:
1. Normal for the first processed URL — graphs build up over time
2. Ensure tags are being generated correctly (check classification output)
3. Verify registry file exists at `learn-output/.registry.json`

---

## KB Import Issues {#siyuan}

### SiYuan won't start

**Symptom**: `⚠ SiYuan executable not found`

**Solution**:
1. Set `SIYUAN_EXE` env var to the correct path
2. Start SiYuan manually, then retry `kb_router.py`
3. Force alternative target: `python scripts/kb_router.py --file "..." --force obsidian`

### Import fails even when SiYuan is running

**Symptom**: SiYuan is running but API returns errors

**Troubleshooting**:
1. Verify token: `curl http://127.0.0.1:6806/api/system/version`
2. Confirm notebook exists
3. Check SiYuan logs (Settings → About → Logs)

### Fallback to local save

When no knowledge base is detected, notes are saved locally via `kb_router.py`:
```
./learn-output/<slug>/final.md
```

---

## Common Error Codes {#errors}

| Error | Meaning | Solution |
|-------|---------|----------|
| `❌ Unable to identify platform` | Link format not supported | Check link format against supported platforms |
| `❌ Content extraction failed` | Extraction produced no output | Check network, cookies, tool installation |
| `⚠ Missing dependencies` | ffmpeg/yt-dlp/tesseract not found | Run the install command provided in the error |
| `⚠ SiYuan API error` | SiYuan import returned error | Check token and notebook config |
| `⏭ Skipped (already processed)` | Duplicate link | Normal behavior — dedup working |
| `⚠ 安全拦截` | API call limit reached | Wait for reset or set `LEARN_SKIP_SAFETY=1` |
| `⚠ 连续失败 N 次` | 3+ consecutive API failures | Check network & API key; continues to next URL |
| `⏳ 达每分钟上限` | Per-minute rate limit hit | Auto-waits 60s then retries |
