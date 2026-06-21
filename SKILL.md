---
name: learn
version: "3.1.0"
description: "视频/音频/播客/文章链接 → 一键提取·AI分类·闪卡·思源笔记导入。支持抖音/B站/YouTube/小红书/微信/播客/本地文件。当用户提到学习、总结视频、记笔记、提取知识、做闪卡、视频笔记、播客转文字、learn、summarize video 时触发。"
user-invocable: true
allowed-tools: [Bash, Read, Write, Skill, Glob, Grep, WebFetch]
---

# Learn / 学习 v3.1

> 一条命令：**任意链接 → 提取 → ZCode AI 分类 → 闪卡 → 思源导入**。8大平台，自动环境适配，全自动管线。
>
> **设计原则**：AI 分析（分类、闪卡）由 ZCode 自身完成，无需额外 API 配置。外部工具只负责内容提取和导入。

## 触发条件

用户消息包含以下**任一触发词+链接**时自动执行本技能：

| 触发词 | 示例 |
|--------|------|
| `学习` / `learn` | `学习 https://www.bilibili.com/video/BVxxx` |
| `总结` / `summarize` | `总结这个视频 https://v.douyin.com/xxx/` |
| `提取` / `extract` | `提取这个链接中的知识` |
| `笔记` / `note` | `给这个视频做笔记` |
| `闪卡` / `flashcard` | `给这篇内容生成闪卡` |
| `转录` / `transcribe` | `把这个播客转成文字` |

也接受直接贴链接说"处理这个"、"分析这个"等。

## 快速决策树

```
收到链接
  ├─ 第一步：平台识别（8种正则）
  ├─ 第二步：按平台路由提取方法
  ├─ 第三步：读取提取结果（summary.md）
  ├─ 第四步：ZCode 内联 AI 分类（你直接分析转录文本）
  ├─ 第五步：ZCode 内联闪卡生成（你直接生成 Q&A）
  ├─ 第六步：组装标准化 Markdown（调用 assemble_md.py）
  └─ 第七步：导入思源（调用 import_siyuan.py）
```

## 平台路由表

| 平台 | 提取方法 | 入口 | 详见 |
|------|---------|------|------|
| 抖音 / TikTok | tiktok-extract Skill | 调用 `Skill("tiktok-extract", url)` | `references/platforms.md#douyin` |
| B站 | yt-dlp 字幕 → hearsay whisper 兜底 | `python tools/learn.py "<url>"` | `references/platforms.md#bilibili` |
| 播客 / RSS | hearsay | `python -m hearsay ingest "<url>"` | `references/platforms.md#podcast` |
| 本地音视频 | hearsay whisper 转写 | `python -m hearsay ingest "<path>" --transcribe` | `references/platforms.md#local` |
| 微信 / 小红书 | feedgrab (需Edge浏览器) | 见 references | `references/platforms.md#wechat` |
| YouTube | 国内被墙 | 提示用户使用代理 | `references/troubleshooting.md#youtube` |

---

## 执行流程

### 步骤 1：平台识别

用以下正则按优先级从上到下匹配：

```
抖音:   (?:v\.douyin\.com|www\.douyin\.com/video|www\.iesdouyin\.com/share/video|douyin\.com/user/.*modal_id)
TikTok: (?:tiktok\.com|vm\.tiktok\.com)
B站:    bilibili\.com/video/
YouTube: (?:youtube\.com/watch|youtu\.be/)
微信:   mp\.weixin\.qq\.com
小红书: xiaohongshu\.com
播客:   \.(?:xml|rss)(?:\?|$)
本地:   \.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$
```

### 步骤 2：内容提取

**推荐方式** — 调用 `tools/learn.py` 仅提取（`--extract-only` 跳过 AI 步骤）：

```bash
C:\Python312\python.exe C:\Users\Administrator\ZCodeProject\tools\learn.py "<URL>" --extract-only --out C:\Users\Administrator\ZCodeProject\learn-output
```

**按平台定制** — 详见 `references/platforms.md`。

### 步骤 3：读取提取结果

提取完成后，查找并读取输出目录中的 `summary.md`。从中解析：
- `title` — 标题
- `platform` — 平台
- `author` — 作者
- `duration` — 时长
- `transcript` — 转录文本（`## 📝 Transcript` section 之后的内容）

### 步骤 4：AI 分类（由你 — ZCode 自身完成）

**你直接分析转录文本**，不需要调用外部 API。读取 transcript 内容后，根据以下指引输出分类结果：

> 分析以下视频/音频内容的标题和前2000字转录，给出：
> 1. 一个最合适的主题分类（10字以内，中文优先）
> 2. 3-5个标签（中文或英文）
>
> 标题: {title}
> 转录前2000字: {transcript[:2000]}
>
> 请用 JSON 格式回复，方便后续步骤解析：
> ```json
> {"category": "主题分类", "tags": ["标签1", "标签2", "标签3"]}
> ```

**质量自检**：分类结果是否与内容明显相关？若分类与内容风马牛不相及（如技术视频分为美食），重新审阅转录文本后再输出。

### 步骤 5：闪卡生成（由你 — ZCode 自身完成）

**快速路径判断**：转录文本 < 500 字 → 跳过闪卡生成（内容太短不适合做闪卡），直接进入步骤6。

**标准路径**（转录 ≥ 500 字）：你直接基于转录内容生成 5 张 Q&A 闪卡：

> 基于以下转录内容，生成5张问答闪卡。每张应测试对关键概念的理解，而非琐碎细节。
> 问题要精准，答案要信息量大但简洁。
>
> 转录内容（前3000字）:
> {transcript[:3000]}
>
> 请用 JSON 数组格式回复：
> ```json
> [{"q": "问题1", "a": "答案1"}, {"q": "问题2", "a": "答案2"}, ...]
> ```

**质量自检**：闪卡内容是否与原文相关？若明显无关则重新生成一次。

### 步骤 6：组装标准化 Markdown

将分类结果和闪卡内容写入临时文件，然后调用 `assemble_md.py`：

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\assemble_md.py ^
  --title "<标题>" --url "<原始链接>" --platform "<平台>" ^
  --author "<作者>" --duration "<时长>" ^
  --transcript-file "<transcript路径>" ^
  --category "<分类>" --tags "<标签1>,<标签2>" ^
  --flashcards-file "<闪卡JSON临时文件路径>" ^
  --out "C:\Users\Administrator\ZCodeProject\learn-output\<slug>\final.md"
```

模板格式（中英双语）：

```markdown
---
title: "{title}"
source: "{url}"
platform: "{platform}"
author: "{author}"
duration: "{duration}"
date: "{today}"
tags: [{tags_json}]
category: "{category}"
---

# {title}

## 📋 Metadata / 元数据
- **Platform / 平台**: ...
- **Author / 作者**: ...
- **Duration / 时长**: ...
- **Source / 来源**: ...

## 🤖 AI Classification / AI 分类
- **Category / 主题**: ...
- **Tags / 标签**: #tag1 #tag2 ...

## 📝 Transcript / 内容转录
...

## 🃏 Flashcards / 闪卡
**Q1**: ...
**A1**: ...
```

### 步骤 7：导入思源笔记

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\import_siyuan.py --file "<final.md路径>"
```

脚本自动：
1. 检测思源是否运行
2. 未运行则自动启动（查找已知安装路径）
3. 等待就绪（最多 15 秒）
4. POST 到 `/api/filetree/createDocWithMd`
5. 导入失败时降级保存到本地 `learn-output/` 目录

详见 `references/siyuan-api.md`。

### 步骤 8：汇报结果

向用户报告最终状态：

```
✅ 学习完成
📄 标题: {title}
🏷 分类: {category} | 标签: {tags}
📥 思源: /学习/{today}/
🃏 闪卡: {count}张 (或 "跳过 - 内容过短")
💾 本地: {local_path}
```

---

## 配置

### 技能模式（ZCode 内联 AI）— 零配置

使用本技能时，AI 分类和闪卡生成由 ZCode 自身完成，**无需任何额外 API 配置**。

### 命令行模式（learn.py 独立运行）

如果你直接在命令行运行 `tools/learn.py`（而非通过技能），它需要 DeepSeek API 来做分类和闪卡。在 `tools/.env` 中配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `SIYUAN_TOKEN` | 思源 API Token | — |
| `BILI_COOKIE` | B站 Cookie（获取完整字幕） | — |
| `OBSIDIAN_VAULT` | Obsidian 库路径（备选导入目标） | — |

---

## 参考文档

按需读取以下文档：

| 文档 | 内容 | 何时读取 |
|------|------|---------|
| `references/platforms.md` | 各平台提取详情、Cookie 配置、降级策略 | 遇到特定平台问题时 |
| `references/siyuan-api.md` | 思源笔记 API 参考、常见操作 | 思源导入失败时 |
| `references/troubleshooting.md` | 常见问题排查、错误码对照 | 任何步骤出错时 |

## 附录：平台正则速查

```
PLATFORM_PATTERNS = {
    "douyin":      [r"v\.douyin\.com|douyin\.com/video|iesdouyin\.com/share/video|douyin\.com/user/.*modal_id"],
    "tiktok":      [r"tiktok\.com|vm\.tiktok\.com"],
    "bilibili":    [r"bilibili\.com/video/"],
    "youtube":     [r"youtube\.com/watch|youtu\.be/"],
    "wechat":      [r"mp\.weixin\.qq\.com"],
    "xiaohongshu": [r"xiaohongshu\.com"],
    "podcast":     [r"\.(?:xml|rss)(?:\?|$)", r"/feed/?$", r"podcast"],
    "local":       [r"\.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$"],
}
```
