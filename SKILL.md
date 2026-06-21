---
name: learn
version: "3.0.0"
description: "视频/音频/播客/文章链接 → 一键提取·AI分类·闪卡·思源笔记导入。支持抖音/B站/YouTube/小红书/微信/播客/本地文件。当用户提到学习、总结视频、记笔记、提取知识、做闪卡、视频笔记、播客转文字、learn、summarize video 时触发。"
user-invocable: true
allowed-tools: [Bash, Read, Write, Skill, Glob, Grep, WebFetch]
---

# Learn / 学习 v3.0

> 一条命令：**任意链接 → 提取 → AI分类 → 闪卡 → 思源导入**。8大平台，自动环境适配，全自动管线。

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
  ├─ 第一步：平台识别（8种正则，见附录）
  ├─ 第二步：按平台路由提取方法（见路由表）
  ├─ 第三步：读取提取结果（summary.md）
  ├─ 第四步：AI 分类（DeepSeek）→ 向用户展示确认
  ├─ 第五步：闪卡生成（短内容跳过）
  ├─ 第六步：组装标准化 Markdown
  └─ 第七步：导入思源（自动启动，失败降级本地保存）
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

**推荐方式** — 直接调用统一入口 `tools/learn.py`（自动识别平台、选择提取方法）：

```bash
C:\Python312\python.exe C:\Users\Administrator\ZCodeProject\tools\learn.py "<URL>" --out C:\Users\Administrator\ZCodeProject\learn-output
```

**按平台定制** — 详见 `references/platforms.md`。

**注意**：
- 抖音链接优先调用 `Skill("tiktok-extract", url)`（用 Skill 工具）
- B站需要 Cookie 才能获取完整字幕（配置 `BILI_COOKIE` 到 `.env`）
- 本地文件自动用 hearsay whisper 转写

### 步骤 3：读取提取结果

提取完成后，查找并读取输出目录中的 `summary.md`：

```bash
powershell -Command "Get-ChildItem -Recurse C:\Users\Administrator\ZCodeProject\learn-output -Filter summary.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content"
```

从 frontmatter 和正文中解析：
- `title` — 标题
- `platform` — 平台
- `author` — 作者
- `duration` — 时长
- `transcript` — 转录文本（`## 📝 Transcript` section 之后的内容）

### 步骤 4：AI 分类

调用 `scripts/classify.py` 进行主题分类：

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\classify.py --title "<标题>" --summary "<摘要前2000字>"
```

输出 JSON：`{"category": "主题分类", "tags": ["标签1", "标签2", "标签3"]}`

**质量自检**：展示分类结果给用户确认。若分类明显不合理（如技术视频被分为美食），重试一次或让用户指定分类。

### 步骤 5：闪卡生成

**快速路径**：转录 < 500 字 → 跳过闪卡生成（内容太短不适合做闪卡）。
**标准路径**：转录 ≥ 500 字 → 生成 5 张 Q&A 闪卡。

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\flashcards.py --transcript "<转录文本前3000字>"
```

输出 JSON：`[{"q": "问题1", "a": "答案1"}, ...]`

**质量自检**：闪卡内容应与原文相关。若生成结果与原文主题无关，丢弃重试一次。

### 步骤 6：组装标准化 Markdown

调用 `scripts/assemble_md.py` 生成最终文档：

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\assemble_md.py ^
  --title "<标题>" --url "<原始链接>" --platform "<平台>" ^
  --author "<作者>" --duration "<时长>" ^
  --transcript-file "<transcript路径>" ^
  --category "<分类>" --tags "<标签1>,<标签2>" ^
  --flashcards-file "<闪卡JSON路径>" ^
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
...

## 🤖 AI Classification / AI 分类
...

## 📝 Transcript / 内容转录
...

## 🃏 Flashcards / 闪卡
...
```

### 步骤 7：导入思源笔记

```bash
C:\Python312\python.exe C:\Users\Administrator\.agents\skills\learn\scripts\import_siyuan.py --file "<final.md路径>"
```

脚本自动：
1. 检测思源是否运行（轮询 `http://127.0.0.1:6806/api/system/version`）
2. 未运行则自动启动（查找 `D:\Program Files\siyuan\SiYuan.exe` 等路径）
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
🃏 闪卡: {count}张
💾 本地: {local_path}
```

## 配置

所有敏感配置放在 **`C:\Users\Administrator\ZCodeProject\tools\.env`**（不提交到 Git）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `SIYUAN_TOKEN` | 思源 API Token | — |
| `SIYUAN_API` | 思源 API 地址 | `http://127.0.0.1:6806` |
| `BILI_COOKIE` | B站 Cookie（获取完整字幕） | — |
| `OBSIDIAN_VAULT` | Obsidian 库路径（备选导入目标） | — |

脚本自动加载 `.env`，无需手动设置环境变量。

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
