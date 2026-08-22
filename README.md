# 知析 zhixi-learn v5.6.0

> **Agent-Native Learning Pipeline.** Shared link or local media → link normalization → subtitle-first extraction or resilient transcription → keyframe OCR → evidence-first Map-Reduce-Verify → hierarchical knowledge card and knowledge base import.
>
> **Agent 原生学习管道。** 分享文案或本地音视频 → 短链/推广参数清洗 → 字幕优先与可恢复转写 → 关键帧 OCR → 全文 Map-Reduce-Verify → 层级化知识卡片（章节、思维导图、亮点、术语、闪卡）→ Obsidian/思源导入。

---

## 🚀 Quick Install / 快速安装

```bash
git clone git@github.com:gtbwpkwjnb-alt/learn-skill.git
cd learn-skill
pip install yt-dlp faster-whisper hearsay requests
```

### 系统依赖

| 工具 | 安装 |
|------|------|
| ffmpeg | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` |
| Python 3.10+ | `python --version` 确认 |

---

## ✨ Features / 特性

| 特性 | 说明 |
|------|------|
| 🌐 **网络自适应** | 自动检测 GFW，筛选可用平台 |
| 🔍 **8 平台支持** | 抖音 · TikTok · B站 · YouTube · 播客 · 微信 · 小红书 · 本地文件 |
| 👤 **抖音主页批量学习** | 自动枚举 `/aweme/post` 分页、按作品 ID 去重并报告页面计数差异 |
| 🔍 **中文界面 OCR** | PP-OCRv6（隔离环境）→ 旧 PaddleOCR → Tesseract |
| 🏗 **当前 Agent 证据分析** | 全文分段 Map → Reduce 汇总 → 本地证据 Verify；技能激活后使用当前 agent 的会话模型，不依赖外部模型 API |
| 📑 **层级化输出** | 章节分解 + Mermaid 思维导图 + 3段式总结 |
| 📤 **双知识库导入** | Obsidian（默认）+ 思源回退 + 本地 Markdown |
| 📦 **可恢复任务** | SQLite 任务账本 + 工件清单 + 断点续传；成功导入后默认清理本地工件 |
| 🔒 **安全边界** | 主脚本只做本地提取与证据保存，不读取或调用外部模型 API |

---

### 文件保存规则

- 处理中工件：`learn-output/_tasks/<task_id>/`，用于断点续传、转录、关键帧与分析中间结果。
- 导入 Obsidian 后的笔记：`<Vault>/learn/<主题>-<YYYY-MM-DD>.md`，仅保留 Markdown 和引用的关键帧/资产。
- 导入成功后默认清理该任务的本地工件；SQLite 账本仍保留来源链接和最终笔记路径。需要保留工件时加 `--keep-local`。

---

## 🎯 Usage / 使用

### 作为 AI 技能

```
知析 https://www.bilibili.com/video/BV1GJ411x7h7
zhixi https://v.douyin.com/xxxxx/
学习一下这个视频 https://b23.tv/xxx
```

### 命令行

```bash
# 单条处理
python zhixi-learn.py "https://www.bilibili.com/video/BV1GJ411x7h7"

# 批量处理
python zhixi-learn.py "url1" "url2" "url3"

# 抖音博主主页（自动枚举公开可访问视频）
python zhixi-learn.py "https://www.douyin.com/user/..."

# 仅提取内容（跳过 AI 分析和导入）
python zhixi-learn.py "url" --extract-only

# 预览（dry-run）
python zhixi-learn.py "url1" "url2" --dry-run

# 分享文案、短链与推广参数会自动清洗；仅预览清洗结果时：
python zhixi-learn.py "6.12 复制打开抖音，https://v.douyin.com/xxxxx/?share_token=.../" --dry-run

# 不访问网络解析短链（仍会移除推广参数）：
python zhixi-learn.py "https://b23.tv/xxxxx?spm_id_from=333" --dry-run --no-resolve-links
```

---

## 🏗 Architecture / 架构

```
URL → 🌐 Network Detect → 🔍 Platform Detect → 📥 Extract
     ↓
🧹 Text Processing → 🤖 Current Agent Analysis (current session model; no external API by default)
     ↓                    ├─ Category + Tags
     ↓                    ├─ 3-paragraph Summary (TL;DR→Detail→Implications)
     ↓                    ├─ Chapters (title + timestamp + points)
     ↓                    ├─ Highlights + Glossary + Rating
     ↓                    └─ Flashcards + Deep Questions
     ↓
📄 Hierarchical Markdown (Mermaid mindmap + all sections)
     ↓
📤 Import → Obsidian / SiYuan fallback / Local
```

### 输出示例

```markdown
# 视频标题

## 📊 快速概览
[3段层级总结]
## 🧭 内容结构
[mermaid mindmap]
## 📑 章节分解
### 📍 章节1 ⏱ 00:00 — 要点...
### 📍 章节2 ⏱ 05:30 — 要点...
## ⭐ 核心亮点
## 📚 关键术语
## 🃏 复习闪卡
## 🤔 深度思考
## 🤖 AI 分类
```

---

## 📁 Directory Structure / 目录结构

```
learn-skill/
├── zhixi-learn.py             # 主入口（知析 v4.0）
├── SKILL.md                   # 技能定义
├── scripts/
│   ├── assemble_md.py         # Markdown 组装工具
│   ├── extract_douyin.py      # 抖音/TikTok 提取管线
│   ├── kb_router.py           # 知识库自动路由
│   └── legacy/                # 旧版独立脚本
├── references/
│   ├── platforms.md           # 平台提取详情
│   ├── siyuan-api.md          # 思源 API 参考
│   └── troubleshooting.md     # 故障排查
├── .env.example               # 配置模板
└── README.md
```

---

## 🔧 Configuration / 配置

复制 `.env.example` 为 `.env`，填写必要变量：

| 变量 | 必需 | 说明 |
|------|:----:|------|
| `SIYUAN_TOKEN` | ❌ | 思源 API token（导入思源时必需） |
| `BILI_COOKIE` | ❌ | B站 Cookie（获取高质量字幕） |
| `OBSIDIAN_VAULT` | ❌ | Obsidian 库路径 |

---

## 📊 v3 → v4 升级亮点

| 改进 | v3 (learn) | v4 (zhixi-learn) |
|------|:----------:|:----------------:|
| AI 分析入口 | 外部 API 串行调用 | **当前 agent 会话模型（主脚本不调用外部模型）** |
| 章节分解 | ❌ | ✅ 带时间戳+要点 |
| 思维导图 | ❌ | ✅ Mermaid |
| 层级化总结 | ❌ | ✅ 3段式 |
| 输出模板 | 平面 | **层级化** |
| 测试覆盖 | ❌ | ✅ 35 项 pytest |
| 代码可维护性 | 单函数 200+ 行 | **7 个辅助函数** |

---

## 🚀 DeepSeek Harness 插件市场

本仓库同时是 DeepSeek Harness（dsh）技能包插件，可通过 dsh 插件系统安装：

```bash
dsh plugin --profile web add github:gtbwpkwjnb-alt/learn-skill
```

安装后重启 dsh web，技能出现在 Settings → Plugins，按需懒加载（渐进式披露）。技能包由本仓库根目录的 `SKILL.md` 提供，`cordis.patch.yml` + `index.js` 为插件外壳（只读 skill provider，无工具、无凭据、无网络请求）。

- 测试兼容版本：dsh v0.1.1-rc.2（2026-08-22）。预览期版本迭代快，若 API 变更请以官方文档为准。
- 技能格式：kebab-case 名称 + `name`/`description` frontmatter，与 dsh 技能契约一致。
- 插件外壳无 npm 依赖，可从 GitHub 直装。

---

## 📄 License

MIT
