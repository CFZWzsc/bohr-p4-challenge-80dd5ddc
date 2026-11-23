# 题面要求逐条落地

本文件把 `challenge-80dd5ddc` 的题面要求映射到本 Skill 的具体字段与行为，便于评审逐项核对。正式依据是题面原文与平台案例输入；本文件不是平台评分结果。

## 1. 题面四步操作

| 题面要求 | 本 Skill 的落地 |
|-|-|
| 盘点输入文件、目录和权限 | `index[]`：相对路径、扩展名、字节、字符、sha256、编码、抽取器、`permissions.readable/mode`、`skipped[]` |
| 按规则组织资料并维护元数据/版本关系 | `versions[]`：同目录同主干的年份/版本标签分组；`duplicates[]`：sha256 重复；`index[]` 的 `years`、`version_label`、`title` |
| 输出可检索、可交接的清单或知识结构 | `index[]` + `supporting_passages[]` + `citations[]`；`result` 聚合对象可直接交接 |
| 记录跳过、失败、冲突和恢复方式 | `skipped[]`、`errors[]`、`conflicts[]`、`needs_human_confirmation[]`；不把未完成写成完成 |

## 2. 五个突破方向

| 方向 | 本 Skill 的做法 | 对应字段 |
|-|-|-|
| 多文件检索 | 递归遍历、去重、分块、tf-idf 跨文件召回 | `index`、`supporting_passages` |
| 带来源引用的问答 | 答案只由原文片段拼接，每段附 `[S#]` | `answers[].answer`、`citations` |
| 证据回链 | 文件 + 行号 + 字符区间 + 片段 + 片段哈希 | `citations[].line_start`、`char_start/char_end`、`quote_sha256` |
| 不确定性提示 | 无依据、低分、冲突、不可读、PDF 限制分级记录 | `evidence_gaps`、`conflicts`、`uncertainty` |
| 目录/元数据/版本管理 | 清单、哈希、年份、版本标签、重复识别、许可 | `index`、`versions`、`duplicates` |

## 3. 交付材料要求

| 材料 | 本包中的位置 |
|-|-|
| `SKILL.md`（用途、适用条件、调用方式、输入输出、异常处理） | 根目录 `SKILL.md` |
| 运行必需的脚本与资源 | `scripts/sk_entry.py`、`scripts/run_skill.py`、`assets/policy.json` |
| 使用与方法说明 | `SKILL.md`、`references/method.md`、`references/evidence-discipline.md` |
| 最小调用示例 | `examples/demo-case/`、`examples/quickstart.md` |

## 4. 运行输出三段要求

| 题面段落 | 字段 | 完成标准 |
|-|-|-|
| 资料结果 | `index`、`versions`、`duplicates`、`answers` | 与输入文件和题目规则一一对应 |
| 操作证据 | `evidence`、`citations`、`stats` | 含哈希、来源、权限、变更记录，可复跑核对 |
| 失败与恢复 | `skipped`、`errors`、`conflicts`、`needs_human_confirmation` | 跳过/冲突/无权限/重复都有记录 |

## 5. 平台运行约束

- `result.json` 必须含全部原始 `output_contract` 键与 `case_id`：由 `contract_notes` 与 `contract_extras.mapping` 逐键证明。
- 不提交预制答案：`examples/demo-case` 是合成示例，运行结果不冒充正式案例。
- 不编造软件状态或科学数据：无文本层 PDF、不可读文件、零命中都如实记录。
- 资源限制：文本文件 ≤50 个、单文件 ≤500 KB、总计 ≤2 MB、无符号链接。本包实际文件数与大小见 `examples/quickstart.md` 的自检命令。
