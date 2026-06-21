---
name: learn
version: "2.0.0"
description: "Learn / 学习 — One-click video/audio → knowledge base import. Auto-detect network, multi-engine extraction, AI classification, flashcard generation. Supports SiYuan & Obsidian."
user-invocable: true
---

# Learn / 学习 v2.0

> **One link → One knowledge card.** Paste any video/audio/podcast URL, get a structured note in your knowledge base — with AI-generated tags, category, and flashcards.
>
> **一个链接 → 一张知识卡片。** 粘贴任意视频/音频/播客链接，自动生成结构化笔记并导入知识库——含 AI 分类、标签和闪卡。

---

## Trigger / 触发词

| Trigger (EN) | 触发词 (CN) | Example / 示例 |
|-------------|------------|---------------|
| `learn` | `学习` | `学习 https://v.douyin.com/xxx/` |
| `summarize video` | `总结视频` | `总结视频 https://www.bilibili.com/video/BVxxx` |
| `extract this link` | `提取这个链接` | `提取这个链接中的知识` |
| `video notes` | `视频笔记` | `给这个视频做笔记` |
| `import link` | `整理链接` | `整理链接知识入库` |

---

## Supported Platforms / 支持平台

| Platform | URL Pattern | Engine | China 🇨🇳 | Global 🌍 |
|----------|------------|--------|:--:|:--:|
| 抖音 Douyin | `v.douyin.com/*` `douyin.com/video/*` | tiktok-extractor | ✅ | ✅ |
| TikTok | `tiktok.com/*` `vm.tiktok.com/*` | tiktok-extractor | ✅ | ✅ |
| Bilibili 哔哩哔哩 | `bilibili.com/video/*` | yt-dlp + hearsay | ✅ | — |
| YouTube | `youtube.com/*` `youtu.be/*` | — | ❌ need proxy | ✅ |
| Podcasts 播客 | `.xml` `.rss` | hearsay | ✅ | ✅ |
| Local files 本地 | `.mp4` `.mp3` `.wav` `.mkv` | hearsay | ✅ | ✅ |
| WeChat 微信 | `mp.weixin.qq.com/*` | feedgrab (via Edge) | ✅ via Edge | — |
| Xiaohongshu 小红书 | `xiaohongshu.com/*` | feedgrab (via Edge) | ✅ via Edge | — |

> **Auto-detection**: The skill detects your network environment and automatically filters unavailable platforms.
> **自动检测**: 技能自动检测网络环境，过滤不可用平台。

---

## Output Targets / 输出目标

| Target | Status | Auto-start? | Notes |
|--------|:--:|:--:|-------|
| **SiYuan 思源笔记** | ✅ | ✅ | Auto-launches if not running |
| **Obsidian** | ✅ | — | Set `OBSIDIAN_VAULT` env var |
| **Local Markdown** | ✅ | — | Always saved as fallback |

---

## Workflow / 工作流

```
URL Input / 链接输入
    │
    ▼
🌐 Network Detection / 网络环境检测
    │  (China GFW? YouTube accessible? Chrome installed?)
    │
    ▼
🔍 Platform Detection / 平台识别
    │  (Regex match → douyin/tiktok/bilibili/youtube/podcast/local/wechat/xhs)
    │
    ▼
📥 Content Extraction / 内容提取
    ├─ Douyin/TikTok → tiktok-extractor pipeline (metadata + transcript + frames)
    ├─ Bilibili      → yt-dlp subtitles (with Cookie) → hearsay whisper fallback
    ├─ Podcast/Local → hearsay (captions-first → faster-whisper fallback)
    └─ Unavailable   → ❌ Error with actionable message
    │
    ▼
🧹 Text Processing / 文本处理
    ├─ SRT → plain text (strip timestamps & sequence numbers)
    ├─ Dedup consecutive identical lines / 去重连续重复行
    ├─ Fix ALL-CAPS lines / 修正全大写行
    ├─ Merge short fragments / 合并过短片段
    └─ Segment long text into ## sections / 长文本自动分段
    │
    ▼
🏷 AI Classification (DeepSeek) / AI 分类
    ├─ Category / 主题分类
    └─ Tags (3-5) / 标签
    │
    ▼
🃏 Flashcard Generation / 闪卡生成
    └─ 5 Q&A cards from key concepts / 从关键概念生成5张问答卡
    │
    ▼
📄 Standardized Markdown / 标准化输出
    ├─ YAML frontmatter (title, source, platform, author, duration, date, tags, category)
    ├─ Bilingual section headers / 中英双语章节标题
    └─ AI classification section + Flashcards section
    │
    ▼
📤 Import / 导入
    ├─ SiYuan (auto-start if needed) → /学习/YYYY-MM-DD/
    ├─ Obsidian → vault/learn/
    └─ Local → learn-output/ (always saved)
```

---

## Usage / 使用方法

### As ZCode Skill (automatic) / ZCode 技能调用（自动）

Just send a link with a trigger word:
```
学习 https://v.douyin.com/xxx/
summarize video https://www.bilibili.com/video/BVxxx/
extract this link https://example.com/podcast.xml
```

### CLI (manual) / 命令行

```bash
# Single URL / 单个链接
python learn.py "https://www.bilibili.com/video/BV1GJ411x7h7"

# Batch mode / 批量处理
python learn.py "url1" "url2" "url3"

# With keyframes (douyin/tiktok only) / 含关键帧
python learn.py "https://v.douyin.com/xxx/" --frames

# Skip import, save locally only / 仅本地保存
python learn.py "url" --no-import

# Dry run / 预览
python learn.py "url" --dry-run

# Custom output directory / 自定义输出目录
python learn.py "url" --out ./my-notes
```

---

## Configuration / 配置

| Variable | Default | Purpose / 用途 |
|----------|---------|---------------|
| `BILI_COOKIE` | — | Bilibili SESSDATA for subtitle access / B站 Cookie 用于获取字幕 |
| `OBSIDIAN_VAULT` | — | Obsidian vault path for export / Obsidian 库路径 |
| `SIYUAN_TOKEN` | Auto | SiYuan API auth token / 思源 API 令牌 |
| `DEEPSEEK_KEY` | Auto | DeepSeek API key for AI classification / AI 分类 API 密钥 |

Add to `.env` file in project root:
```bash
BILI_COOKIE="SESSDATA=your_sessdata_here"
OBSIDIAN_VAULT="D:/MyObsidianVault"
```

---

## Features / 特性矩阵

| Feature | v1.0 | v2.0 |
|---------|:--:|:--:|
| Multi-platform extraction | ✅ | ✅ |
| YAML frontmatter standardization | ✅ | ✅ |
| AI classification (DeepSeek) | ✅ | ✅ |
| SiYuan auto-import | ✅ | ✅ |
| SiYuan auto-launch | ❌ | ✅ |
| Network environment detection | ❌ | ✅ |
| URL dedup registry | ❌ | ✅ |
| Transcript cleaning & dedup | ❌ | ✅ |
| Long text segmentation | ❌ | ✅ |
| Batch URL processing | ❌ | ✅ |
| Progress tracking (resume) | ❌ | ✅ |
| Flashcard generation | ❌ | ✅ |
| Bilibili Cookie support | ❌ | ✅ |
| Obsidian export | ❌ | ✅ |
| Bilingual output (CN/EN) | ❌ | ✅ |
| Graceful degradation (multi-fallback) | ❌ | ✅ |

---

## Error Handling / 故障处置

| Scenario | Action |
|----------|--------|
| SiYuan not running | 🔧 Auto-launch, wait 15s, retry |
| SiYuan not installed | ⚠ Fallback to Obsidian or local |
| AI classify timeout | ⚠ Skip, mark as "未分类" |
| Bilibili no subtitles | 🔄 yt-dlp → hearsay whisper fallback |
| Douyin video private/deleted | ❌ Exit code 2, show stderr |
| YouTube blocked (China) | ❌ "需要代理 / need proxy" |
| WeChat/XHS no Chrome | ❌ "需要Chrome浏览器 / need Chrome" |
| Duplicate URL | ⏭ Skip with message |
| ffmpeg missing | ❌ Exit code 1, show install path |

---

## File Structure / 文件结构

```
learn-skill/
├── SKILL.md              ← This file / 本文件
├── README.md             ← GitHub README (bilingual)
├── learn.py              ← Main orchestrator / 主编排脚本
├── douyin2md.py          ← Douyin/TikTok wrapper
└── requirements.txt      ← Python dependencies
```

---

## Requirements / 依赖

- Python 3.10+
- ffmpeg (auto-detected)
- hearsay (`pip install hearsay`)
- yt-dlp (`pip install yt-dlp`)
- tiktok-extractor (for Douyin/TikTok)
- DeepSeek API key (for AI classification)
