---
name: research-kb-evidence-qa
description: Use when a research-library case asks a question over a local multi-file knowledge base and requires sourced answers, passage back-links, and conflict or gap reporting; runs scripts/run_skill.py for a deterministic extractive result.json that keeps case_id and every output_contract field, with honest status.
---

# 科研知识库问答（带来源与缺证判断）

## 用途与适用条件

在「知识库已在本地、回答问题必须逐句有出处」的任务中使用：多文件检索、带来源引用的问答、证据回链、不确定性提示。输入为 `/input/case.json`、可选 `/input/task.md` 与文件集合。

只做**抽取式回答**：答案由原文片段组成，不添加知识库外的论断。

不适用：开放网络检索、论文精读综述、需要推理出知识库未记载内容的生成式回答。

## 输入

- `case.json`：`case_id`、`output_contract`；问题在 `question`、`query`、`prompt`、`task` 或 `questions` 数组。
- `task.md`：可含 `Question:` / `问题：` 行。
- 材料：`input_dir`、`materials`、`files`、`path`；回退 `/input`。
- 输出：`/app/output/result.json`（`--out` 与 `--output` 等价）；工作目录 `/app/work`。

## 处理流程

1. **范围界定**：记录纳入/未纳入的文件与原因；非文本格式与无文本层 PDF 进入 `skipped`。
2. **分块与索引**：按空行分段，超长段 1000 字符切分，保留字符偏移与最近章节标题。
3. **召回**：查询与段落做 ASCII 词 + CJK 单字/二元组；tf-idf 排序取前 6 段；低于阈值即判为证据不足。
4. **答案组装**：答案只由最高分段落中的原句拼接，每句附 `[S1]` 式引用；不给推断性结论。
5. **证据回链**：每条引用含 `file`、`section`、`page`（无可靠页码时为 `null`）、`char_start`、`char_end`、`quote`。
6. **缺证与冲突**：查询词在语料中零命中写入 `evidence_gaps`；同一关键词的多段证据出现不同数值时写入 `conflicts`，原文并列，不取平均、不做裁决。
7. **确定性**：所有排序带稳定次级键，不使用随机数与时间戳。

## 输出契约

| 字段 | 含义 |
|-|-|
| `case_id` | 与输入一致，不被合同字段覆盖 |
| `output_contract` 各字段 | 命中别名时填真实值；否则 `null` 并在 `contract_notes` 说明 |
| `status` | `success` / `partial` / `insufficient_input` / `failed` |
| `result` | `answer`、`citations`、`supporting_passages`、`evidence_gaps`、`conflicts`、`index`、`chunks` |
| `evidence` | 问题、检索参数、文件哈希、`source_mutation=none` |
| `uncertainty` | 词法召回边界、PDF 页码限制、证据不足说明 |
| `needs_human_confirmation` | 无法回答或证据冲突项（调用 Agent 补齐）：`item`、`locator`（文件+字符区间或 `null`）、`reason` |
| `errors` / `stats` | 真实错误与计数 |

## 异常处理

| 情况 | 处置 | 状态 |
|-|-|-|
| `case.json` 缺失/非法 | 空结果 + 错误 | `failed` |
| 知识库为空 | 明确说明无材料 | `insufficient_input` |
| 无问题 | 只返回索引，`confidence=no_question` | `partial` |
| 零命中 | 回答「知识库中没有依据」，列出缺口 | `partial` |
| 低分命中 | 标注 `low_confidence`，不写成确定结论 | `partial` |
| 多来源数值冲突 | 原文并列展示，标注 `conflicts` | `partial` |
| PDF 无文本层 | `skipped`，不伪造内容 | `partial` |
| 输出目录不存在 | 自动创建 | 原状态 |

## 限制

- 词法检索会漏掉同义改写；`uncertainty` 必须保留此说明。
- 不做跨语言翻译、不做单位换算、不做因果推断。
- PDF 抽取不保证页码与阅读顺序，引用页码为 `null`。

## 最小调用示例（示例，非官方案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

示意输入 `{"case_id":"synthetic-demo","output_contract":{"answer":"string","citations":"array"},"question":"what buffer was used"}`；示意输出保留 `case_id`、`answer`、`citations`、`status`，无材料时为 `insufficient_input`。仅为接口示例。

## 交付与自检

1. 先运行 `python scripts/run_skill.py`（默认 `/input/case.json` → `/app/output/result.json`；`--case`、`--out`、`--output` 等价）。脚本正常结束恒以退出码 0 返回，失败类别只看 `status` 与 `errors`。
2. 脚本只给抽取式片段；调用 Agent 必须针对题面每个子问题写出完整 `answer`，逐句附 `citations` 中的 `[S#]` 标号，并补齐 `supporting_passages`。知识库无依据的部分写入 `evidence_gaps` 与 `needs_human_confirmation`（`item/locator/reason`），不得留空、`pending` 或用泛泛表述替代。
3. 覆盖全部输入条目：每个问题、每份纳入文件都要有对应记录；跳过的文件在 `skipped` 说明原因，不静默丢弃。
4. 自检：`case_id` 与输入一致；`output_contract` 每字段存在；每条引用可回到具体文件与字符区间；数值与原文一致；不编造知识库外事实，不声称平台评分或官方案例结果。
