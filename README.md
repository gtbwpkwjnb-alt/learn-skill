# Learn Skill / 学习技能 v3.4

> 一条链接 → 全自动管线：采集 → AI分析 → AI总结 → Markdown → 知识库

## 🚀 Quick Install / 快速安装

```bash
git clone git@github.com:gtbwpkwjnb-alt/learn-skill.git
cd learn-skill
pip install yt-dlp faster-whisper scenedetect opencv-python pytesseract Pillow hearsay
```

### 系统依赖

| 工具 | 安装 |
|------|------|
| ffmpeg | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` |
| tesseract (可选，深度OCR) | `winget install UB-Mannheim.TesseractOCR` / `brew install tesseract` / `apt install tesseract-ocr` |

## ✨ Features / 特性

- **双速自适应**：播客/本地mp3 → 快速（~30s）；抖音/B站/YouTube → 深度（含关键帧+OCR，~3-10min）
- **8 平台支持**：抖音 · TikTok · B站 · YouTube · 播客 · 微信 · 小红书 · 本地文件
- **自包含深度提取**：内置 `extract_douyin.py`，无需外部技能
- **AI 全自动**：分类 + 闪卡 + 总结，由 AI 模型内联完成，零 API 配置
- **多知识库导入**：自动检测思源/Obsidian/Logseq/Joplin/Trilium，本地保存兜底

## 🎯 Usage / 使用

### 作为 AI 技能

```
学习 https://v.douyin.com/xxxxx/       ← 深度模式（自动）
学习 快速 https://example.com/podcast  ← 强制快速
学习一下这个视频 https://b23.tv/xxx     ← 宽容触发
```

### 独立脚本

```bash
# 深度提取（抖音/TikTok）
python scripts/extract_douyin.py <url> --frames --out ./learn-output

# 组装 Markdown
python scripts/assemble_md.py \
  --title "标题" --url "<链接>" --platform "bilibili" \
  --transcript-file transcript.txt \
  --category "分类" --tags "AI,教程" \
  --summary "AI 总结文本" \
  --out final.md

# 导入知识库（自动检测）
python scripts/kb_router.py --file final.md
python scripts/kb_router.py --file final.md --force obsidian
```

## 📁 Structure / 目录结构

```
learn-skill/
├── SKILL.md                    # 技能定义（177行）
├── scripts/
│   ├── extract_douyin.py      # 深度提取管线（抖音/TikTok）
│   ├── kb_router.py           # 知识库自动检测路由
│   ├── assemble_md.py         # Markdown 组装
│   └── legacy/                # 旧版独立脚本
├── references/
│   ├── platforms.md           # 平台提取详情
│   ├── siyuan-api.md          # 思源 API 参考
│   └── troubleshooting.md     # 故障排查
├── .env.example               # 配置模板
└── README.md
```

## 🔧 Config / 配置

复制 `.env.example` 为 `.env`，按需填写（所有字段可选，AI 分类/闪卡/总结默认由模型内联完成）。

关键变量：`SIYUAN_TOKEN`（思源导入）、`OBSIDIAN_VAULT`（Obsidian 路径）、`BILI_COOKIE`（B站字幕）。

## 📄 License

MIT
