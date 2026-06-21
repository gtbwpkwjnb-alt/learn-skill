# 平台提取参考

> 各平台的提取方法、Cookie 配置、降级策略和已知限制。

## 目录

- [抖音 / TikTok](#douyin)
- [B站 (Bilibili)](#bilibili)
- [播客 / RSS](#podcast)
- [本地音视频文件](#local)
- [微信公众号](#wechat)
- [小红书 (XHS)](#xiaohongshu)
- [YouTube](#youtube)

---

## 抖音 / TikTok {#douyin}

### 提取方法

**方法 A（推荐）**：调用 tiktok-extract Skill
```
使用 Skill 工具调用 "tiktok-extract"，传入链接
```

**方法 B**：直接脚本
```bash
C:\Python312\python.exe C:\Users\Administrator\ZCodeProject\tools\douyin2md.py "<链接>" --out C:\Users\Administrator\ZCodeProject\learn-output
```

### 支持的链接格式

- `https://v.douyin.com/xxxxx/` — 短链接（最常见）
- `https://www.douyin.com/video/xxxxx` — 视频页
- `https://www.iesdouyin.com/share/video/xxxxx` — 分享链接
- `https://www.douyin.com/user/xxx?modal_id=xxxxx` — 用户页视频

### 输出

提取完成后，在 `learn-output/<id>/` 目录下：
- `summary.md` — 元数据 + 转录文本
- `video.mp4` — 无水印视频
- `frames/` — 关键帧截图（如果使用 `--frames`）

### 限制

- 需要有效的网络环境（B站通即可访问抖音）
- 部分私密/删除视频无法提取

---

## B站 (Bilibili) {#bilibili}

### 提取方法

统一入口：
```bash
C:\Python312\python.exe C:\Users\Administrator\ZCodeProject\tools\learn.py "https://www.bilibili.com/video/BVxxxxxx"
```

### 提取流程（两阶段）

**阶段 1：字幕下载**
- 使用 yt-dlp 下载官方字幕（优先中文 `zh-Hans, zh-CN, zh`）
- 自动下载 AI 生成字幕作为兜底（`ai-zh`）
- 字幕格式：SRT

**阶段 2：Whisper 兜底**
- 若无字幕，使用 hearsay whisper 模型进行音频转写
- 命令：`python -m hearsay ingest "<url>" -o <dir>/hearsay.md --transcribe`

### Cookie 配置（获取完整字幕）

B站部分视频字幕需要登录 Cookie 才能获取。在 `tools/.env` 中配置：

```env
# 方式1：完整 Cookie 字符串
BILI_COOKIE="SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx; ..."

# 方式2：仅 SESSDATA
BILI_SESSDATA="xxx"
```

### 已知限制

- 会员专享视频无法提取
- Cookie 过期需重新获取
- 极长视频（>2h）字幕下载可能超时

---

## 播客 / RSS {#podcast}

### 提取方法

使用 hearsay：
```bash
C:\Python312\python.exe -m hearsay ingest "<播客RSS链接>" -o C:\Users\Administrator\ZCodeProject\learn-output\podcast.md
```

### 支持的格式

- RSS 2.0 / Atom feed
- 标准播客 XML
- 直接音频链接（.mp3, .m4a）
- BBC Sounds、Apple Podcasts 链接

### 输出

- `podcast.md` — 标题、描述、章节、转录文本

---

## 本地音视频文件 {#local}

### 提取方法

```bash
C:\Python312\python.exe -m hearsay ingest "<文件路径>" -o C:\Users\Administrator\ZCodeProject\learn-output\local.md --transcribe
```

### 支持的格式

- 视频：`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`
- 音频：`.mp3`, `.wav`, `.flac`, `.m4a`

### 前提条件

- ffmpeg 已安装且可在 PATH 中找到
- 默认路径：`C:\Tools\ffmpeg-8.1.1-essentials_build\bin`

### 时间估算

- 1小时音频 → 约 5-10 分钟（取决于硬件）

---

## 微信公众号 {#wechat}

### 前置条件

- Edge 浏览器（Chromium 内核）
- feedgrab 工具已配置

### 提取方法

通过 Edge 浏览器使用 feedgrab 提取。需要浏览器 User Agent 配置。

详见项目 `.env` 中的 feedgrab 配置。

### 已知限制

- 部分公众号文章需微信客户端内打开
- 企业微信文章可能受限
- 图片/富媒体内容可能丢失

---

## 小红书 (XHS) {#xiaohongshu}

### 前置条件

- Edge 浏览器
- feedgrab 工具

### 已知限制

- 小红书反爬较强，成功率不高
- 建议优先使用其他平台

---

## YouTube {#youtube}

### 国内状态

**YouTube 在中国大陆被 GFW 封锁**，直连不可用。

### 可用方案

1. **代理**：配置 HTTP/HTTPS 代理后，yt-dlp 可正常工作
2. **手动下载**：用代理下载视频或字幕文件，然后作为本地文件处理
3. **B站搬运**：很多 YouTube 视频在 B站有搬运版

### 代理配置

```env
# 在 tools/.env 中设置
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```
