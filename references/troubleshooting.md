# 故障排查

> learn skill 常见问题及解决方案。

## 目录

- [环境问题](#环境问题)
- [提取问题](#提取问题)
- [AI 分类/闪卡问题](#ai-分类闪卡问题)
- [思源导入问题](#思源导入问题)
- [常见错误码](#常见错误码)

---

## 环境问题

### ffmpeg 未找到

**症状**：`❌ ffmpeg 未找到` 或 `'ffmpeg' is not recognized`

**解决**：
```bash
# 确认安装
dir "C:\Tools\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"

# 如未安装，下载安装
# https://www.gyan.dev/ffmpeg/builds/ → ffmpeg-release-essentials.zip
# 解压到 C:\Tools\
```

### DeepSeek API 密钥未配置

**症状**：`⚠ DEEPSEEK_API_KEY 未配置`

**解决**：在 `C:\Users\Administrator\ZCodeProject\tools\.env` 添加：
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### 思源 Token 未配置

**症状**：思源导入 401 错误

**解决**：
1. 打开思源 → 设置 → 关于 → API Token
2. 复制 Token 到 `.env`：`SIYUAN_TOKEN=xxxxxxxx`

---

## 提取问题

### B站字幕下载失败

**症状**：yt-dlp 报错，无字幕文件生成

**排查步骤**：
1. 确认 Cookie 有效 — 新开浏览器登录 B站，复制 Cookie 到 `.env`
2. 确认视频存在 — 手动打开链接确认视频可播放
3. 尝试 AI 字幕 — 在 B站网页端开启 AI 字幕后重试
4. 降级到 Whisper — 脚本会自动切换到 hearsay whisper 转写

### 抖音链接无法识别

**症状**：`❌ 无法识别平台: ...`

**检查**：
- 确认链接包含 `douyin.com/video/`、`v.douyin.com/` 或 `iesdouyin.com/share/video/`
- 确认不是 `tiktok.com` 链接（国际版需要不同处理）

### hearsay 转写超时

**症状**：hearsay 运行超过 15 分钟未完成

**原因**：长音频 (1h+) Whisper 转写耗时长

**解决**：
- 等待完成（正常情况）
- 如超时失败，手动分成短段落处理

### YouTube 无法访问

**症状**：`❌ YouTube 在当前网络环境不可用（需代理）`

**解决**：
1. 配置代理到 `.env`：`HTTP_PROXY=http://127.0.0.1:7890`
2. 或在 B站搜索搬运视频
3. 或手动下载后作为本地文件处理

---

## AI 分类/闪卡问题

### AI 分类结果不合理

**症状**：技术视频被分类为"美食"等明显错误

**处理**：
1. 重试一次（API 偶发不稳定）
2. 手动指定分类（告知用户当前分类，让用户修正）
3. 检查转录文本是否含噪声

### 闪卡内容与原文无关

**症状**：生成的 Q&A 与视频主题不符

**处理**：
1. 丢弃当前闪卡结果
2. 用更精准的转录片断重试
3. 内容过短时跳过闪卡生成（自动检测 < 500 字）

### DeepSeek API 超时/报错

**症状**：`⚠ AI 分类请求失败: ...` 或 HTTP 5xx

**处理**：
1. 检查网络：`curl -s https://api.deepseek.com/v1/models`
2. 检查 API 余额：登录 platform.deepseek.com
3. API 不可用时跳过 AI 步骤，生成基础笔记

---

## 思源导入问题

### 思源无法启动

**症状**：`⚠ 未找到思源安装路径`

**解决**：
1. 确认安装路径在 `SIYUAN_PATHS` 列表中
2. 手动启动思源后再重试
3. 或使用 `--no-start` 跳过自动启动

### 思源启动后导入仍失败

**症状**：思源已在运行，但 API 返回错误

**排查**：
1. 确认 Token 配置正确：`curl http://127.0.0.1:6806/api/system/version`
2. 确认笔记本"学习"存在
3. 查看思源日志（设置 → 关于 → 日志）

### 降级到本地保存

思源完全不可用时，笔记自动保存到：
```
C:\Users\Administrator\ZCodeProject\learn-output\<slug>\final.md
```

---

## 常见错误码

| 错误 | 含义 | 解决 |
|------|------|------|
| `❌ 无法识别平台` | 链接格式不支持 | 检查链接是否完整，确认平台是否在支持列表 |
| `❌ 内容提取失败` | 提取步骤未生成输出 | 检查网络、Cookie、工具安装 |
| `⚠ AI 分类失败` | DeepSeek API 调用异常 | 检查 API Key 和网络 |
| `⚠ 闪卡生成失败` | DeepSeek API 调用异常或内容过短 | 短内容自动跳过，API 问题检查配置 |
| `⚠ 思源 API 错误` | 思源导入接口返回错误 | 检查 Token 和笔记本配置 |
| `⏭ 跳过(已处理)` | 重复链接 | 正常行为，去重机制生效 |
