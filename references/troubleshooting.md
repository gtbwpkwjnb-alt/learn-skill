# Troubleshooting / 故障排查

> Common issues and solutions for the learn skill.

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

**Note**: This only matters for **CLI standalone mode**. When used as an AI skill, classification and flashcards are done by the AI model directly — no API key needed.

**Solution** (CLI mode only): Add to `.env`:
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

## AI Classification / Flashcards {#ai}

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

### External API errors (CLI mode only)

**Symptom**: `⚠ Classification request failed` or HTTP 5xx

**Handling**:
1. Check network: `curl -s https://api.deepseek.com/v1/models`
2. Check API balance: visit platform.deepseek.com
3. If API is down, skip AI steps and generate basic notes

---

## SiYuan Import Issues {#siyuan}

### SiYuan won't start

**Symptom**: `⚠ SiYuan executable not found`

**Solution**:
1. Verify installation path is in the search list
2. Set `SIYUAN_EXE` env var to the correct path
3. Start SiYuan manually, then retry
4. Or use `--no-start` to skip auto-start

### Import fails even when SiYuan is running

**Symptom**: SiYuan is running but API returns errors

**Troubleshooting**:
1. Verify token: `curl http://127.0.0.1:6806/api/system/version`
2. Confirm notebook exists
3. Check SiYuan logs (Settings → About → Logs)

### Fallback to local save

When SiYuan is completely unavailable, notes are saved locally to:
```
./learn-output/<slug>/final.md
```

---

## Common Error Codes {#errors}

| Error | Meaning | Solution |
|-------|---------|----------|
| `❌ Unable to identify platform` | Link format not supported | Check link format against supported platforms |
| `❌ Content extraction failed` | Extraction produced no output | Check network, cookies, tool installation |
| `⚠ Classification failed` | External API error (CLI mode) | Check API key and network |
| `⚠ Flashcards failed` | External API error or content too short | Short content auto-skipped; check API config |
| `⚠ SiYuan API error` | SiYuan import returned error | Check token and notebook config |
| `⏭ Skipped (already processed)` | Duplicate link | Normal behavior — dedup working |
