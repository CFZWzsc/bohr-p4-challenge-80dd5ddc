---
name: research-kb-evidence-qa
description: Use when a research-library case supplies local files plus questions and asks for sourced answers, version/duplicate awareness and honest evidence gaps; runs a stdlib-only deterministic indexer over /input and writes a contract-complete /app/output/result.json.
---

# 科研知识库问答（多文件检索 / 带引用回答 / 证据回链）

## 用途

在一个**已经在本地**的科研文件集合上回答一个或多个问题，并交付可复核的证据链：

1. 递归盘点文件，输出目录/文件清单，含哈希、字节、字符数、编码、抽取器、权限与可读性。
2. 识别**重复文件**（sha256）与**版本关系**（文件名/元数据中的年份、v1/v2、revision、final 等标签）。
3. 把每个问题转成检索查询，跨文件召回段落（ASCII 词 + 中文单字/二元组，tf-idf）。
4. 用**原文片段**拼出回答，每条片段给出文件、章节、行号、字符区间、片段哈希。
5. 对没有依据的问题明确写「知识库中没有依据」，列出缺失词；对同单位数值不一致的段落并列引用、不裁决。
6. 输出 `result.json`，覆盖输入 `output_contract` 的每一个键，并给出 `status`、`uncertainty`、`errors`、`stats` 与运行记录。

本 Skill **只做抽取式回答**：答案由原文片段组成，不补充知识库之外的论断。

## 适用条件

- 输入目录包含 `case.json`（必需），可选 `task.md`，以及真实材料文件。
- 材料是本地文件：`.txt` `.md` `.markdown` `.csv` `.tsv` `.json` `.jsonl` `.tex` `.rst` `.log` `.yaml` `.yml` `.xml` `.html` `.htm`，以及带文本层的 `.pdf`。
- 任务要求「哪个文件/哪一版/哪一段能回答这个问题」，需要引用与回链，而不是开放网络检索或论文精读。
- 需要确定性复跑：同一输入必须得到同一结果。

## 不适用

- 无文本层扫描件的 OCR、图片/表格版面理解、加密或损坏 PDF 的内容恢复。
- 开放网络文献检索、综述写作、需要推理出知识库未记载内容的生成式回答。
- 跨语言翻译、单位换算、因果推断。
- 语义向量检索或调用外部模型（本 Skill 只用标准库词法检索）。
- 存储系统底层权限建设与跨账号权限审计。

## 输入形态

```text
/input/
  case.json            # 必需：case_id、questions/question、output_contract
  task.md              # 可选：可含 "Question:" / "问题：" 行
  <materials>/...      # 任意层级的真实文件
```

- 问题可位于 `questions` / `question` / `query` / `queries` / `prompt` / `task`；`questions` 支持字符串数组或 `{id, question}` 对象数组。
- 材料路径可由 `input_dir` / `materials` / `files` / `path` / `root` 指定；缺省扫描 `case.json` 所在目录。
- `output_contract` 支持 JSON Schema（`properties`）、字段名数组、`{field: type}` 对象、`required` 数组。
- `case.json` 与 `task.md` 不会被当成回答材料。

## 调用方式

在 Skill 安装目录（平台为 `/skills/weekly-skill`）执行：

```bash
python3 /skills/weekly-skill/scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

等价薄封装（参数完全相同）：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py --input /input --work /app/work --out /app/output
```

- `--input`：目录或单个 `case.json`，默认 `/input`；兼容 `--case`。
- `--work`：工作目录，写 `inventory.json`、`qa_evidence.json`、`qa-report.md` 草稿，默认 `/app/work`。
- `--out`：目录（写 `result.json`）或 `.json` 文件，默认 `/app/output`；兼容 `--output`。
- 仅 Python 标准库；不联网；无状态；可重复执行；退出码恒为 0。

Windows 注意：`--out` 指到已存在的目录时，脚本会写入该目录下的 `result.json`；不会把目录当作文件替换（避免 `WinError 5`）。

## 输出契约

`result.json` 顶层固定包含：

| 字段 | 含义 |
|-|-|
| `case_id` | 与输入一致；合同字段不能覆盖它 |
| `status` | `success` / `partial` / `insufficient_input` / `failed` |
| `answers` | 逐问题结果：答案、置信度、引用标签、支撑段落、缺失词 |
| `answer` | 第一个问题的答案（兼容单问题契约） |
| `citations` | 可定位引用：`label`、`file`、`section`、`page`、`line_start/line_end`、`char_start/char_end`、`quote`、`quote_sha256` |
| `supporting_passages` | 排序后的段落：分数、命中词、坐标、引用标签 |
| `evidence_gaps` | 无依据问题：缺失词与原因 |
| `conflicts` | 同单位数值冲突：双方引用、数值、单位，不裁决 |
| `confidence` | `moderate_lexical_support` / `low_lexical_support` / `no_evidence` / `no_question` / `no_material` |
| `index` | 文件清单：哈希、字节、字符、编码、权限、年份、版本标签；重复文件单独标记 |
| `versions` | 版本组：成员、年份/版本标签、是否内容不同 |
| `duplicates` | 按 sha256 识别的重复文件与首份文件 |
| `skipped` | 跳过文件及原因 |
| `needs_human_confirmation` | 缺证、冲突、不可读文件的人工确认项 |
| `result` | 上述业务字段的聚合对象 |
| `evidence` | 检索参数、文件哈希、`source_mutation=none`、生成器版本 |
| `uncertainty` | 词法召回、PDF 页码、版本分组等限制 |
| `errors` / `stats` | 真实错误与计数 |
| `contract_notes` | 每个契约键的映射或"无法判断"说明 |
| `contract_extras` | 契约键、映射方式、未知键、被接受的额外键 |

**契约覆盖规则**：`output_contract` 的每个键都会出现在顶层。已知别名（`results`→`answers`、`sources`→`citations`、`gaps`→`evidence_gaps`、`index`→`index` 等）填真实值；已知生产者但没有值时写结构化 `cannot_determine` 对象；完全未知的键同样写结构化对象并记录在 `contract_extras.unknown_fields`。不会留 `null`、`pending` 或空占位冒充结果。

## 处理流程

1. **输入解析**：读取 `case.json`；不可读或非对象 → `failed`，仍写完整契约结果。
2. **盘点**：按相对路径排序遍历；不跟随符号链接；跳过 `__pycache__`、`.git` 等；单文件与总量有上限。
3. **文本抽取**：UTF-16 BOM → UTF-8 → GB18030 → Big5 → Latin-1；HTML 去标签；XML 保留原文；PDF 解压 FlateDecode 内容流并抽取 `Tj`/`TJ` 与十六进制串；抽不到文本记 `empty_or_no_text_layer`，**不伪造内容**。
4. **去重与版本**：sha256 相同只索引首份，其余进 `duplicates`；同目录同名主干（去年份/版本词）形成 `versions` 组。
5. **分块**：按空行分块，识别 Markdown、编号、中文序号标题；超长块按 1000 字符切分；记录章节、行号、字符区间。
6. **召回**：查询与段落做 ASCII 词 + CJK 单字/二元组；tf-idf 打分，加分文件名与章节命中；低于阈值判为无依据。
7. **回答**：每个问题取前 6 段，选与查询重合最高且含数值的句子作为引用片段；答案只拼接原文片段并附 `[S#]`。
8. **缺证与冲突**：查询词在语料中零命中 → `evidence_gaps`；同一内容词下同单位数值不同 → `conflicts`，双方原文并列。
9. **确定性**：所有排序带稳定次级键；不使用随机数、时间戳或机器绝对路径。

## 证据要求

- 每条引用必须能被第三方复现：`file` 是相对输入根的 POSIX 路径，`line_start` 是抽取文本的 1 起算行号，`char_start/char_end` 是字符偏移，`quote` 是该区间内的连续原文，`quote_sha256` 是片段 UTF-8 的 sha256。
- PDF 的 `page` 为 `null`（本 Skill 不解析页面对象），行号也只对应抽取文本；必须在 `uncertainty` 说明。
- 哈希覆盖范围：文件未超过 4 MB 时为 `full`，否则为 `prefix`；`prefix` 不能当作整文件指纹。
- 复核方法：打开 `file`，跳到 `line_start`，逐字比对 `quote`；对不上就判该引用不可用，并在复核记录中说明。
- 跳过、不可读、重复、版本冲突、证据冲突都要有记录；**不把未完成写成完成**。

## 异常处理

| 情况 | 处置 | status |
|-|-|-|
| `case.json` 缺失 | 仍尝试扫描材料，记录 `case_json_missing` | `failed` |
| `case.json` 损坏/非对象 | 记录 `case_json_invalid`，仍写完整契约结果 | `failed` |
| 知识库为空 / 无可读文本 | 空索引 + `no_material` 说明 | `insufficient_input` |
| 无问题字段 | 只返回索引，`confidence=no_question` | `partial` |
| 某问题零命中或低分 | 回答「没有依据」，写入 `evidence_gaps` | `partial` |
| 同单位数值冲突 | 双方原文并列，写入 `conflicts` | `partial` |
| 文件不可读 / stat 失败 | 记入 `skipped`，其余文件继续 | `partial` |
| 不支持扩展名 / 二进制 | 安全跳过，不影响其它文件 | 不降级 |
| PDF 无文本层 / 解压失败 | 记 `empty_or_no_text_layer`，不伪造 | `partial` |
| 编码异常 | 逐级回退；替换字符标记低置信 | `partial` |
| 输出目录不存在或 `--out` 是目录 | 自动创建并写 `result.json` | 原状态 |
| 未捕获异常 | 兜底写 `failed` 结果，退出码 0 | `failed` |

## 限制

- 词法检索会漏掉同义改写、跨语言表达与隐含指代；`low_lexical_support` 不等于错误，但必须人工复核。
- 版本关系只依据文件名/元数据标签，不做语义 diff；同名不同目录不会归为同组。
- 重复识别依据字节哈希，内容相同但编码不同的文件不会被判重。
- PDF 抽取不保证阅读顺序与印刷页码。
- 不做单位换算；冲突检测只比较相同单位下的数值。
- `answer` 是抽取式拼接，不是流畅的综述；执行 Agent 可以在不新增事实的前提下组织语言，但必须保留引用。

## 最小示例

```bash
python3 scripts/sk_entry.py --input examples/demo-case --work /tmp/demo-work --out /tmp/demo-out
```

示例输入见 `examples/demo-case/case.json`，完整说明见 `examples/quickstart.md`。示例输出仅用于演示接口与定位字段，**不是**任何平台案例的正式结果。

## 交付自检

- [ ] `python3 scripts/sk_entry.py --input <案例目录> --work <工作目录> --out <输出目录>` 退出码为 0。
- [ ] `result.json` 的 `case_id` 与输入一致。
- [ ] `output_contract` 每个键都在顶层，且不是 `null` / `pending` / 空占位。
- [ ] `status` 属于四个枚举值，且与 `evidence_gaps`、`conflicts`、`errors` 自洽。
- [ ] 每条引用都有 `file`、`line_start`、`char_start/char_end`、`quote`、`quote_sha256`。
- [ ] 逐条打开引用位置，确认 `quote` 与原文一致；对不上就降级或剔除。
- [ ] 无依据的问题没有被编造成有依据；冲突没有被擅自裁决。
- [ ] 重复文件、版本组、跳过文件都有记录。
- [ ] 相同命令重复执行，`result.json` 内容一致。
- [ ] 提交目录无 `__pycache__`、无符号链接、无令牌或本机绝对路径。

## 执行 Agent 的强制步骤

1. 先运行入口命令，确认退出码 0。
2. 读取 `/app/output/result.json`，检查 `case_id`、`status`、`contract_extras`、`evidence_gaps`。
3. 对每条 `citations`，按 `file` + `line_start` 打开原文核对 `quote`；核对失败的引用不得保留为有效证据。
4. 把运行命令、`status`、核对结果、缺证项、限制写入 `/app/output/qa-report.md`（脚本已生成草稿，执行 Agent 必须核对后改写）。
5. 不要修改输入文件；不要声称平台评分或官方案例结果。
