# AI 分析提示词 v5.4.0

> zhixi-learn AI 综合分析的完整提示词（Map-Reduce-Verify 三段式）。参见 SKILL.md「步骤 4」。

---

## 4a. Map — 分段提取

将转录按逻辑切分为若干段落（每段约 2-5 分钟 / 500-1500 token）。对每段独立执行提取：

> 分析以下转录段落，提取其中的**原子知识点**（每条只含一个独立事实）。
>
> 对每个知识点输出：
> - `claim`: 知识点陈述（一句话，不超过 30 字）
> - `evidence_quote`: 转录中的**原句引用**（逐字，不可改写）
> - `timestamp`: 该句在视频中的时间戳（如 `[MM:SS]`）
> - `confidence`: 置信度 (`"high"` = 原文明确陈述 / `"medium"` = 原文直接隐含 / `"low"` = 推测但合理)
> - `topic`: 所属主题标签（如 `"架构"`、`"概念"`、`"案例"`）
> - `entity_type`: `person` / `product` / `organization` / `tool` / `concept` / `metric` / `unknown`
> - `role`: 实体在内容中的角色或用途；工具必须说明解决的问题
>
> **严禁**：
> - ❌ 合并多个事实到一条 `claim`
> - ❌ 添加转录中不存在的信息
> - ❌ 改写 `evidence_quote` —— 必须是原文逐字引用
> - ❌ 跳过时间戳
>
> 转录段落：
> ```
> {segment_text}
> ```
>
> 输出 JSON 数组：`[{"claim": "...", "evidence_quote": "...", "timestamp": "MM:SS", "confidence": "high", "topic": "..."}]`

---

## 4b. Reduce — 合并验证

将所有段落提取的知识点汇总，执行：

1. **去重** — 同一条知识出现在多段的，保留 evidence_quote 最完整的那条
2. **矛盾消解** — 若不同段落有矛盾陈述，在最终输出中标注双方，不改写
3. **主题分组** — 按 `topic` 将知识点聚类
4. **置信度过滤** — 移除 `confidence: "low"` 且无其他段落佐证的知识点
5. **生成最终结构化输出**

最终输出格式：

```json
{
  "category": "主题分类（具体，如'机器学习'非'科技'）",
  "tags": ["标签1", "标签2", "标签3"],
  "one_sentence_summary": "一句话说明内容主体、核心动作和结果，不超过 40 字",
  "main_points": ["5-10 条核心事实；每条包含主体、动作、原因或结果"],
  "takeaways": ["3-5 条可迁移结论；必须区分原文事实与推导"],
  "summary": "3-5句精华摘要，每句覆盖一个核心论点，有细节有证据",

  "entities": [
    {"name": "主体或工具名称", "type": "person|product|tool|organization|concept|metric", "role": "在内容中的作用", "evidence": "原文证据"}
  ],

  "tools": [
    {"name": "工具名", "purpose": "用于什么", "why": "为什么选择/解决什么约束", "evidence": "原文证据"}
  ],

  "workflow_steps": [
    {"order": 1, "time": "MM:SS", "step": "做了什么", "why": "为什么这一步在此时做", "result": "得到什么", "evidence": "原文证据"}
  ],

  "opportunity_method": [
    {"signal": "需求/商机信号", "observation": "观察到什么", "inference_boundary": "能推断什么、不能推断什么", "evidence": "原文证据"}
  ],

  "metrics": [
    {"name": "指标", "value": "数值", "meaning": "内容赋予的含义", "verification": "verified|source_claim|unavailable", "evidence": "原文证据"}
  ],

  "action_checklist": ["将内容转化为 3-7 条可执行动作；每条说明前置条件或限制"],
  "evidence_gaps": ["未提供的来源、人物身份、工具名、数据或关键上下文"],

  "highlights": [
    {"time": "MM:SS", "description": "核心要点 + 简短机制说明（25-50字）",
     "evidence": "原文支撑句"},
    {"time": "MM:SS", "description": "另一要点 + 案例解释",
     "evidence": "原文支撑句"}
  ],

  "deep_thinking": [
    {"q": "从用户真实困惑出发的问题（为什么/如果…会怎样/与X对比）",
     "a": "结合原文+合理推理的深度答案",
     "evidence": "推理所依据的原句(s)"}
  ],

  "glossary": [
    {"term": "关键术语",
     "definition": "简明定义",
     "evidence": "原文中出现该术语的典型例句"}
  ],

  "rating": {"info_density": 4.0, "practicality": 4.5, "clarity": 4.0},

  "flashcards": [
    {"q": "测试关键概念的问题",
     "a": "信息量大但简洁的答案"}
  ],

  "chapters": [
    {"time": "MM:SS", "title": "章节标题（前加 emoji 🧩⚡⭐🔄⏳ 更佳）",
     "screenshot": "frames/scene_NNN.jpg",
     "summary": "一段完整解释（50-150字），包含核心论点、作者使用的类比/案例、该部分在整体中的定位"}
  ]
}
```

---

## 4c. Verify — 二次验证

对上述输出逐字段执行验证。当前实现优先使用本地确定性校验：将每条 `evidence` 去空白后与完整原转录逐字匹配；无法匹配的列表项不进入最终 Markdown。

> 验证以下 AI 提取结果是否准确。对每条 `highlights`、`glossary` 条目逐一检查：
>
> 1. **原文支持**：`evidence` 是否在转录或关键帧中找到？✅/❌
> 2. **正确性**：`claim` / `definition` 是否与原文一致？✅/❌
> 3. **完整性**：人物、工具、步骤、原因、方法论、指标是否覆盖？✅/❌
> 4. **边界**：是否将 `source_claim` 错写成独立核验事实，或把推导伪装成原文？✅/❌
> 5. **可用性**：是否能从章节、行动清单和实体名称中复用这份笔记？✅/❌
>
> 任一字段标记 ❌ → 从最终输出移除，并在任务验证记录中计数。不要为了填满版面而保留无来源内容。
