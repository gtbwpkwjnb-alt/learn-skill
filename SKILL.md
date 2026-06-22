---
name: learn
version: "3.4.0"
description: 学习+链接 → 全自动采集·AI总结·深度OCR·入库
user-invocable: true
---

# Learn / 学习 v3.3

> 一条链接 → 全自动管线：采集 → AI分析 → AI总结 → Markdown → 知识库。零配置，零手动，速度/深度自适应。

## 触发规则

用户消息含 **`学习`**（如"学习一下""帮我学习"）或 **`learn`** + 链接时自动触发。无链接则提示提供链接。独立词"总结"不触发本技能（走总结功能），互不干扰。

## 双速自适应决策树

```
收到链接
  ├─ 自判定模式（默认）：
  │   ├─ 播客/RSS/微信/本地.mp3 → 快速（元数据+字幕，~30秒）
  │   └─ 抖音/TikTok/B站/YouTube/本地.mp4 → 深度（元数据+字幕+关键帧+OCR，~3-10分）
  ├─ 显式指定： "学习 快速 <链接>" 或 "学习 深度 <链接>"
  ├─ 第1步：平台识别（正则匹配 URL）
  ├─ 第2步：按平台路由提取命令
  ├─ 第3步：读取提取结果（summary.md）
  ├─ 第4步：AI 分类（你直接分析转录文本，无需 API）
  ├─ 第5步：闪卡生成（转录≥500字），过短则跳过
  ├─ 第6步：AI 总结（你生成 3-5 句摘要）
  ├─ 第7步：组装标准化 Markdown（调用 scripts/assemble_md.py）
  ├─ 第8步：导入知识库（调用 scripts/kb_router.py，自动检测）
  └─ 第9步：汇报结果
```

## 平台 → 提取命令

| 平台 | 快速/深度 | 命令 |
|------|-----------|------|
| 抖音 | 深度 | `python scripts/extract_douyin.py <url> --frames` |
| TikTok | 深度 | `python scripts/extract_douyin.py <url> --frames` |
| B站 | 深度 | `yt-dlp --write-subs <url>` → whisper 兜底 |
| YouTube | 深度 | `yt-dlp --write-subs <url>` → whisper 兜底 |
| 播客/RSS | 快速 | `python -m hearsay ingest <url>` |
| 微信/小红书 | 快速 | 浏览器打开 → 阅读全文 → 手动复制正文 |
| 本地文件 | 自动 | `whisper <file> --model base` |

> **环境检测**：执行前检查 ffmpeg / yt-dlp / whisper / tesseract。降级规则：
> - 缺 tesseract → 跳过 OCR 和关键帧，继续转录
> - 缺 yt-dlp → 尝试 `pip install yt-dlp`，失败则提示手动下载
> - 缺 ffmpeg → 无法提取，报安装命令后终止

---

## 执行流程

### 步骤 1：平台识别

按优先级依次匹配 URL：

```
抖音:   (?:v\.douyin\.com|www\.douyin\.com/video|www\.iesdouyin\.com|douyin\.com/user/.*modal_id)
TikTok: (?:tiktok\.com|vm\.tiktok\.com)
B站:    bilibili\.com/video/
YouTube: (?:youtube\.com/watch|youtu\.be/)
微信:   mp\.weixin\.qq\.com
小红书: xiaohongshu\.com
播客:   \.(?:xml|rss)(?:\?|$) | /feed/?$ | podcast
本地:   \.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$
```

### 步骤 2：内容提取

按上表命令执行提取。深度模式产物结构（`learn-output/<id>/`）：

```
├── summary.md       ← 元数据+转录+关键帧引用+OCR文本
├── transcript.txt
├── video.mp4
├── audio.wav
└── frames/
    ├── scene_001.jpg
    ├── scene_002.jpg
    └── ocr.txt
```

### 步骤 3：读取提取结果

从 `summary.md` 解析：`title`、`platform`、`author`、`duration`、`transcript`（`## 📝 Transcript` 之后内容）。

### 步骤 4：AI 分类（由你完成）

> 分析标题和前2000字转录，输出 JSON：
> `{"category": "主题分类", "tags": ["标签1", "标签2"]}`

自检：分类与内容明显相关？是→继续，否→重审转录。

### 步骤 5：闪卡生成（由你完成）

转录≥500字 → 生成5张Q&A闪卡；<500字 → 跳过。

> 输出 JSON 数组：
> `[{"q": "问题1", "a": "答案1"}, ...]`

自检：闪卡与原文相关？是→继续，否→重生成。

### 步骤 6：AI 总结（由你完成）

> 基于转录内容，用中文生成 3-5 句精华摘要，突出核心观点和关键发现。

### 步骤 7：组装 Markdown

```bash
python scripts/assemble_md.py \
  --title "<标题>" --url "<链接>" --platform "<平台>" \
  --author "<作者>" --duration "<时长>" \
  --transcript-file "<transcript路径>" \
  --category "<分类>" --tags "<tag1>,<tag2>" \
  --flashcards-file "<闪卡JSON路径>" \
  --summary "<AI总结文本>" \
  --out "learn-output/<slug>/final.md"
```

模板（中英双语）：

```markdown
---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration}"
date: "{date}"
tags: [{tags_yaml}]
category: "{category}"
---

# {title}

## 📋 Metadata / 元数据
...

## 🤖 AI Classification / AI 分类
...

## 💡 AI Summary / AI 总结
{summary}

## 📝 Transcript / 内容转录
...

## 🃏 Flashcards / 闪卡
...
```

### 步骤 8：导入知识库

```bash
python scripts/kb_router.py --file "learn-output/<slug>/final.md"
```

自动检测已安装知识库（思源/Obsidian/Logseq/Trilium/Joplin/本地），优先尝试有 API 的，降级到文件复制，本地保存兜底。
强制指定目标：`python scripts/kb_router.py --file "..." --force obsidian`

### 步骤 9：汇报结果

```
✅ 学习完成 | 📄 {title} | 🏷 {category} | 📥 {import_target} | 🃏 {count}张 | 💾 本地路径
```

---

## 配置

参考 `.env.example`（技能目录下）。无需 `.env` 即可作为 AI 技能使用（分类/闪卡/总结由模型在线完成）。

## 参考文档

| 文档 | 内容 | 何时读取 |
|------|------|---------|
| `references/platforms.md` | 各平台提取详情、降级策略 | 特定平台提取出错时 |
| `references/siyuan-api.md` | 思源 API 参考 | 思源导入失败时 |
