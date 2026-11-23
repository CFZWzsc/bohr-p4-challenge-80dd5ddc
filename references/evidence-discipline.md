# 证据纪律：定位、回链、不编造

## 1. 三条硬规则

1. **不编造**：知识库里没有的论断，不写进 `answer`。没有依据就写没有依据，并列出缺什么。
2. **可回链**：每条引用必须能落到具体文件、具体行、具体字符区间和具体原文片段。
3. **不改输入**：`source_mutation=none`；脚本只读输入，所有产物写到 `--work` 与 `--out`。

## 2. 引用的可核对结构

```json
{
  "label": "S1",
  "question_id": "q1",
  "file": "01_lab/2021-buffer-notes.md",
  "section": "Buffer recipe",
  "page": null,
  "line_start": 5,
  "line_end": 5,
  "char_start": 52,
  "char_end": 128,
  "quote": "The final buffer recipe was 50 mM Tris-HCl, 150 mM NaCl, 1 mM EDTA at pH 7.4.",
  "quote_sha256": "<片段 UTF-8 的 sha256>"
}
```

复核步骤：

1. 在输入根下打开 `file`。
2. 跳到 `line_start`，确认该行包含 `quote` 的首句。
3. 逐字比较 `quote` 与原文（允许首尾空白差异，不允许改字）。
4. 计算 `quote` 的 sha256，与 `quote_sha256` 比较。
5. 任一步失败：该引用不可用，必须在复核记录中写明，不能保留为有效证据。

## 3. 何时必须写"没有依据"

- 查询词在语料中零命中（`missing_terms` 覆盖全部查询词）。
- 最高检索分低于阈值。
- 唯一命中来自文件名或章节标题，而没有正文句子支撑。
- PDF 无文本层、文件不可读、权限不足。

这些情况写入 `evidence_gaps`，并把 `status` 降为 `partial` 或 `insufficient_input`。不得用「可能」「大概」把无依据写成有依据。

## 4. 冲突的处理

- 只有**同一单位**下数值集合不同才算冲突；例如两段都写 `3000 g` 不冲突，一段写 `3000 g`、另一段写 `2500 g` 才冲突。
- 冲突双方原文并列，附带引用编号、文件、数值；`resolution` 为 `not decided`。
- 不取平均、不选「更新版本」、不擅自说哪一方正确；版本新旧只作为元数据记录，不作为真值裁决。

## 5. 重复与版本

- 重复：sha256 相同 → 后者进 `duplicates`，不作为独立证据重复计分。
- 版本：只按文件名/元数据标签分组，不声称内容差异；需要语义 diff 时由人工完成。
- 版本组内每个成员都保留哈希与字符数，便于确认是否真的不同。

## 6. 不确定性的写法

`uncertainty` 必须是可操作的限制，而不是免责声明。示例：

- "Lexical retrieval may miss paraphrases, synonyms and cross-language matches."
- "PDF citations use page=null; line numbers refer to extracted text."
- "N duplicate file(s) were identified by sha256 and not indexed twice."
- "Some questions had no above-threshold evidence; see evidence_gaps."

## 7. 禁止事项

- 不写平台分数、评审结论或官方案例结果。
- 不把 `examples/demo-case` 的输出冒充正式案例结果。
- 不写令牌、密钥、个人路径或账号信息。
- 不修改输入文件，不删除无法处理的文件；只记录 `skipped`。
