# 对照与增益证据（基础 Agent 基线 vs 本 Skill）

> 本文件由提交者在仓库内 demo 案例上实跑生成：命令
> `python3 scripts/sk_entry.py --input examples/demo-case --work /tmp/work --out /tmp/out`，
> 退出码 0，`status`=partial。数值仅说明演示案例上的接口与产出，不代表平台正式案例结果。

## 任务与基线口径

- 本题任务：科研知识库问答（带引用与冲突检测）
- 基础 Agent 基线：基础 Agent 直接读问题、返回整篇文件或凭印象作答，不给可定位段落、不区分版本、不标缺证。

## 同输入下的实际产出（demo）

| 结果字段 | 条目数 |
|---|---:|
| `answers` | 2 |
| `citations` | 5 |
| `supporting_passages` | 5 |
| `evidence_gaps` | 0 |
| `conflicts` | 1 |

- 契约键覆盖：`answers`, `citations`, `supporting_passages`, `evidence_gaps`, `conflicts`, `index`, `versions`, `duplicates`, `status` 中非空 8/9 个；
  无法由材料支撑的项写入 `uncertainty`/`unresolved`，不以空列表冒充已完成。
- 单次运行即产出上述全部内容（无第二阶段待办），重复执行结果字节一致。

## 差异结论

1. 基线停在「建议/整篇返回」，本 Skill 把结果落成带标识与证据的结构化记录，可直接被他人复核。
2. 每条记录都带来源文件与哈希（见 `evidence`/`applied_records`/`citations`），定位到具体文件或页码，
   而不是只给结论。
3. 材料不足时如实降级（`status`、`misses`、`evidence_gaps`、`unresolved`），不编造条目。
