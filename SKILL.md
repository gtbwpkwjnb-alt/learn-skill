---
name: learn
version: "5.1.0"
description: 学习+链接 → 自动提取·AI分析·闪卡·导入Obsidian
user-invocable: true
---

# zhixi-learn v5.1.0

> **一条链接 → 全增强知识卡片。** AI 分类 + 亮点提取 + 深度思考 + 术语解释 + 评分 + 知识图谱 + 闪卡 + 章节总结 + 多知识库导入。双速自适应，零配置。
>
> **One link → one enhanced knowledge card.** AI classification, highlights, deep thinking, glossary, rating, knowledge graph, flashcards, chapter summaries, and multi-KB import. Dual-speed auto-adaptive, zero config.

---

## 0. 🧬 自检自进化引擎（Self-Check & Self-Evolution）

> **每次执行前自动运行。** 检测环境 → 加载记忆 → 预判问题 → 选择最优路径 → 执行后更新记忆。

### 0a. 前置综合自检

执行任何提取前，运行完整环境扫描并输出汇总报告：

```bash
# 检测内容
ffmpeg  → 音视频处理          [必要 | 无可降级]
yt-dlp  → 视频/字幕下载       [必要
playwright → 浏览器自动化      [推荐
faster-whisper → 音频转录      [必要
scenedetect → 关键帧提取       [深度可选
PaddleOCR → OCR（推荐，中英双语最优，Apache-2.0） [深度可选
browser_cookie3 → 浏览器Cookie [辅助可选
python    → Python 解释器路径   [必要]
```

**自检输出格式**（供用户一目了然）：
```
🔍 Learn 环境自检报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ ffmpeg         → /usr/bin/ffmpeg
❌ PaddleOCR      → MISSING (影响: 跳过OCR)
❌ scenedetect    → MISSING (影响: 跳过关键帧)
⚠️ 提示: 安装缺失项可提升深度模式质量
     pip install paddleocr scenedetect
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**规则**：
- `❌ 必要缺失` → 先尝试自动安装，失败则**提前告知用户**并终止，不给用户"执行到一半才报错"的体验
- `❌ 可选缺失` → 标注"影响：XXX将被跳过"，列出安装命令，**继续执行**
- `✅ 全部就绪` → 正常进入提取流程

### 0b. 环境状态记忆（Skill State）

在 `<output_dir>/.skill_state.json` 持久化环境状态，跨会话记忆：
> 路径优先级：`$LEARN_OUTPUT` 环境变量 → 默认 `./learn-output/`

```json
{
  "last_check": "2026-06-24T15:20:00",
  "env": {
    "ffmpeg": {"found": true, "version": "8.1.1", "path": "/usr/bin/ffmpeg"},
    "yt-dlp": {"found": true, "version": "2026.06.01"},
    "playwright": {"found": true, "version": "1.60.0"},
    "faster-whisper": {"found": true},
    "PaddleOCR": {"found": false, "last_attempt": "2026-06-24"},
    "scenedetect": {"found": false, "last_attempt": "2026-06-24"}
    "browser_cookie3": {"found": true}
  },
  "platform_memory": {
    "douyin": {
      "last_success_method": "playwright_intercept",
      "yt-dlp_cookie_issues": true,
      "cookies_available": false,
      "last_success": "2026-06-24"
    }
  },
  "stats": {
    "total_extractions": 3,
    "successful": 3,
    "failed": 0,
    "last_extraction": "2026-06-24"
  }
}
```

**记忆用途**：
1. 跳过重复检测（缓存 < 1小时直接复用）
2. 预判问题（如上次抖音用了 playwright，这次优先尝试 playwright）
3. 统计成功率（持续失败的平台标记为"不稳定"，提前告知用户）

### 0c. 平台记忆路由

根据 `.skill_state.json` 的 `platform_memory` 选择最优提取路径：

| 记忆内容 | 路由决策 |
|---------|---------|
| 上次抖音 yt-dlp 成功 | 先用 yt-dlp（快） |
| 上次抖音 yt-dlp 因 cookie 失败 | 优先 playwright（绕开 cookie 问题） |
| 首次 / 无记忆 | 按默认顺序尝试：yt-dlp → 失败 → playwright 自动兜底 |

### 0d. 自进化规则

每次执行后，更新 `.skill_state.json`：

```python
# 伪代码逻辑
if extraction_successful:
    state.stats.successful += 1
    state.platform_memory[platform].last_success_method = method_used
    state.platform_memory[platform].last_success = now
else:
    state.stats.failed += 1
    if error contains "cookie":
        state.platform_memory[platform].yt-dlp_cookie_issues = True
    if error contains "timeout":
        state.platform_memory[platform].needs_proxy = True
```

**版本演进**：累计失败 > 3 次的平台，在触发时主动提示："该平台上次连续失败，建议检查网络/账号状态后重试。"

---

## 触发规则

用户消息含 **`学习+`**、**`learn+`**、**`知析`**、**`zhixi`** 等关键词 + 分享链接时自动触发。无链接则提示提供链接。

### 链接提取规则（分享文本、短链与推广参数）

复制内容不等于可提取内容。必须先调用 `scripts/link_normalizer.py` 的规范化逻辑，再把 `canonical_url` 传给平台识别和下载器：

1. 从整段分享文案中提取全部 HTTP(S) URL，去掉表情、中文标点、引号和零宽字符。
2. 当同一文本含推广页与视频/播客页时，优先选择已支持的平台链接，不取第一个 URL。
3. 对 `v.douyin.com`、`b23.tv`、`youtu.be`、`vm.tiktok.com`、`xhslink.com` 等已知短链，最多跟随 5 次公网重定向；禁止解析 localhost、内网或非 HTTP(S) 目标。
4. 移除 `utm_*`、`spm*`、`share_*`、`vd_source`、`fbclid`、`gclid` 等推广/追踪参数；保留 B站 `p/t`、微信签名参数、YouTube `v/t/list` 等内容参数。
5. 规范化后的 URL 用于去重、平台识别、提取与最终来源；原始输入、短链解析结果、移除参数和失败原因写入任务进度，便于追溯。
6. 本地音视频路径不经过 URL 清洗。短链解析不可用时保留已清洗的短链并继续尝试，不把网络错误误报为“无链接”。

命令行使用 `--no-resolve-links` 可关闭短链网络解析；`--dry-run` 会显示规范化后的 URL 和移除的追踪参数。

## 前置条件

执行前检查以下依赖。缺失时按降级规则运行：

| 依赖 | 等级 | 用途 | 降级 |
|------|------|------|------|
| ffmpeg | 🔴 必需 | 音视频处理 | ❌ 无法继续，报安装命令后终止 |
| playwright | 🔴 必需（抖音） | 浏览器自动化 → 网络拦截下载视频 | ⚠ `pip install playwright && playwright install chromium` |
| faster-whisper | 🔴 必需 | 音频转录 | ⚠ `pip install faster-whisper` 尝试安装 |
| yt-dlp | 🟢 辅助
| PaddleOCR | 🟡 深度模式 | OCR 文字提取 | ⚠ 跳过 OCR |
| scenedetect | 🟡 深度模式 | 关键帧提取 | ⚠ 跳过关键帧 |
| browser_cookie3 | 🟢 推荐 | 从浏览器提取 Cookie | ⚠ 跳过浏览器 Cookie 方式，使用无 Cookie 降级 |

> **降级规则说明**：
> - 🔴 缺失 → 自动尝试安装，失败后**提前终止**并告知用户（不执行到一半才报错）
> - 🟡 缺失 → 标注影响范围，**继续执行**，但输出中标记"部分功能受限"
> - 🟢 缺失 → 标注可优化项，不影响执行

## 双速自适应决策树

```
收到链接
  ├─ 0. 自检自进化引擎（每次必执行）
  │   ├─ 检测所有依赖
  │   ├─ 加载 .skill_state.json
  │   ├─ 输出自检报告给用户
  │   └─ 根据平台记忆路由选择最佳方法
  ├─ 自判定模式（默认）：
  │   ├─ 播客/RSS/微信/本地.mp3 → 快速（元数据+字幕，~30秒）
  │   └─ 抖音/TikTok/B站/YouTube/本地.mp4 → 深度（元数据+字幕+关键帧+OCR，~3-10分）
  ├─ 降级提示：深度模式缺 scenedetect 或全部 OCR provider 时自动降为"浅深度"（无关键帧/OCR）
  ├─ 显式指定： "学习 快速 <链接>" 或 "学习 深度 <链接>"
  ├─ 风格控制（可选）：
  │   ├─ "简单点" → style=beginner（加类比、减术语）
  │   ├─ "详细点" → style=detailed（章节扩至100-150字）
  │   └─ 默认     → style=balanced
  ├─ 第1步：平台识别（正则匹配 URL）
  ├─ 第2步：URL 清洗（去除分享杂项，提取纯净链接）
  ├─ 第3步：按平台路由提取：
  │   ├─ 抖音 → `python tools/zhixi-learn.py <url> --no-import`  # Playwright网络拦截
  │   ├─ B站  → `bilibili-cli 字幕时间线 → yt-dlp → ASR 兜底`
  │   ├─ 本地 → `python tools/zhixi-learn.py <local_path> --no-import`
  │   └─ 播客 → `python tools/zhixi-learn.py <url> --no-import`
  ├─ 第4步：AI 综合分析（全文 Map 分段 → Reduce 汇总 → 原文证据 Verify）
  ├─ 第5步：知识图谱（语义关联：tags 交集匹配已有笔记）
  ├─ 第6步：组装增强 Markdown（关键帧截图 + 层级模板）
  ├─ 第7步：导入 Obsidian/思源（Obsidian 优先）
  └─ 第8步：汇报结果（含评分和链接）
```

## 平台 → 提取命令

> 完整平台提取详情、Cookie 配置、兜底策略见 [references/platforms.md](references/platforms.md)
>
> 核心命令（统一入口）：
> - 抖音/TikTok/B站/播客/本地 → `python tools/zhixi-learn.py <url>`
> - 小红书/通用网页 → `python scripts/extract_webpage.py <url>`
- 通用网页深度爬取 → **Firecrawl MCP**（已预装，JS渲染/结构化提取）

> **环境检测**：执行前运行 0a 综合自检。降级规则：
> - PP-OCRv6（隔离环境）优先；旧 PaddleOCR 初始化失败时回退 Tesseract；都不可用才跳过 OCR，继续转录
> - 缺 scenedetect → 跳过关键帧，继续转录
> - 缺 ffmpeg → 无法提取，报安装命令后终止
> - 缺 playwright → 仅影响抖音兜底路径

---

## 执行流程

### 第0步：全环境综合自检

执行前先运行自检脚本，集中检查所有依赖并输出报告。**不逐个报错打断用户**。

```python
# 自检脚本逻辑（简化）
checks = {
    "ffmpeg": {"required": True, "cmd": "where ffmpeg"},
    "yt-dlp": {"required": True, "cmd": "yt-dlp --version"},
    "playwright": {"recommended": True, "cmd": "python -c \"from playwright.sync_api import sync_playwright; print('OK')\""},
    "faster-whisper": {"required": True, "cmd": "python -c \"import faster_whisper; print('OK')\""},
    "scenedetect": {"optional_depth": True, "cmd": "python -c \"import scenedetect; print('OK')\""},
    "tesseract": {"optional_depth": True, "cmd": "where tesseract"},
}
# 输出汇总，而非逐个报错
```

> **自检输出**：无论成功与否，都以格式化表格输出给用户。缺失项附带安装命令。

### 步骤 1：平台识别

按优先级依次匹配 URL：

```
抖音:   (?:v\.douyin\.com|www\.douyin\.com/video|www\.iesdouyin\.com|douyin\.com/user/.*modal_id)
TikTok: (?:tiktok\.com|vm\.tiktok\.com)
B站:    bilibili\.com/video/
YouTube: (?:youtube\.com/watch|youtu\.be/)
微信:   mp\.weixin\.qq\.com
小红书: xiaohongshu\.com
播客:   \.(?:xml|rss)(?:\?|$) | /feed/?$
本地:   \.(?:mp4|mkv|avi|mov|mp3|wav|flac|m4a|webm)$
```

### 步骤 2：内容提取（含多级兜底）

按上表命令执行提取。各平台兜底逻辑：

#### 抖音/TikTok 特定兜底流程

```
yt-dlp <url>
  ├─ 成功 ✅ → 正常处理
  ├─ 失败: "Fresh cookies are needed"
  │   ├─ 尝试 browser_cookie3 从浏览器提取 Cookie 重试
  │   ├─ 再失败 → Playwright 拦截方案
  │   │   ├─ 用 playwright 打开页面
  │   │   ├─ 拦截网络请求获取真实视频 URL（douyinvod.com）
  │   │   ├─ 如果视频无音频 → 拦截音频 URL 一起下载
  │   │   └─ ffmpeg 合并音视频
  │   └─ 更新 .skill_state.json 记录"douyin: yt-dlp cookie issue"
  └─ 更新 .skill_state.json 记录"douyin: yt-dlp ok"
```

> **音视频分离处理（抖音特有）**：
> 抖音将视频（h264）和音频（aac）分为两个 URL 发送。Playwright 拦截时将捕获到两个 `douyinvod.com` 的请求：
> - 含 `video/tos` → 视频流 → 保存为 video.mp4
> - 含 `media-audio` → 音频流 → 保存为 audio_source.mp4
> - ffmpeg 合并：`ffmpeg -i video.mp4 -i audio_source.mp4 -c copy -map 0:v:0 -map 1:a:0 output.mp4`

> **长视频转写恢复**：抖音/TikTok 深度提取器对超过 20 分钟的音频按 20 分钟切段（2 秒重叠）转写。每完成一段即在同目录写入 `transcription_progress.json`；同一音频再次执行时仅处理未完成分段。音频大小或修改时间变化会自动废弃旧进度，避免混用不同来源的转写结果。

深度模式处理中工件结构（`learn-output/_tasks/<task_id>/`）：

> 完整产物结构树和 Markdown 模板见 [references/output-format.md](references/output-format.md)

**新增**：
- `extraction.log` → 记录每一步执行结果、耗时、降级原因，用于自检自进化分析
- `audio_source.mp4` → 抖音等平台单独下载的音频流

> **输出原则**：final.md 仅包含 AI 提炼后的知识点（摘要/亮点/思考/术语/评分/图谱/闪卡/章节总结），**不含原始全文转录**，以控制输出体积和 API 成本。

### 步骤 3：读取提取结果

从 `summary.md` 解析：`title`、`platform`、`author`、`duration`。如有封面图 URL 一并提取。

> 注意：原始转录仅用于 AI 分析，不进入 final.md 最终输出。
>
> **错误恢复**：如果 summary.md 不存在或格式错误，检查：
> 1. `transcript.txt` 是否存在（至少要有转录）
> 2. `metadata.json`（playwright 方式产生的元数据）
> 3. 从这些来源手动构建 summary.md

### 步骤 4：AI 综合分析（Map → Reduce → Verify）

> **Map-Reduce 架构**：先分段提取 → 再合并验证。相比单轮输出，大幅降低"丢失中间"和幻觉风险。
>
> ⚠️ 完整提示词已外移至 `references/prompts.md`。执行时按以下流程调用：
>
> 1. **Map** — 将转录切分为若干段落（每段 2-5 分钟），对每段独立调用 Map prompt 提取原子知识点
> 2. **Reduce** — 汇总所有段落的提取结果：去重 → 矛盾消解 → 主题分组 → 置信度过滤 → 生成 JSON
> 3. **Verify** — 本地逐项核对 `evidence` 是否在原转录中出现；无证据的亮点、术语、章节、闪卡和深度问题不进入最终 Markdown

**风格适配**（在 Map 阶段应用）：
| 用户输入 | 效果 |
|---------|------|
| 含"简单点" | 章节缩至 30-80 字，类比增多，术语减少 |
| 含"详细点" | 章节扩至 100-150 字，highlights 增至 8-10 条 |
| 默认 | 平衡模式 |

### 步骤 5：知识图谱（语义关联）

> 从当前内容中提取 3-5 个**核心概念词**（如"Transformer""Self-Attention"），然后扫描 `learn-output/` 下历史条目的 `tags` 和 `final.md` 标题，匹配规则：
>
> - 核心概念词 ∩ 历史条目 tags 有交集 → 关联
> - 核心概念词 出现在历史条目标题中 → 关联
>
> 最多 5 条关联。输出 JSON：
> `[{"title": "相关笔记标题", "tag": "匹配标签/概念词", "url": ""}, ...]`

**质量**：关联是否合理且有信息量？若完全无关联，留空数组。

### 第6步：组装增强 Markdown（v3.6）

```bash
python scripts/assemble_md.py \
  --title "<标题>" --url "<链接>" --platform "<平台>" \
  --summary "<AI总结文本>" \
  --highlights '<亮点JSON>' \
  --chapters '<章节JSON>' \
  --out "learn-output/<slug>/final.md"
```

> 完整组装命令参数和 Markdown 模板见 [references/output-format.md](references/output-format.md)

### 第7步：导入知识库

```bash
python scripts/kb_router.py --file "learn-output/<slug>/final.md"
```

默认导入 Obsidian（仅复制 Markdown 与关键帧/资产，保持相对链接；不复制 HTML、转录、元数据和媒体）；未配置 Obsidian 时回退思源，再保留本地任务工件。Obsidian 笔记保存为 `<Vault>/learn/<YYYY>/<YYYY-MM>/<platform>/<title>--<task_id>/<title>.md`；成功导入后默认清理 `learn-output/_tasks/<task_id>/`，传入 `--keep-local` 可保留该任务工件。
强制指定目标：`python scripts/kb_router.py --file "..." --force obsidian`

> **导入前验证**：
> 1. 检查目标知识库 API 是否可达（思源 → `curl :6806/api/system/version`）
> 2. 检查 API token 是否配置（环境变量或 `.env`）
> 3. 如果目标不可达，自动降级到下一个候选或本地保存
> 4. 导入后验证文档是否在知识库中可见

### 任务与恢复

每个任务在 `learn-output/_tasks/<task_id>/` 保存 `task.json`、`source.json`、`artifacts.json`、`analysis.json` 和媒体工件；全局任务账本为 `learn-output/.learn/tasks.sqlite3`。任务在媒体阶段后失败时，重试会复用已有 `summary.md`，不重复下载或转写。成功导入并清理工件后，账本会保留来源 URL 和最终 Vault 路径，不会重建任务目录。

### 第8步：更新自进化状态

```python
# 更新 .skill_state.json（路径: $LEARN_OUTPUT/.skill_state.json 或 ./learn-output/.skill_state.json）
state = load_state()
state.stats.total_extractions += 1
state.stats.successful += 1  # or failed
state.platform_memory[platform] = {
    "last_success_method": method_used,
    "yt-dlp_cookie_issues": cookie_had_issues,
    "last_success": datetime.now().isoformat()
}
state.last_check = datetime.now().isoformat()
save_state(state)
```

### 第9步：汇报结果

```
✅ 学习完成 | 📄 {title} | 🏷 {category} | ⭐ {rating} | 🃏 {count}张
📥 {import_target} | 🧭 {related}条关联
⚙ 提取方式: {method} | 🟡 降级项: {degraded_list} | ⏱ 耗时: {time}
💾 本地路径: {path}
```

> **降级/受限提示**：如果以降级模式运行，在汇报中明确标注 🟡 降级项及安装建议：
> ```
> 🟡 本次以降级模式运行：
>    - 缺 tesseract → 无 OCR 文本提取
>    - 缺 scenedetect → 无关键帧截图
>    安装命令: winget install UB-Mannheim.TesseractOCR && pip install scenedetect
> ```

---

## 配置

参考 `.env.example`（技能目录下）。无需 `.env` 即可作为 AI 技能使用（分类/闪卡/总结由模型在线完成）。

### 推荐环境

为获得最佳体验，建议安装：
```bash
# 核心（必要）
pip install yt-dlp faster-whisper
winget install Gyan.FFmpeg

# 深度模式增强（推荐）
pip install scenedetect playwright paddleocr
playwright install chromium

# Cookie 提取（可选）
pip install browser_cookie3
```

## 参考文档

| 文档 | 内容 | 何时读取 |
|------|------|---------|
| `references/platforms.md` | 各平台提取详情、降级策略 | 特定平台提取出错时 |
| `references/siyuan-api.md` | 思源 API 参考 | 思源导入失败时 |
| `references/troubleshooting.md` | 常见错误排查 | 任何步骤出错时 |
| `references/self-evolution.md` | 自进化引擎详细说明 | 理解状态持久化机制时 |
