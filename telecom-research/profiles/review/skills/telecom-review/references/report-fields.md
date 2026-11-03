# 本地后端评审记录

`review_submit` 的 `report` 使用下列字段，提交对象由评委运行时的分配决定，不能在参数中指定另一个课题或稿件：

| 字段 | 类型与含义 |
|---|---|
| `decision` | `pass`、`revise`、`reject`、`insufficient` |
| `scores` | 六项有限数值，均为 0–10：`novelty`、`theory`、`experiments`、`engineering`、`evidence`、`presentation`；仅 `insufficient` 可用 `null` 表示无法评价 |
| `confidence` | 0–1，说明评审证据充分程度 |
| `rationale` | 非空理由，引用具体证据和必要修改，解释分项评分 |
| `search_evidence` | 实际独立检索记录，每项含 `query`、`source`、HTTP(S) `url`、`accessed_at`、`finding`；仅 `insufficient` 可为空 |
| `blockers` | 未解决重大问题的字符串列表；`pass` 必须为空 |

评分用于表达判断，当前后端不会把它换算成期刊录用概率。`experiments` 在初稿模式评价设计，在完整论文模式评价真实执行与结果。检索失败或工具不可用时使用 `insufficient`，在 `rationale` 说明缺少的访问能力和受影响的判断；不能为满足字段而编造 URL、访问时间或搜索结果。

初稿和完整论文均绑定提交的内容摘要。初稿通过开放对应课题执行能力；完整论文按项目设定的多个独立评委数及全部已分配评审结果汇总。已提交意见是历史记录，返修形成新提交后重新分配评审。
