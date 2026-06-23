# 思源笔记 API 参考

> `kb_router.py` 使用的思源 API 接口说明。`kb_router.py` 自动检测已安装知识库，思源优先。

## 基础信息

| 项目 | 值 |
|------|-----|
| 默认地址 | `http://127.0.0.1:6806` |
| 认证方式 | `Authorization: Token <token>` |
| Token 配置 | `.env`（技能根目录）中的 `SIYUAN_TOKEN` |
| 消息格式 | JSON (POST) |

## 核心 API

### 1. 检查服务状态

```
GET /api/system/version
```

无需认证。用于检测思源是否运行。

**返回示例**：
```json
{"code": 0, "data": "3.1.20"}
```

### 2. 创建文档（Markdown 导入）

```
POST /api/filetree/createDocWithMd
Authorization: Token <token>
Content-Type: application/json
```

**请求体**：
```json
{
    "notebook": "学习",
    "path": "/学习/2024-06-21",
    "markdown": "# 标题\n\n内容..."
}
```

| 字段 | 说明 |
|------|------|
| `notebook` | 笔记本 ID 或名称（如"学习"） |
| `path` | 文档路径，以 `/` 分隔。父目录不存在时自动创建 |
| `markdown` | Markdown 格式文档内容 |

**返回示例**：
```json
{
    "code": 0,
    "msg": "",
    "data": {
        "id": "20240621123456-abc123"
    }
}
```

### 3. 错误码

| code | 说明 | 处理 |
|------|------|------|
| 0 | 成功 | — |
| -1 | 通用错误 | 检查 msg 字段 |
| 404 | 笔记本不存在 | 在思源中创建对应笔记本 |
| 401 | Token 错误 | 检查 `SIYUAN_TOKEN` 配置 |

## 自动启动逻辑

`kb_router.py` 的 `_ensure_siyuan_running()` 函数执行以下逻辑：

```
1. GET /api/system/version (timeout=3s)
   ├─ 成功 → 已运行，返回 True
   └─ 失败 → 进入步骤 2

2. 查找 exe（按顺序）：
   ├─ D:\Program Files\siyuan\SiYuan.exe
   ├─ C:\Program Files\siyuan\SiYuan.exe
   └─ D:\SiYuan\SiYuan.exe
   ├─ 未找到 → 返回 False
   └─ 找到 → 进入步骤 3

3. 启动进程（detached, CREATE_NO_WINDOW）
   └─ 轮询等待最多 15 秒
      ├─ GET /api/system/version 成功 → 返回 True
      └─ 超时 → 返回 False
```

## 笔记本结构

当前使用结构（在思源中）：

```
学习/
├── 2024-06-19/
│   ├── <视频标题1>
│   └── <视频标题2>
├── 2024-06-20/
│   └── ...
└── ...
```

## 备选导入目标

思源不可用时，导入降级链：

1. **思源** (优先) — 自动启动、导入
2. **Obsidian** (备选) — 复制到 `OBSIDIAN_VAULT/learn/` 目录
3. **本地 Markdown** (兜底) — 保存到 `learn-output/` 目录
