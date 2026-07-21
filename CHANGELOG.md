# Changelog

All notable changes to the learn skill.

---

## [5.2.0] - 2026-07-21

### Fixed
- 普通抖音 `/user/` 与 `share/user/` 主页现在可枚举 `/aweme/post` 分页、按 `aweme_id` 去重，并报告页面计数差异。
- Playwright 兜底现在保留作者、捕获分离音频，并在 `--frames` 模式执行关键帧和 OCR。
- `.skill_state.json`、综合依赖自检和抖音成功路径记忆已由文档契约落为真实实现。
- 最终 Markdown 默认不再嵌入全文转录；内部任务工件仍保留转录供分析与恢复。
- 修复 `douyin_playwright_extract` 测试夹具的导入问题，并将 Playwright 改为按需导入。

### Performance
- 关键帧默认均匀采样最多 60 张，可通过 `LEARN_MAX_KEYFRAMES` 调整，避免长视频 OCR 无上限增长。

## [5.1.1] - 2026-07-16

### Summary
补齐 VERSION 与 CHANGELOG 元数据，让 skills-summarize-audit 健康度体检能正常评分。本次仅添加元数据文件，未修改任何代码或行为。

### Added
- **VERSION 文件**：建立版本号 5.1.1（与 SKILL.md 标注一致）。
- **CHANGELOG.md**：本次为首版 CHANGELOG，起始版本直接锚定到 SKILL.md 内部声明的 5.1.1。

### Notes
- 历史版本（5.1.0 及更早）变更未追溯记录；后续每次实质性修改须按语义化版本追加条目。
- skill-registry.yaml 中记录的版本（4.1.0）已过期，下次审计会自动回写为 5.1.1。

---

## 维护说明

- 修改代码 → 追加新版本段（按 SemVer：major.minor.patch）
- 仅改文档/配置 → patch 版本号
- 新功能 → minor 版本号
- 破坏性变更 → major 版本号
