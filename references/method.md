# 方法说明：索引、检索、引用与冲突

## 1. 盘点与去重

- 只遍历 `--input` 解析出的根目录（`case.json` 所在目录，或 `input_dir`/`materials`/`files`/`path` 指定目录）。
- 跳过符号链接、`__pycache__`、`.git`、`node_modules`、虚拟环境等目录。
- 单文件读取上限 4 MB；超过时只读取前缀，`hash_scope` 记为 `prefix`。
- 相同 sha256 的文件只索引第一份（按相对路径排序），其余写入 `duplicates`，避免重复证据抬高分数。

## 2. 文本抽取

| 类型 | 方法 | 编码/置信 |
|-|-|-|
| 纯文本/Markdown/CSV/JSON/TeX | 按字节解码 | UTF-16 BOM → UTF-8 → GB18030 → Big5 → Latin-1 |
| HTML/XML | 保留原文，按文本检索 | 同上；不解析 DOM |
| PDF | 解压 FlateDecode 内容流，抽取 `(...)Tj`、`[...]TJ` 与 `<hex>` 字符串 | Latin-1 / UTF-16BE（十六进制串） |
| 二进制或空文本 | 跳过 | `binary_content` / `empty_or_no_text_layer` |

PDF 不解析页面对象，因此 `page=null`，行号也只对应抽取文本。

## 3. 分块与定位

- 按空行分块；只有 1–2 行且形如 Markdown 标题、编号标题、中文序号的块被当作章节名，不单独索引。
- 每块记录 `section`、`line_start/line_end`、`char_start/char_end`。
- 超过 1000 字符的块继续切分；切分后仍保持连续原文，不重叠。
- 引用片段从块内挑选：优先与查询词重合最多的句子，数值句获得 0.5 的轻量加分；片段长度上限 400 字符。

## 4. 检索打分

查询与段落都做同一套分词：

- ASCII：`[a-z0-9][a-z0-9_\-.]{1,}`，去掉英文停用词。
- 中文：单字 + 二元组，去掉中文停用词。
- 打分：`idf = log((1+N)/(1+df)) + 1`，按 token 权重累加；中文二元组权重 1.6，单字 0.45，ASCII 1.0。
- 文件名命中查询词 +0.5；章节名命中 +0.6。
- 取前 6 段；最高分低于 2.0 判为无依据；低于 3.0 或支撑段落少于 2 条标为 `low_lexical_support`。
- 排序键：分数降序 → 文件路径 → 行号 → 字符偏移，保证同分稳定。

## 5. 回答与引用

- 每个问题的答案只拼接前两条引用片段，格式 `原文 [S1] 原文 [S2]`。
- 每条引用包含：`label`、`question_id`、`file`、`section`、`page`、`line_start/line_end`、`char_start/char_end`、`quote`、`quote_sha256`。
- `quote` 必须是原文连续子串；脚本用 `find` 回填偏移，找不到时回退到块首。
- 多问题共用全局引用编号 `S1..Sn`，每条引用带 `question_id` 便于分组。

## 6. 缺证与冲突

- 缺证：查询 token 在全部语料中零命中，或最高分低于阈值 → `evidence_gaps`，列出 `missing_terms`。
- 冲突：两段证据共享至少一个内容词（长度 ≥4 或中文词），且**同一单位**下数值集合不同 → `conflicts`。
- 单位解析：`mg/kg/g/mL/L/mM/µM/nM/min/h/day/%/°C` 以及 `pH`；`4 C` 与 `room temperature` 不会因为多一个数值而被判冲突。
- 冲突只并列展示双方原文与数值，不取平均、不裁决；`resolution` 固定为 `not decided`。

## 7. 版本关系

- 版本键 = 目录 + 文件名去掉年份/`v1`/`revision`/`final`/`draft`/`copy`/`backup` 后的首个词。
- 同键且成员 ≥2 时输出 `versions` 组，记录每个成员的年份、版本标签、哈希、标题。
- `distinct_content` 表示组内是否存在不同哈希；脚本不做语义 diff，`note` 明确说明这一点。

## 8. 状态判定

| status | 条件 |
|-|-|
| `success` | 所有问题都有中等以上证据，无冲突、无不可读错误 |
| `partial` | 任一问题无依据/低置信、存在冲突、不可读文件或运行错误 |
| `insufficient_input` | 没有可读材料 |
| `failed` | `case.json` 缺失、损坏或非对象 |

## 9. 确定性

- 不使用 `random`、`time`、`datetime`、网络或环境相关排序。
- 输出不含时间戳与机器绝对路径；文件路径统一为相对 POSIX 路径。
- 同一输入重复运行，`result.json` 内容一致。
