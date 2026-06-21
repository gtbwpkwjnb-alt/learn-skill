# Learn Skill / 学习技能 v2.0

> **One link → One knowledge card.** Paste any video/audio/podcast URL, get a structured note in your knowledge base — with AI-generated tags, category, and flashcards.
>
> **一个链接 → 一张知识卡片。** 粘贴任意视频/音频/播客链接，自动生成结构化笔记并导入知识库——含 AI 分类、标签和闪卡。

---

## ✨ Features / 特性

- 🌐 **Auto network detection** — Detects GFW, YouTube availability, Chrome presence / 自动检测国内外网络环境
- 🔍 **Multi-platform support** — Douyin, TikTok, Bilibili, YouTube, podcasts, local files / 支持8个平台
- 📥 **Multi-engine extraction** — Captions-first strategy with Whisper fallback / 字幕优先+Whisper兜底
- 🧹 **Smart text processing** — Dedup, fix all-caps, merge fragments, auto-segment / 去重、修正大写、合并片段、自动分段
- 🏷 **AI classification** — DeepSeek-powered topic categorization + tags / DeepSeek 驱动主题分类
- 🃏 **Flashcard generation** — Auto-generate 5 Q&A cards from content / 自动生成5张问答闪卡
- 📤 **Dual import targets** — SiYuan (auto-launch!) + Obsidian + local markdown / 思源+Obsidian+本地
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
# Windows: winget install Gyan.FFmpeg
# macOS: brew install ffmpeg
# Linux: apt install ffmpeg

# 3. Install dependencies
pip install hearsay yt-dlp requests
```

### Installation / 安装

```bash
# Clone the skill
git clone git@github.com:reasonix/learn-skill.git
cd learn-skill

# Or install as ZCode skill
cp SKILL.md ~/.agents/skills/learn/
cp learn.py ~/ZCodeProject/tools/
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
```

---

## 📋 Supported Platforms / 支持平台

| Platform 平台 | Pattern 特征 | Engine 引擎 | China 🇨🇳 | Global 🌍 |
|:---|:---|:---|---:|:---|
| 抖音 Douyin | `v.douyin.com/*` | tiktok-extractor | ✅ | ✅ |
| TikTok | `tiktok.com/*` | tiktok-extractor | ✅ | ✅ |
| Bilibili 哔哩哔哩 | `bilibili.com/video/*` | yt-dlp + hearsay | ✅ | — |
| YouTube | `youtube.com/*` | — | ❌ | ✅ |
| Podcasts 播客 | `.xml` `.rss` | hearsay | ✅ | ✅ |
| Local 本地文件 | `.mp4` `.mp3` `.wav` | hearsay | ✅ | ✅ |
| WeChat 微信 | `mp.weixin.qq.com/*` | feedgrab | ❌ | ❌ |
| Xiaohongshu 小红书 | `xiaohongshu.com/*` | feedgrab | ❌ | ❌ |

> Network environment is auto-detected. Unavailable platforms are filtered.
> 网络环境自动检测，不可用平台自动过滤。

---

## 🏗 Architecture / 架构

```
URL Input → 🌐 Network Detect → 🔍 Platform Detect → 📥 Extract
    ├── Douyin/TikTok → tiktok-extractor
    ├── Bilibili      → yt-dlp subtitles → hearsay whisper fallback
    ├── Podcast/Local → hearsay (captions-first → whisper)
    └── Unavailable   → ❌ Error
         ↓
🧹 Text Processing → 🏷 AI Classify → 🃏 Flashcards
         ↓
📄 Standardized Markdown (YAML + bilingual headers)
         ↓
📤 Import → SiYuan (auto-launch) / Obsidian / Local
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
[Cleaned, segmented transcript with timestamps]

## 🃏 Flashcards / 闪卡
**Q1**: What is the core concept of...?
**A1**: The core concept is...
```

---

## 🔧 Configuration / 配置

Add to `.env` file (optional):

```bash
# Bilibili Cookie for subtitle access / B站 Cookie 用于获取字幕
BILI_COOKIE="SESSDATA=your_sessdata_here"

# Obsidian vault path for export / Obsidian 库路径
OBSIDIAN_VAULT="D:/MyObsidianVault"
```

---

## 📊 Comparison / 对比

| Feature | learn v1.0 | learn v2.0 | BiliNote | VideoMemo |
|---------|:--:|:--:|:--:|:--:|
| Multi-platform | ✅ | ✅ | ✅ | ✅ |
| Auto network detect | ❌ | ✅ | ❌ | ❌ |
| SiYuan auto-launch | ❌ | ✅ | ❌ | ❌ |
| Obsidian export | ❌ | ✅ | ❌ | ❌ |
| Flashcard generation | ❌ | ✅ | ✅ | ✅ |
| Dedup registry | ❌ | ✅ | ❌ | ❌ |
| Batch processing | ❌ | ✅ | ✅ | ✅ |
| Progress resume | ❌ | ✅ | ❌ | ❌ |
| Bilingual output | ❌ | ✅ | ❌ | ❌ |
| Bilibili Cookie | ❌ | ✅ | ❌ | ❌ |
| Transcript cleaning | ❌ | ✅ | ❌ | ❌ |
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
