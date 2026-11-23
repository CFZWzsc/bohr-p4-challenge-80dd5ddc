---
name: research-kb-evidence-qa
description: Use when a research-library case asks a question over a local multi-file knowledge base and requires sourced answers, passage back-links, conflict or gap reporting; run scripts/run_skill.py for a deterministic extractive result.json.
---

# 科研知识库问答（带来源与缺证判断）

## 用途与适用条件

在「知识库已在本地，回答必须逐句有出处」的任务中使用：多文件检索、带来源引用的问答、证据回链、不确定性提示。输入为 `/input/case.json`、可选 `/input/task.md` 与文件集合。

不适用：开放网络检索、论文精读综述、需要推理出知识库未记载内容的生成式回答。本 Skill **只做抽取式回答**：答案由原文片段组成，不添加知识库外的论断。

## 输入

- `case.json`：`case_id`、`output_contract`；问题在 `question`、`query`、`prompt`、`task` 或 `questions` 数组。
- `task.md`：可含 `Question:` / `问题：` 行。
- 材料：`input_dir`、`materials`、`files`、`path`；回退 `/input`。
- 输出：`/app/output/result.json`。

## 处理流程（对应评分维度）

1. **范围界定（任务完成度）**：记录纳入/未纳入的文件与原因；非文本格式与无文本层 PDF 进入 `skipped`。
2. **分块与索引（完整性）**：按空行分段，超长段 1000 字符切分，保留字符偏移与最近章节标题。
3. **召回（正确性）**：查询与段落做 ASCII 词 + CJK 单字/二元组；tf-idf 排序，取前 6 段；低于阈值即判为证据不足。
4. **答案组装（正确性）**：答案只由最高分段落中的原句拼接，每句附 `[S1]` 式引用；不给推断性结论。
5. **证据回链（可核验性）**：每条引用含 `file`、`section`、`page`（无可靠页码时为 `null`）、`char_start`、`char_end`、`quote`。
6. **缺证与冲突（可靠体验）**：查询词在语料中零命中写入 `evidence_gaps`；同一关键词的多段证据出现不同数值时写入 `conflicts`，不取平均、不做裁决。
7. **确定性**：所有排序带稳定次级键，不使用随机数与时间戳。

## 输出契约

| 字段 | 含义 |
|-|-|
| `case_id` | 与输入一致 |
| `output_contract` 各字段 | 命中别名时填真实值，否则 `null` + `contract_notes` |
| `status` | `success` / `partial` / `insufficient_input` / `failed` |
| `result` | `answer`、`citations`、`supporting_passages`、`evidence_gaps`、`conflicts` |
| `evidence` | 查询、检索参数、文件哈希 |
| `uncertainty` | 词法召回边界、PDF 页码限制、证据不足说明 |
| `errors` / `stats` | 真实错误与计数 |

## 异常处理表

| 情况 | 处置 | 状态 |
|-|-|-|
| case.json 缺失/非法 | 空结果 + 错误 | `failed` |
| 知识库为空 | 明确说明无材料 | `insufficient_input` |
| 无问题 | 只返回索引，`confidence=no_question` | `partial` |
| 零命中 | 回答「知识库中没有依据」，列出缺口 | `partial` |
| 低分命中 | 标注 `low_confidence`，不写成确定结论 | `partial` |
| 多来源数值冲突 | 原文并列展示，标注 `conflicts` | `partial` |
| PDF 无文本层 | `skipped`，不伪造内容 | `partial` |

## 限制

- 词法检索会漏掉同义改写；`uncertainty` 必须保留此说明。
- 不做跨语言翻译、不做单位换算、不做因果推断。
- PDF 抽取不保证页码与阅读顺序，引用页码为 `null`。

## 最小调用示例（示例，非官方案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

示意输入 `{"case_id":"synthetic-demo","output_contract":{"answer":"string","citations":"array"},"question":"what buffer was used"}`；示意输出保留 `case_id`、`answer`、`citations`、`status`，无材料时为 `insufficient_input`。仅为接口示例。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 按契约取 `success`/`partial`/`insufficient_input`/`failed`（缺输入或证据不足时用 `insufficient_input`/`partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
