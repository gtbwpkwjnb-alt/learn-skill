---
name: learn
version: "2.1.0"
description: "Learn / 学习 — 视频/音频链接一键提取·AI分类·闪卡·导入思源笔记。全自动管线。"
user-invocable: true
---

# Learn / 学习 v2.1

> 一条命令：**链接 → 提取 → AI分类 → 闪卡 → 思源导入**，全自动无需手动干预。

---

## 触发方式

当用户消息中包含以下**任一触发词+链接**时，执行本技能：

| 触发词 | 示例 |
|--------|------|
| `学习` | `学习 https://v.douyin.com/xxx/` |
| `总结视频` | `总结视频 https://www.bilibili.com/video/BVxxx` |
| `提取这个链接` | `提取这个链接中的知识` |
| `视频笔记` | `给这个视频做笔记` |

---

## ⚡ 执行流程（必须严格按顺序执行）

### 步骤 1：平台识别

用以下正则识别链接平台（按优先级从上到下匹配）：

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

### 步骤 2：内容提取（按平台执行对应命令）

#### 抖音 / TikTok → 调用 tiktok-extract 技能

**方法A（推荐）**：使用 Skill 工具调用 `tiktok-extract`，传入链接。

**方法B（直接命令）**：
```bash
C:\Python312\python.exe C:\Users\Administrator\ZCodeProject\tools\douyin2md.py "<链接>" --out C:\Users\Administrator\ZCodeProject\learn-output
```

提取完成后，读取 `learn-output\*\summary.md` 获取元数据+逐字稿。

#### B站

```bash
C:\Python312\python.exe -c "
import sys; sys.path.insert(0, r'C:\Users\Administrator\ZCodeProject\tools')
from learn import run_bilibili, detect_network
from pathlib import Path
env = detect_network()
out = Path(r'C:\Users\Administrator\ZCodeProject\learn-output')
md = run_bilibili('<链接>', out, env)
print(f'OUTPUT: {md}')
"
```

提取完成后读取输出的 `summary.md`。

#### 播客 / 本地文件

```bash
C:\Python312\python.exe -m hearsay ingest "<链接>" -o C:\Users\Administrator\ZCodeProject\learn-output\hearsay.md
```

### 步骤 3：读取提取结果

读取 `summary.md` 或 `hearsay.md`，获取：
- 标题 (title)
- 作者 (author)  
- 时长 (duration)
- 转录文本 (transcript)

### 步骤 4：AI 分类（DeepSeek API）

```python
import requests, json

prompt = f"""分析以下视频内容的标题和摘要，给出：
1. 一个最合适的主题分类（10字以内）
2. 3-5个标签（用逗号分隔）

标题: {title}
摘要: {transcript[:2000]}

请用 JSON 格式回复：
{{"category": "主题分类", "tags": ["标签1", "标签2", "标签3"]}}"""

resp = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": "Bearer sk-1474dc8cc9a448888dd549245da8b66d"},
    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 200},
    timeout=30
)
result = json.loads(resp.json()["choices"][0]["message"]["content"])
category = result["category"]
tags = result["tags"]
```

### 步骤 5：生成闪卡（5张 Q&A）

```python
prompt2 = f"""基于以下转录内容，生成5张问答闪卡。每张测试对关键概念的理解。
JSON格式：[{{"q": "问题", "a": "答案"}}, ...]

转录内容:
{transcript[:3000]}"""

resp2 = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": "Bearer sk-1474dc8cc9a448888dd549245da8b66d"},
    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt2}], "temperature": 0.5, "max_tokens": 800},
    timeout=30
)
flashcards = json.loads(resp2.json()["choices"][0]["message"]["content"])
```

### 步骤 6：组装标准化 Markdown

按以下模板生成最终 Markdown（中英双语标题）：

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
- **Platform / 平台**: {platform}
- **Author / 作者**: {author}
- **Duration / 时长**: {duration}
- **Source / 来源**: [{url}]({url})

## 🤖 AI Classification / AI 分类
- **Category / 主题**: {category}
- **Tags / 标签**: {tags_hashtag}

## 📝 Transcript / 内容转录
{transcript}

## 🃏 Flashcards / 闪卡
{flashcards_formatted}
```

### 步骤 7：导入思源笔记

**先确保思源运行**：
```bash
curl -s http://127.0.0.1:6806/api/system/version
```
若不可达 → 启动思源：
```bash
start "" "D:\Program Files\siyuan\SiYuan.exe"
```
等待15秒后重试。

**导入文档**：
```python
import requests

resp = requests.post(
    "http://127.0.0.1:6806/api/filetree/createDocWithMd",
    headers={"Authorization": "Token 1zywc884lc44buwd"},
    json={
        "notebook": "学习",
        "path": f"/学习/{today}",
        "markdown": final_markdown
    },
    timeout=10
)
# code=0 即成功
```

思源不可用时 → 保存到 `C:\Users\Administrator\ZCodeProject\learn-output\` 目录。

### 步骤 8：汇报结果

向用户报告：
```
✅ 已完成
📄 标题: {title}
🏷 分类: {category}
🏷 标签: {tags}
📥 已导入思源: /学习/{today}/
🃏 闪卡: 5张
```

---

## 配置速查

| 配置 | 值 |
|------|-----|
| Python | C:\Python312\python.exe |
| ffmpeg | C:\Tools\ffmpeg-8.1.1-essentials_build\bin |
| 思源 API | http://127.0.0.1:6806 |
| 思源 Token | 1zywc884lc44buwd |
| DeepSeek Key | sk-1474dc8cc9a448888dd549245da8b66d |
| DeepSeek Base | https://api.deepseek.com/v1 |
| 输出目录 | C:\Users\Administrator\ZCodeProject\learn-output |
| tiktok-extractor | C:\Users\Administrator\ZCodeProject\tools\douyin2md.py |

---

## 注意事项

- **抖音链接优先调用 tiktok-extract 技能**（Skill 工具），而非手动逐步骤
- **B站视频**优先用 yt-dlp 下载字幕，无字幕时用 hearsay whisper 转写
- **思源不可用时自动降级**为本地 Markdown 保存
- **重复链接自动跳过**（检查 learn-output\.registry.json）
- 遇到 ffmpeg 缺失：`winget install Gyan.FFmpeg`
- 遇到 yt-dlp 报错：升级 `C:\Python312\python.exe -m pip install -U yt-dlp`
