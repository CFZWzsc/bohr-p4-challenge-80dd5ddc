# 快速开始（示例）

以下命令与输出仅用于演示接口，**不是**任何平台案例的正式结果。

## 1. 运行示例

在提交目录（含 `scripts/`、`assets/`、`examples/`）下执行：

```bash
python3 scripts/sk_entry.py \
  --input examples/demo-case \
  --work /tmp/demo-work \
  --out /tmp/demo-out
```

Windows PowerShell：

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python scripts\sk_entry.py --input examples\demo-case --work .\demo-work --out .\demo-out
```

退出码应为 0。生成：

```text
/tmp/demo-out/result.json
/tmp/demo-out/qa-report.md          # 草稿，需人工核对后改写
/tmp/demo-work/inventory.json       # 文件清单、版本组、重复、跳过
/tmp/demo-work/qa_evidence.json     # 问题、答案、缺证、冲突
/tmp/demo-work/qa-report.md         # 草稿副本
```

## 2. 示例输入

- `01_lab/2021-buffer-notes.md`：2021 配方与血浆分离条件。
- `01_lab/2022-buffer-revision.md`：2022 修订版，配方数值相同、措辞不同；与 2021 文件形成版本组。
- `02_protocols/protocol-A.txt`：血浆分离流程与储存温度。
- `03_data/measurements.csv`：四个样本的测量值。
- `04_archive/2021-buffer-notes-copy.md`：与 2021 文件字节相同，用于演示 sha256 去重。
- `case.json`：两个问题、9 个 `output_contract` 字段。

## 3. 预期结果摘要

```json
{
  "case_id": "demo-lab-kb-001",
  "status": "partial",
  "answers": [
    {"question_id": "q1", "confidence": "moderate_lexical_support", "citations": ["S1", "S2"]},
    {"question_id": "q2", "confidence": "moderate_lexical_support", "citations": ["S3", "S4", "S5"]}
  ],
  "duplicates": [{"file": "04_archive/2021-buffer-notes-copy.md",
                  "duplicate_of": "01_lab/2021-buffer-notes.md"}],
  "versions": [{"group": "01_lab/buffer", "members": 2, "distinct_content": true}],
  "evidence_gaps": [],
  "conflicts": [
    {"question_id": "q2", "quantity": "temperature", "unit": "°C",
     "left": {"file": "01_lab/2021-buffer-notes.md", "value": "room temperature (approx. 20-25 °C)"},
     "right": {"file": "01_lab/2022-buffer-revision.md", "value": "4 °C"},
     "resolution": "condition_conflict"}
  ]
}
```

实际行号、分数、`version_label` 与引用条数以运行结果为准；上面只是字段示意。

## 4. 核对

1. 打开 `result.json`，确认 `case_id`、`status`、`index`、`citations`、`duplicates`、`versions` 都存在。
2. 对每条引用，打开 `file` 跳到 `line_start`，逐字比较 `quote`。
3. 打开 `inventory.json`，核对 4 份被索引文件 + 1 份重复文件。
4. 用相同命令再跑一次，确认 `result.json` 内容一致。
5. 检查提交目录没有 `__pycache__`：

```powershell
Get-ChildItem -Recurse -Filter __pycache__
```

## 5. 常见问题

| 现象 | 原因 | 处理 |
|-|-|-|
| `status=insufficient_input` | 目录没有可读文本 | 检查 `--input` 是否指向案例根目录 |
| 某问题 `evidence_gaps` 非空 | 查询词零命中或分数低于阈值 | 查看 `missing_terms`；不要放宽阈值后声称有依据 |
| `duplicates` 有记录 | 文件字节相同 | 正常行为；重复文件不重复计分 |
| `versions` 为空 | 文件名没有可识别的年份/版本主干 | 正常；版本分组只依据文件名与元数据 |
| PDF 引用 `page` 为 `null` | 未解析页面对象 | 用 `line_start` 与 `quote` 复核 |
| `status=partial` 且有 `conflicts` | 同题段落数值或温度条件不一致 | 人工核对原文，不要擅自裁决 |
