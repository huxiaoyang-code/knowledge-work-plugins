# 本地控制后端契约

本版本管理现有 harness 的独立进程、阶段工作区和正式工具权限，不实现模型推理循环。SQLite、稿件快照、凭据、日志与数据产物必须存放在 Git 工作树外。此实现适合本机原型验证，不是多租户安全服务。

## 安装与边界

在 `telecom-research/` 执行 `python -m pip install -e ".[mcp]"`。核心 CLI 仅依赖 Python 3.11+ 标准库；MCP stdio 适配器使用可选的官方 `mcp` SDK。Python wheel 不包含 profile 素材；非 editable 安装后，`materialize` 必须传 `--profiles-root <源码目录>/telecom-research/profiles`。

研究、审稿和执行的 Skills 分别来自 `profiles/research`、`profiles/review`、`profiles/execution`。物化时仅复制当前阶段 Skills 到 Claude 的 `.claude/skills` 或 Codex 的 `.agents/skills`，不会复制作者会话历史。Claude 通过项目 Skills 加载，避免同时通过 `--plugin-dir` 重复发现。

生成的命令使用新会话且不使用危险的权限绕过选项。Claude 的严格 MCP 配置与 Codex 的忽略用户配置选项只约束对应设置，不保证屏蔽宿主全部全局 Skills、系统指令或文件读取。强隔离仍需操作人员提供干净的宿主配置与进程/文件系统沙箱；本地同一 OS 用户若可直接读取数据库或管理者凭据，能够绕过本原型的权限边界。

## CLI

统一形式为 `python -m telecom_research --state <外部状态目录> <命令>`，JSON 输出为 `{ok,result}` 或 `{ok:false,error}`。`init` 创建管理者凭据，其他管理命令默认从状态目录的 `manager.token` 读取。支持 `--token-file` 覆盖，凭据永不写到源码。

Windows 下处理中文稿件、课题名称或 JSON 输出时，使用 `python -X utf8 -m telecom_research --state <外部状态目录> <命令>`，或在当前终端设置 `PYTHONUTF8=1`，避免重定向输出使用系统 GBK 编码。此设置无需修改宿主全局配置。

| 命令 | 参数 |
|---|---|
| `init` | 新状态目录，不覆盖已有授权 |
| `project-create` | `--name`、`--final-quorum`（2–10，默认 2）、可选 `--synthetic` |
| `runtime-create` | `--project`、`--role research\|review\|execution`；review 必须提供 `--submission` |
| `submit` | `--runtime`、`--kind draft\|final`、`--manuscript`、`--evidence`、`--plan` 三个 UTF-8 文件 |
| `review` | `--runtime`、`--report` JSON 文件 |
| `materialize` | `--runtime`、`--harness claude\|codex`、`--destination` 新外部目录；可选 `--profiles-root`、`--python-executable` |
| `experiment-submit` | `--runtime`、`--spec` |
| `experiment-result` | `--experiment`、`--result`；管理者导入并校验来源和文件哈希 |
| `device-register` | `--device`、`--config`，须含 `operator_approved:true` |
| `device-lease` | `--device`、`--runtime`、`--seconds`（1–86400） |
| `status` | 可选 `--project` |
| `audit` | 读取追加式操作记录 |
| `supervise` | 启动 JSONL 管理循环，仅收到显式 start 后才运行真实 harness |

`submit/review/experiment-submit` 是管理者代指定运行时提交的 CLI 便捷入口。Agent 只能拿到自己的凭据并调用 MCP，MCP 不暴露创建项目、创建审稿身份、导入结果、注册设备等管理操作。

监督循环输入示例：`{"op":"start","runtime":"运行时 ID"}`、`{"op":"status","runtime":"运行时 ID"}`、`{"op":"stop","runtime":"运行时 ID"}`、`{"op":"quit"}`。管理进程须保持运行。退出会停止其拥有的进程；Windows 用拥有的 Job Object 管理进程树，POSIX 用独立进程组。状态写入数据库，日志写入状态目录。管理器崩溃后可能遗留 running 记录，需要操作人员核对现场；不会仅凭数据库 PID 杀死未验证进程或重复启动。当前没有提供自动恢复陈旧进程记录的 CLI。

## 权限与版本

每次提交在事务中保存 manuscript、evidence、plan 原文及 SHA-256；每次重交生成新版本。审稿身份绑定一个版本且只能提交一次不可变意见。所有当前分配的初稿评委均完成并通过后，才可建立执行身份。新增评委会恢复待审状态。任何 revise、reject、insufficient 均阻止执行。

新初稿使旧执行授权失效，即使旧进程已缓存工具列表，每次调用仍核对最新数据库。旧执行目录里的 Skill 文本无法被追溯“遗忘”，后端保证的是正式服务调用被拒绝。MCP 的工具列表也随当前权限变化，不依赖客户端热刷新才能拒绝调用。

完整论文需要至少一个当前初稿下的完成实验记录。终审至少由项目设定数量的独立身份完成，所有已分配终审均通过才标记 complete；否则要求修改并提交新终稿。complete 是内部交付状态，不代表期刊录用或自动投稿。

审稿窗口的 `project_status` 只返回自己的报告，`review_context` 不返回作者身份或其他评委意见。研究窗口的 `research_context` 返回 `current_draft` 和该版本的 `feedback`，使全新研究会话能够继续修改。执行窗口的 `execution_context` 返回 `approved_draft`、`experiments`、`current_final` 和当前终稿的 `feedback`，供全新执行会话读取获批计划及继续返工。`current_draft` 或 `current_final` 在尚未提交时为 null；稿件的 `documents` 含 manuscript、evidence、plan 原文。终审上下文返回终稿绑定的实验及来源记录，避免通过开放执行能力读取结果。

## MCP 字段

启动：`python -X utf8 -m telecom_research.mcp_server --state <目录> --token-file <该运行时凭据>`。服务器拒绝管理者凭据。工具为 `project_status`、研究阶段 `research_context/submission_submit`、审稿阶段 `review_context/review_submit`、执行阶段 `execution_context/experiment_submit/experiment_status/paper_submit`。

`review_submit` 参数为 `{"report": {...}}`：

- `decision`: `pass | revise | reject | insufficient`。
- `scores`: `novelty/theory/experiments/engineering/evidence/presentation` 六项 0–10 有限数值；仅 insufficient 可以为 null。
- `confidence`: 0–1 有限数值。
- `rationale`: 非空理由。
- `blockers`: 未解决严重问题的字符串数组；pass 必须为空。
- `search_evidence`: `{query,source,url,accessed_at,finding}` 数组，实际来源 URL 为 HTTP(S)。只有 insufficient 可为空，以免缺少联网能力时被迫编造搜索。

后端检验结构和权限，不会自动联网证明报告真实性或判断创新。论文质量由独立 harness 实际读取、检索和评审；检索服务尚未默认配置。

`experiment_submit` 参数为 `{"spec": {...}}`，字段含 `kind:simulation|hardware`、`name`、`code_revision`、非空 `config`。硬件还要求 `device_id`、`device_config_hash`、与已登记配置完全相同的 `hardware_config` 和有效独占租约。硬件的 `config` 只表示算法参数，RF 设置以批准的 hardware_config 为准。请求仅登记为 `pending_unconfigured`，本版本不会执行命令、发射或采集。

管理者可导入结果：`origin:simulated|measured|synthetic`、`source`、匹配请求的 `code_revision/config_hash`、非空 `metrics`、`artifacts:[{path,sha256}]`。文件必须真实存在且哈希匹配，后端复制快照。后续完整稿件提交与结果读取再检查快照是否变化。合成结果仅允许显式 synthetic 项目；校验来源字段不能证明实验真实发生，管理者仍须核验外部 Worker 日志与设备记录。

## 验证

`python -m unittest discover -s tests -v` 包括状态恢复、角色越权、版本撤销、盲审隔离、终审返工、硬件配置、产物哈希、阶段物化、假 harness 进程及子进程停止，以及使用官方 SDK 的真实 stdio 协议往返。没有安装 SDK 时只跳过对应协议测试。所有测试使用合成材料，不调用真实模型、联网检索或设备。协议测试设独立进程截止时间，受限 Windows 环境若不支持 SDK 的异步管道，会明确失败，不能视作联通成功。
