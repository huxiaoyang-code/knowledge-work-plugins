# 通信研究：按阶段开放能力的 harness 插件

复用 Claude Code、Codex 等成熟运行时，完成通信工程选题、初稿、独立评审、仿真/实物实验与论文返修。管理器只管理会话、提交物与权限；研究、规划、工具调用和写作由所选 harness 执行。

本目录是从原 `bio-research` 方法与插件组织改编的独立增量，原目录和仓库现有插件不变。许可与来源见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。

同事接手与继续开发请先读 [AGENTS.md](AGENTS.md) 和 [Codex 交接指南](docs/CODEX_HANDOFF.md)。指南包括源码包核验、环境安装、模型与连接器配置、完整手动阶段流程、返修及扩展位置。

## 阶段与隔离

```text
独立研究运行时 A / B / C
       │ 各自选题、调研、理论与实验前初稿
       ▼
冻结提交版本 → 全新评审运行时独立检索与审查
       │ revise / reject / insufficient：返修或停止
       │ 当前初稿版本 pass
       ▼
为该课题物化执行配置 → 仿真、SDR/USRP、真实结果与完整论文
       ▼
冻结完整论文 → 多个全新评审运行时 → 返修、复审或内部交付
```

三个 profile 是可分别加载的插件根目录：

| Profile | 可发现 Skills | 用途 |
|---|---|---|
| `profiles/research` | `telecom-research` | 选题、文献、理论、初稿与提交 |
| `profiles/review` | `telecom-review` | 独立初稿/完整论文评审 |
| `profiles/execution` | `telecom-experiment`、`telecom-paper` | 通过初稿评审后才开放的实验与完整论文 |

不能把三个 profile 一起安装为研究运行时的默认能力。管理器每次只物化当前身份对应的 Skills，并使用新的运行目录和会话配置。Claude 配置使用项目 `.claude/skills`，Codex 配置使用 `.agents/skills`；生成的 Claude 启动计划不再同时加载同一份插件副本。细节参考资料随 Skill 按需读取；执行阶段的 Skill 描述、工具及凭据不进入研究配置。

## 本地安装与基本操作

需要 Python 3.11+。从本目录安装控制后端；MCP 适配器使用可选 SDK：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[mcp]"
python -m telecom_research --help
```

研究状态、令牌、稿件、实验数据和运行目录放到源码目录之外。下面的 `D:\telecom-work\state` 是管理者状态路径示例，不写入源码仓库：

```powershell
python -m telecom_research --state D:\telecom-work\state init
python -m telecom_research --state D:\telecom-work\state project-create --name "通信研究课题" --final-quorum 2
```

使用命令返回的实际标识创建研究运行时：

```powershell
$projectId = '<project-create 返回的课题 id>'
python -m telecom_research --state D:\telecom-work\state runtime-create --project $projectId --role research
$runtimeId = '<runtime-create 返回的运行时 id>'
python -m telecom_research --state D:\telecom-work\state materialize --runtime $runtimeId --harness claude --profiles-root "$PWD\profiles" --destination D:\telecom-work\research-001
```

`--harness codex` 物化相应宿主布局。`--profiles-root` 指向当前源码副本中的 `profiles`；安装的后端包不隐式包含全部阶段 Skills。目标目录需为新目录，避免混入旧会话能力。按生成的启动说明及计划运行宿主，检查实际工具清单；物化配置不等于已经启动或验证该 harness。

管理器提供前台 JSONL 进程监督接口。显式 `start` 才会按状态库中保存的启动计划运行真实宿主；`launch-plan.json` 是可读副本，直接编辑它不会改变监督器命令。这一步可能调用已配置模型并产生费用。保持监督进程运行，以管理多个独立子进程和各自日志：

```powershell
python -m telecom_research --state D:\telecom-work\state supervise
```

在其标准输入发送 JSON 行，`runtime` 填实际运行时 id：

```json
{"op":"start","runtime":"实际运行时 id"}
{"op":"status","runtime":"实际运行时 id"}
{"op":"stop","runtime":"实际运行时 id"}
{"op":"quit"}
```

多个 `start` 可启动不同课题或评委；默认不自动调用模型，不创建自建 Agent 推理循环。监督接口管理独立进程/会话，当前没有桌面多窗口界面。`quit` 会停止该监督进程所拥有的子进程；监督进程异常退出后的残留状态需核对处理，不能根据旧 PID 直接终止未知进程。

初稿提交后，管理者用返回的提交 id 创建独立评审身份，再物化新的评审目录：

```powershell
$submissionId = '<初稿提交返回的 id>'
python -m telecom_research --state D:\telecom-work\state runtime-create --project $projectId --role review --submission $submissionId
```

评委用 `review_context` 领取不可变稿件，用 `review_submit` 提交记录；字段说明见 [评审记录](profiles/review/skills/telecom-review/references/report-fields.md)。评委提交通过决定后，管理者为该课题创建 `--role execution` 运行时并物化执行目录。未通过、过期或被新稿替代的批准不能授权执行。查看进度：

```powershell
python -m telecom_research --state D:\telecom-work\state status --project $projectId
```

研究会话用 `research_context` 读取当前初稿与该版本反馈；执行会话用 `execution_context` 读取批准初稿、证据、计划、运行记录，以及已有完整论文与其评审反馈。重启或更换窗口后从后端恢复返修材料，无需继承旧会话。完整论文提交后，按项目的 `final-quorum` 创建多个独立评审身份。评委通过 `review_context` 获得分配的提交内容及关联运行溯源；第一轮不共享其他评委意见。返修产生新版本并重新评审，不能用平均分跳过未解决的重大缺陷。

## 连接器与后端边界

连接器类别、阶段和可选实现见 [CONNECTORS.md](CONNECTORS.md)。源 profile 的 `.mcp.json` 保持空服务表，物化时配置实际控制后端。外部文献、标准资料、仿真或硬件服务需单独接入；没有预填虚构远程地址。

本地后端记录课题、运行时身份、不可变稿件、评审、阶段权限和实验任务。研究和评审的 MCP 不暴露执行工具；调用路径同时检查作用域和当前批准，避免仅靠提示词限制。

这是本地工作流/控制后端原型。测试可验证阶段控制与数据行为，不代表真实 Claude Code/Codex 会话、联网文献服务、GPU、MATLAB 或 SDR/USRP 已完成联调。未连接 Worker 的实验保持未配置/待执行；管理者导入的真实与合成结果分别标识，不能把演示数据用于真实结论。

物化目录和作用域令牌不是操作系统沙箱：若运行时可任意读取管理者状态、修改后端或访问设备凭据，就不能实现对抗性的隔离。部署时把管理者状态与运行时身份分开，通过宿主权限、独立用户/容器或服务边界限制访问。研究包的通用代码能力不受本插件重新实现；正式算力、实验服务、设备和交付入口由后端控制。

## 验证

```powershell
python -m unittest discover -s tests -v
```

Skills 的结构检查可用 Codex `skill-creator` 的 `quick_validate.py`；Windows 上用 `python -X utf8` 读取中文文件。结构通过不能证明科学判断正确。选题评审和完整论文评审仍需用已知案例、人工意见及实际研究逐步校准。

## 源码交付

本仓库的 [打包 Skill](.agents/skills/package-telecom-research/SKILL.md) 处理“打包/发给同事/交付源码”。默认用 `scripts/package_source.py --repo <仓库> --output-dir <仓库外目录> --scope repository` 从干净 Git 快照生成包含全部原插件的完整源码 ZIP；通信改造保留在 `telecom-research/`。用户明确只要通信项目时才用 `--scope telecom`。包附同事 Codex 入口、元数据、逐文件清单与 SHA256 校验文件；完整步骤和校验边界见 [交接指南](docs/CODEX_HANDOFF.md)。
