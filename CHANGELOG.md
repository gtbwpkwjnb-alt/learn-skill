# Changelog

All notable changes to the learn skill.

---

## [5.6.0] - 2026-07-25

### Added
- `--relearn` creates a distinct task batch and bypasses URL deduplication for an intentional fresh extraction.
- `--finalize-task` with `--final-markdown` records the host-produced learning card and optional Vault copy as the completed result.
- `awaiting_host_analysis` task stage prevents media-only work from being presented as a completed learning result.

### Fixed
- `--out` now binds the registry and progress files to the requested output root instead of reading the default output registry.
- Playwright success after a Douyin Cookie restriction is reported explicitly in the extraction log.

---

## [5.5.0] - 2026-07-25

### Breaking
- Removed the external model API integration, credentials, endpoints, retries, budgets, and call logs.
- Removed legacy standalone classification and flashcard API scripts.
- The host agent's active session model is now the only semantic analysis path.

### Security
- `.env` loading is restricted to an explicit non-model allowlist; unknown model credentials are ignored.

---

## [5.4.1] - 2026-07-25

### Changed
- Replaced product-specific agent wording with the generic current agent/current session model contract.
- Clarified that the skill is model-agnostic and must use the host agent's active model without requiring an external API.

## [5.4.0] - 2026-07-25

### Added
- Host agent's active session model as the default semantic analysis layer; external LLM APIs are opt-in only.
- Source-first, planner-evidence-publisher, modular analysis, and chapter-level output rules.
- Structured output fields for entities, tools and reasons, workflow steps, opportunity signals, metrics, actions, and evidence gaps.
- Topic-and-date Markdown naming and duplicate-date protection during Obsidian import.
- Python 3.14 preferred runtime memory with `py -3.14` fallback.

### Changed
- Video learning notes must cover people, mechanisms, tools, reasons, workflow, methodology, metrics, reuse actions, and evidence boundaries.
- README, prompts, output format, and troubleshooting now match the agent-native workflow.

### Fixed
- Prevented default Python 3.11 from being treated as the learn runtime when dependencies are installed under Python 3.14.
- Prevented final notes from stopping at transcript/summary artifacts without a completed Markdown output.

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
