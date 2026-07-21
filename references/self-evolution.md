# Self-Evolution Engine / 自进化引擎

> 跨会话状态持久化、最优路径学习、自动降级记忆功能说明。

## 概述

自进化引擎通过 `learn-output/.skill_state.json` 持久化环境状态和平台记忆，使技能在使用过程中不断优化自身行为。

## 状态文件结构

```json
{
  "skill_version": "5.2.0",
  "last_check": "2026-06-24T15:20:00",
  "env": {
    "ffmpeg": {"found": true, "version": "8.1.1"},
    "yt-dlp": {"found": true, "version": "2026.06.01"},
    "playwright": {"found": true, "version": "1.60.0"},
    "faster-whisper": {"found": true, "version": ""},
    "scenedetect": {"found": false, "last_attempt": "2026-06-24"},
    "tesseract": {"found": false, "last_attempt": "2026-06-24"},
    "browser_cookie3": {"found": false, "last_attempt": "2026-06-24"},
    "python": {"path": "/usr/bin/python3", "version": "3.14.6"}
  },
  "platform_memory": {
    "douyin": {
      "last_success_method": "playwright_intercept",
      "yt-dlp_cookie_issues": true,
      "last_fail_reason": "Fresh cookies are needed",
      "last_success": "2026-06-24T15:20:00",
      "attempts": 2,
      "failures": 1
    }
  },
  "stats": {
    "total_extractions": 3,
    "successful": 3,
    "failed": 0,
    "last_extraction": "2026-06-24T15:20:00"
  }
}
```

## 状态持久化机制

### 存储位置
- **文件**: `learn-output/.skill_state.json`
- **格式**: JSON，UTF-8 编码
- **更新时机**: 每次提取完成后自动更新

### 读取优先级
1. 检查 `learn-output/.skill_state.json`
2. 如果不存在，创建默认状态
3. 如果存在但版本低于当前 SKILL.md 版本，尝试迁移

### 缓存策略

| 缓存 | 有效期 | 原因 |
|------|--------|------|
| env 检测结果 | 1 小时 | 运行时环境稳定，无需每次检查 |
| 平台记忆 | 永久 | 持续学习优化 |
| 统计信息 | 每次更新 | 实时追踪 |

## 平台记忆路由逻辑

### 抖音（Douyin）记忆驱动决策树

```
检查 .skill_state.json 中 douyin 记忆
  ├─ 无记忆（首次）→ 按默认顺序：
  │   ├─ yt-dlp 尝试（最快）
  │   ├─ 失败 → playwright 脚本自动兜底
  │   └─ 更新记忆
  ├─ 记忆存在且 yt-dlp_cookie_issues = true：
  │   ├─ 告知用户："上次抖音因 cookie 失败，改用 playwright 方案"
  │   ├─ 直接使用 playwright 拦截（跳过 yt-dlp）
  │   └─ 更新记忆
  ├─ 记忆存在且 yt-dlp 上次成功：
  │   ├─ 先用 yt-dlp（快）
  │   └─ 失败 → 降级到 playwright
  └─ 连续失败 > 3 次：
      ├─ 主动提示："⚠ 抖音平台连续失败，建议检查网络/账号"
      └─ 仍尝试最后一次，失败则终止
```

### 通用平台路由逻辑

```
检查 .skill_state.json 中 platform 记忆
  ├─ 无记忆 → 按默认提取方法执行
  ├─ 上次成功 → 沿用上次成功的方法
  └─ 上次失败 → 尝试备选方法（如有）
```

## 环境记忆的用途

### 1. 依赖预判
```python
# 伪代码
state = load_state()
if state.env.tesseract.found == False:
    print("⚠ tesseract 未安装，跳过 OCR")
    print("  安装命令: winget install UB-Mannheim.TesseractOCR")
    # 跳过 OCR 相关步骤
```

### 2. 平台特定配置
```python
if platform == "douyin" and state.platform_memory.douyin.yt-dlp_cookie_issues:
    extraction_method = "playwright_intercept"
elif platform == "douyin":
    extraction_method = "yt-dlp"
```

### 3. 用户友好提示
```python
if state.stats.failed > 3:
    print(f"⚠ 该平台累计失败 {state.stats.failed} 次，可能存在问题")
```

## 自进化规则

### 规则 1：学习最优路径
每次成功提取后，记录使用的方法。下次同平台优先使用上次成功的方法。

### 规则 2：自动降级
如果某个依赖缺失，记录到 `env` 中。下次跳过相关功能，不再重试安装。

### 规则 3：失败追踪
连续失败 > 3 次的平台在触发时主动预警。

### 规则 4：版本兼容性
如果技能升级（version 变化），自动重置旧的状态文件并重建。

## 手动重置

如需强制重新检测环境或清除记忆：

```bash
# 删除状态文件（下次自动重建）
rm learn-output/.skill_state.json

# 或只清除特定平台记忆
# 编辑 learn-output/.skill_state.json，删除 platform_memory 中的对应项
```
