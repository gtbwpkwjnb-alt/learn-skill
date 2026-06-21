# Learn Skill / 学习技能 v3.0

> **One link → One knowledge card.** Paste any video/audio/podcast URL, get a structured note in your knowledge base — with AI-generated tags, category, and flashcards.
>
> **一个链接 → 一张知识卡片。** 粘贴任意视频/音频/播客链接，自动生成结构化笔记并导入知识库——含 AI 分类、标签和闪卡。

---

## 🆕 What's New in v3.0

- 🧭 **Router pattern** — Platform detection → extraction routing → unified pipeline (no more monolithic instructions)
- 🔒 **Zero hardcoded secrets** — All API keys in `.env`, references via environment variables
- 📂 **Progressive disclosure** — L1 metadata, L2 SKILL.md body, L3 `scripts/` + `references/` on demand
- 🪝 **Reusable scripts** — `classify.py`, `flashcards.py`, `import_siyuan.py`, `assemble_md.py` callable standalone
- ✅ **Quality self-check** — AI classification shown for user confirmation before import
- ⚡ **Fast-path** — Short content (<500 chars) skips flashcard generation
- 📖 **Rich references** — `platforms.md`, `siyuan-api.md`, `troubleshooting.md`

## ✨ Features / 特性

- 🌐 **Auto network detection** — Detects GFW, YouTube availability, browser presence / 自动检测国内外网络环境
- 🔍 **Multi-platform support** — Douyin, TikTok, Bilibili, YouTube, podcasts, local files, WeChat, XHS / 支持8个平台
- 📥 **Multi-engine extraction** — Captions-first strategy with Whisper fallback / 字幕优先+Whisper兜底
- 🧹 **Smart text processing** — Dedup, fix all-caps, merge fragments, auto-segment / 去重、修正大写、合并片段、自动分段
- 🏷 **AI classification** — DeepSeek-powered topic categorization + tags with quality self-check / DeepSeek 驱动主题分类+质量自检
- 🃏 **Flashcard generation** — Auto-generate 5 Q&A cards (fast-path skips short content) / 自动生成5张问答闪卡（短内容智能跳过）
- 📤 **Triple import targets** — SiYuan (auto-launch!) + Obsidian + local markdown / 思源(自动启动)+Obsidian+本地
- 📦 **Batch processing** — Multiple URLs in one command / 一次处理多个链接
- 🔁 **Dedup protection** — Registry prevents re-processing / 注册表防重复处理
- 📊 **Progress tracking** — Resume interrupted jobs / 断点续传

---

## 🚀 Quick Start / 快速开始

### Prerequisites / 环境要求

```bash
# 1. Python 3.10+
python --version

# 2. ffmpeg (required by all engines)
# Windows: download from https://www.gyan.dev/ffmpeg/builds/
# macOS: brew install ffmpeg
# Linux: apt install ffmpeg

# 3. Install dependencies
pip install hearsay yt-dlp requests
```

### Configuration / 配置

Copy `.env.example` to `tools/.env` and fill in:

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
SIYUAN_TOKEN=xxxxxxxx
# Optional:
BILI_COOKIE=SESSDATA=xxx; ...
OBSIDIAN_VAULT=D:/MyObsidianVault
```

### Installation / 安装

```bash
# Clone the skill
git clone git@github.com:gtbwpkwjnb-alt/learn-skill.git
cd learn-skill

# Install as ZCode skill (progressive disclosure structure)
cp -r SKILL.md scripts/ references/ ~/.agents/skills/learn/
cp learn.py douyin2md.py ~/ZCodeProject/tools/
```

### Usage / 使用

```bash
# Single URL / 单个链接
python learn.py "https://www.bilibili.com/video/BV1GJ411x7h7"

# Batch mode / 批量处理
python learn.py "url1" "url2" "url3"

# With keyframes (douyin/tiktok) / 含关键帧
python learn.py "https://v.douyin.com/xxx/" --frames

# Dry run to preview / 预览
python learn.py "url1" "url2" --dry-run

# Skip import, save locally only / 仅本地保存
python learn.py "url" --no-import
```

### As ZCode Skill / 作为 ZCode 技能

Send any link with a trigger word:
```
学习 https://v.douyin.com/xxx/
summarize video https://www.bilibili.com/video/BVxxx/
extract this link https://example.com/podcast.xml
做闪卡 https://www.bilibili.com/video/BVxxx/
```

Or use standalone scripts:
```bash
# AI classification only
python scripts/classify.py --title "My Video" --summary-file transcript.txt

# Flashcards only
python scripts/flashcards.py --transcript-file transcript.txt

# Import to SiYuan
python scripts/import_siyuan.py --file final.md
```

---

## 📋 Supported Platforms / 支持平台

| Platform 平台 | Pattern 特征 | Engine 引擎 | China 🇨🇳 | Global 🌍 |
|:---|:---|:---|---:|:---|
| 抖音 Douyin | `v.douyin.com/*` | tiktok-extractor | ✅ | ✅ |
| TikTok | `tiktok.com/*` | tiktok-extractor | ✅ | ✅ |
| Bilibili 哔哩哔哩 | `bilibili.com/video/*` | yt-dlp + hearsay | ✅ | — |
| YouTube | `youtube.com/*` | yt-dlp (proxy needed) | ❌ | ✅ |
| Podcasts 播客 | `.xml` `.rss` | hearsay | ✅ | ✅ |
| Local 本地文件 | `.mp4` `.mp3` `.wav` | hearsay whisper | ✅ | ✅ |
| WeChat 微信 | `mp.weixin.qq.com/*` | feedgrab (Edge) | ✅ | — |
| Xiaohongshu 小红书 | `xiaohongshu.com/*` | feedgrab (Edge) | ✅ | — |

> Network environment is auto-detected. Unavailable platforms are filtered.
> 网络环境自动检测，不可用平台自动过滤。

---

## 🏗 Architecture / 架构

```
URL Input → 🌐 Network Detect → 🔍 Platform Detect → 📥 Extract (Router)
    ├── Douyin/TikTok → tiktok-extractor Skill
    ├── Bilibili      → yt-dlp subtitles → hearsay whisper fallback
    ├── Podcast/Local → hearsay (captions-first → whisper)
    └── Unavailable   → ❌ Filtered
         ↓
🧹 Text Processing → 🏷 AI Classify → ✅ Quality Check → 🃏 Flashcards
         ↓                                    ↓
    (short content <500 chars → skip flashcards)
         ↓
📄 Standardized Markdown (YAML + bilingual headers)
         ↓
📤 Import → SiYuan (auto-launch) / Obsidian / Local
```

### Directory Structure / 目录结构

```
learn/
├── SKILL.md                 # Router pattern, ~250 lines
├── scripts/                 # Reusable, standalone scripts
│   ├── classify.py          # AI classification
│   ├── flashcards.py        # Flashcard generation
│   ├── import_siyuan.py     # SiYuan import + auto-launch
│   └── assemble_md.py       # Markdown assembly
├── references/              # On-demand documentation
│   ├── platforms.md         # Per-platform extraction details
│   ├── siyuan-api.md        # SiYuan API reference
│   └── troubleshooting.md   # Common issues & fixes
├── learn.py                 # Main orchestrator (~960 lines)
├── douyin2md.py             # Douyin/TikTok wrapper
├── requirements.txt
├── .env.example
└── README.md
```

### Output Template / 输出模板

```markdown
---
title: "Video Title"
source: "https://..."
platform: "bilibili"
author: "Creator Name"
duration: "15:30"
date: "2026-06-21"
tags: ["AI", "Deep Learning", "Tutorial"]
category: "Technical Learning"
---

# Video Title

## 📋 Metadata / 元数据
- **Platform / 平台**: bilibili
- **Author / 作者**: Creator Name
- **Duration / 时长**: 15:30
- **Source / 来源**: [Original Link](https://...)

## 🤖 AI Classification / AI 分类
- **Category / 主题**: Technical Learning
- **Tags / 标签**: #AI #DeepLearning #Tutorial

## 📝 Transcript / 内容转录
[Cleaned, segmented transcript]

## 🃏 Flashcards / 闪卡
**Q1**: What is the core concept of...?
**A1**: The core concept is...
```

---

## 🔧 Configuration Reference / 配置参考

All sensitive config in `.env` (not committed):

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | — |
| `DEEPSEEK_BASE_URL` | API base URL | `https://api.deepseek.com/v1` |
| `SIYUAN_TOKEN` | SiYuan API token | — |
| `SIYUAN_API` | SiYuan API URL | `http://127.0.0.1:6806` |
| `BILI_COOKIE` | Bilibili cookie (for full captions) | — |
| `OBSIDIAN_VAULT` | Obsidian vault path (fallback target) | — |

---

## 📊 Comparison / 对比

| Feature | learn v2.1 | learn v3.0 | BiliNote | VideoMemo |
|---------|:--:|:--:|:--:|:--:|
| Multi-platform | ✅ | ✅ | ✅ | ✅ |
| Auto network detect | ✅ | ✅ | ❌ | ❌ |
| SiYuan auto-launch | ✅ | ✅ | ❌ | ❌ |
| Obsidian export | ✅ | ✅ | ❌ | ❌ |
| Flashcard generation | ✅ | ✅ | ✅ | ✅ |
| Flashcard fast-path | ❌ | ✅ | ❌ | ❌ |
| Dedup registry | ✅ | ✅ | ❌ | ❌ |
| Batch processing | ✅ | ✅ | ✅ | ✅ |
| Progress resume | ✅ | ✅ | ❌ | ❌ |
| Bilingual output | ✅ | ✅ | ❌ | ❌ |
| Bilibili Cookie | ✅ | ✅ | ❌ | ❌ |
| Transcript cleaning | ✅ | ✅ | ❌ | ❌ |
| Progressive disclosure | ❌ | ✅ | ❌ | ❌ |
| Quality self-check | ❌ | ✅ | ❌ | ❌ |
| Reusable scripts | ❌ | ✅ | ❌ | ❌ |
| Zero hardcoded secrets | ❌ | ✅ | ✅ | ✅ |
| Web UI | ❌ | ❌ | ✅ | ✅ |

---

## 📝 License / 许可证

MIT

---

## 🤝 Contributing / 贡献

Issues and PRs welcome! Focus areas:
- Additional platform support (WeChat, XHS with browser automation)
- Speaker diarization
- Visual content extraction for all platforms
- RAG integration for cross-note Q&A
