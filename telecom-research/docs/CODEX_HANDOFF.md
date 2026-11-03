# 给接手同事的 Codex：通信研究源码交接

本文面向负责安装、验证、配置和继续开发这份源码的 Codex。先阅读同目录项目的 [AGENTS.md](../AGENTS.md)、[README.md](../README.md) 和 [CONNECTORS.md](../CONNECTORS.md)，再根据实际环境行动。完整仓库包保留全部原插件，通信改造独立在 `telecom-research/`；通信专用包中，本项目直接位于包根目录。

## 先向同事说明当前状态

这是一套已有 harness 的本地运行时管理与阶段控制原型。研究推理和写作交给 Claude Code/Codex，项目不实现自己的模型推理循环。

| 内容 | 源码中已有 | 接手时仍需核实/配置 |
|---|---|---|
| 研究/评审/执行三组 Skills | 分阶段物化，按需读取参考材料 | 实际宿主能否正确发现当前组 Skills |
| 稿件与评审 | 不可变提交、角色凭据、版本绑定、返修反馈 | 真实文献工具与人工校准后的科研评审质量 |
| 阶段控制 | 当前初稿全部已分配评审通过才允许执行；换稿撤销旧授权 | 操作系统、账号和文件访问隔离 |
| 运行时 | 物化目录与启动计划，显式启动/状态/停止的前台监督器 | harness 安装、模型认证、模型/提供商选择及真实联调 |
| 实验 | 申请、硬件配置/租约约束、结果导入与摘要校验 | 实际仿真 Worker、GPU、MATLAB、GNU Radio/UHD/USRP |
| 论文 | 完整论文提交、至少两名独立终审、返修与研究包指引 | 真实实验、引用、LaTeX/文档编译与出版模板 |

没有自动阶段调度器、桌面多窗口管理界面或已部署云后端。评审分数是有理由的判断记录；后端不会证明创新或预测录用。结果导入校验文件摘要和实验来源字段，不能证明研究科学正确或测量真实有效。

先报告本机实际 readiness，再只询问缺失的必要选择：使用哪种 harness/模型账号、研究方向、可用检索源及设备。不要因“源码里有连接器类别”就声称已联网，也不要自动调用模型、运行物理发射或给示例课题签发虚假通过。

## 1. 检查源码包

保留收到的 ZIP 和 `.zip.sha256`。解压前后可核对 SHA256：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '<收到的源码 ZIP 绝对路径>'
Get-Content -LiteralPath '<同名 ZIP 的 .sha256 文件绝对路径>'
```

解压后的顶层 `START_HERE_FOR_CODEX.md` 指向本项目的 AGENTS 和交接指南；`PACKAGE-METADATA.json` 给出 `repository_url`、完整 `commit`、范围、源码/生成文件清单和 `handoff_entrypoint`。可以用通信项目内的 `scripts/package_source.py --verify <原ZIP>` 检查结构/摘要；若另外保有对应 Git 仓库，加 `--repo <仓库>` 才能与 Git 对象核对。包内自洽不等于经过第三方来源认证。

源码 ZIP 没有 `.git`；运行和测试不需要 Git 历史。不要因 `git status` 失败就宣称源码损坏，也不要自动新建仓库冒充原历史。后续做分支开发或重新生成 Git 快照包时，使用真实仓库副本并核对该提交；保存同事原有改动。

## 2. Windows 安装：中文路径与空格可用

打开 PowerShell，进入解压顶层或真实仓库根目录。下列命令同时识别完整仓库包和通信专用包。工作数据与虚拟环境放到用户目录下的独立工作区；已有目录不会被清理。

```powershell
$ErrorActionPreference = 'Stop'
$entryDir = (Get-Location).Path
if (Test-Path -LiteralPath (Join-Path $entryDir 'telecom-research\pyproject.toml')) {
    $telecomSource = (Resolve-Path -LiteralPath (Join-Path $entryDir 'telecom-research')).Path
} elseif ((Test-Path -LiteralPath (Join-Path $entryDir 'pyproject.toml')) -and
          (Test-Path -LiteralPath (Join-Path $entryDir 'profiles'))) {
    $telecomSource = $entryDir
} else { throw '请进入源码包顶层或 telecom-research 目录。' }
$workRoot = Join-Path $env:USERPROFILE 'telecom-work'
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$venvRoot = Join-Path $workRoot 'venv'
python --version  # 必须为 3.11 或更高；不满足时先选择已安装的合适 Python
python -X utf8 -m venv "$venvRoot"
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
$telecomPython = Join-Path $venvRoot 'Scripts\python.exe'
& $telecomPython -X utf8 -m pip install -e "${telecomSource}[mcp]"
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，检查网络与 Python 版本。' }
& $telecomPython -X utf8 -m telecom_research --help
& $telecomPython -X utf8 -m unittest discover -s (Join-Path $telecomSource 'tests') -v
if ($LASTEXITCODE -ne 0) { throw '测试失败，先检查实际错误。' }
```

核心库无第三方运行依赖，MCP stdio 适配器的可选依赖为 `mcp>=1.20,<2`。上述安装会从配置的软件源获取依赖；无网络时先说明缺口。报告测试实际通过/跳过数量；缺 MCP 导致的跳过不是传输联通。

如果 Codex 沙箱不允许系统临时目录，可仅在当前验证进程中把 `$env:TEMP` 和 `$env:TMP` 指向 `$workRoot` 下新建的临时子目录后重跑；不要修改系统全局设置或删除原临时目录。

Linux/macOS 使用相同 Python 模块与 CLI，虚拟环境解释器为 `<venv>/bin/python`；调整路径后执行。不要复制打包者的虚拟环境或任何机器专属认证。

## 3. 配置 harness、模型与外部工具

先检查 `claude --version` 或 `codex --version` 及其当前 `--help`。模型登录、账号和提供商配置由同事在本机完成；包中不包含模型密钥。当前后端没有统一的“按角色选模型/提供商”配置面板。

当前生成的启动行为有以下实际限制：

- Claude 使用项目 `.claude/skills`、显式 `--mcp-config <运行目录>/mcp.json` 和 `--strict-mcp-config`。额外已核实文献 MCP 可以在启动前加入这个生成的 `mcp.json`，不要替换本地 `telecom` 服务或把实验凭据给研究/评审会话。
- Codex 使用 `.agents/skills`、`--ignore-user-config`，并在启动参数中仅注入本地 `telecom` MCP。因此用户配置中的自定义 provider/model/MCP 不会自动保留；认证与可用默认提供商应实际检查。随意修改生成的 `mcp.json` 不会改变 Codex 计划中已存的参数。
- 若 Codex 需要自定义提供商或外部检索，先修改并验证 `runtime.materialize` 的宿主适配，或在确认过配置后显式手动启动。不要声称“填入一个 JSON 就已接好”。
- `launch-plan.json` 是供人检查的计划副本。监督器实际读取状态库中的计划；直接编辑这个文件不会修改 `supervise start` 的命令。要改变启动计划，应在适配代码/可信配置中实现并重新物化新的运行目录。
- 阶段物化只控制本项目放入运行目录的能力，不保证阻止宿主所有全局 Skills、插件、shell 或文件访问。管理员状态与凭据需独立权限/用户/容器或服务隔离；本地原型适合可信协作，不能宣称对抗性隔离已完成。

源 profiles 中的 `.mcp.json` 是空服务表。当前物化器不自动合并它们，也没有统一连接器管理器。真实 IEEE/OpenAlex/arXiv 等文献接入、GPU/MATLAB Worker、USRP 及 LaTeX 服务都要单独实现或配置验证。详见 [CONNECTORS.md](../CONNECTORS.md)。

## 4. 初始化状态与可靠的 CLI 调用

后续示例在同一 PowerShell 会话执行，使用上面定义的 `$telecomSource`、`$telecomPython` 和 `$workRoot`。CLI 输出 `{ok,result}` 或 `{ok:false,error}`；不要把整段 JSON 当成 id。

```powershell
$stateRoot = Join-Path $workRoot 'state'
function Invoke-Telecom {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $raw = & $telecomPython -X utf8 -m telecom_research --state "$stateRoot" @Arguments
    $exitCode = $LASTEXITCODE
    try { $reply = ($raw -join "`n") | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "CLI 未返回合法 JSON；退出码 $exitCode。" }
    if ($exitCode -ne 0 -or -not $reply.ok) { throw $reply.error }
    return $reply.result
}
function Write-Utf8Text {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}
```

`Write-Utf8Text` 写无 BOM 的 UTF-8，兼容 Windows PowerShell 5 与 PowerShell 7 的 JSON 读取差异；不要用系统默认中文编码写配置。

第一次创建状态时执行：

```powershell
if (-not (Test-Path -LiteralPath (Join-Path $stateRoot 'workflow.sqlite3'))) {
    Invoke-Telecom init
}
$project = Invoke-Telecom project-create --name '通信工程研究课题' --final-quorum 2
$projectId = $project.id
$projectId
```

已经有项目时先用 `Invoke-Telecom status` 找到原项目，复用其 id，避免把每次接手都变成新课题。`init` 拒绝覆盖已有状态和管理者凭据；部分初始化失败时保留现场诊断，不能直接删除目录重来。

`project-create --synthetic` 仅用于独立演示/测试项目；真实研究不要加该参数。状态库、`manager.token`、作用域令牌和日志不应提交或随源码传给同事。

## 5. 研究运行时与任务说明

```powershell
$research = Invoke-Telecom runtime-create --project $projectId --role research
$researchDir = Join-Path $workRoot ('research-' + $research.id)
$launch = Invoke-Telecom materialize --runtime $research.id --harness claude `
    --profiles-root (Join-Path $telecomSource 'profiles') `
    --python-executable $telecomPython --destination $researchDir
```

使用 Codex 时把 `--harness claude` 改为 `--harness codex`，并先解决上一节的提供商与检索配置。安装的 Python wheel 不包含全部 profiles；始终显式传本源码的 `--profiles-root`。目的目录必须是新的、位于源码与状态目录之外的路径。

通用启动提示没有具体研究方向。启动前在运行目录写任务说明；以下是可编辑任务示例，标题不代表已验证创新：

```powershell
$taskText = @'
本次任务：围绕 OFDM 信道估计，研究导频开销与模型失配鲁棒性。
先使用 telecom-research Skill，并调用 research_context 恢复当前稿件/反馈。
结合已连接文献工具比较候选方向，形成系统模型、最相近工作对照、
理论分析、实验计划和实验前初稿，再通过 submission_submit 提交。
尚无真实实验结果，禁止编造性能数字；检索能力不足时明确报告缺口。
资源与目标：根据本目录后续补充的实际设备、算力和论文目标执行。
'@
Write-Utf8Text -Path (Join-Path $researchDir 'CLAUDE.md') -Content $taskText
Write-Utf8Text -Path (Join-Path $researchDir 'AGENTS.md') -Content $taskText
Get-Content -LiteralPath (Join-Path $researchDir 'launch-plan.json')
```

任务文件由对应宿主读取；真实宿主是否成功加载须观察首次运行。不要将管理者凭据放入任务文件。并行课题重复创建研究运行时和独立项目/目录，明确分支目标；同一项目多个作者提交会替换该项目的“当前初稿”，需由管理者协调。

## 6. 显式启动与观察

下面命令开始一个保持前台的监督器。进入后发送 JSON 行；只有 `start` 才调用真实模型，检查账号和任务后再执行。不要在说明文档烟测中自动启动。

```powershell
& $telecomPython -X utf8 -m telecom_research --state "$stateRoot" supervise
```

输入示例中的 `runtime` 替换为实际 `$research.id`：

```json
{"op":"start","runtime":"实际研究运行时 id"}
{"op":"status","runtime":"实际研究运行时 id"}
```

同一监督器可对不同运行时发送多个 `start`。`stop` 停止该监督器拥有的进程树；`quit` 停止其余拥有的子进程并退出。管理器不会自动启动评委、自动转换阶段或生成桌面窗口。

另开管理 PowerShell 可查看 `Invoke-Telecom status --project $projectId` 和状态目录下 `runtime-<运行时id>.log`。监督器本身是 JSONL 接口，不要把交互式 `supervise` 输出交给前面的单次 JSON 函数。异常退出后的陈旧状态要核对，不能按旧 PID 盲目杀进程或重复启动。

## 7. 初稿提交与独立评审

研究会话可通过 MCP `submission_submit` 直接提交三个非空文本字段：`manuscript`、`evidence`、`plan`，每份小于 8 MiB。也可由管理者导入已经保存的真实文本文件：

```powershell
$draft = Invoke-Telecom submit --runtime $research.id --kind draft `
    --manuscript (Join-Path $researchDir 'draft.md') `
    --evidence (Join-Path $researchDir 'evidence.md') `
    --plan (Join-Path $researchDir 'experiment-plan.md')
$draftId = $draft.id
$reviewer = Invoke-Telecom runtime-create --project $projectId --role review --submission $draftId
$reviewDir = Join-Path $workRoot ('review-' + $reviewer.id)
Invoke-Telecom materialize --runtime $reviewer.id --harness claude `
    --profiles-root (Join-Path $telecomSource 'profiles') `
    --python-executable $telecomPython --destination $reviewDir
```

实际文件名由研究任务约定，缺文件时先找产物，不创建空文件糊弄提交。后端冻结文本及摘要；评委通过 `review_context` 读取分配版本，按 review Skill 独立联网检索，不能继承作者会话或提前阅读其他评委意见。给评审目录的 `CLAUDE.md`/`AGENTS.md` 说明任务为“独立初稿评审，先调用 review_context”，然后在监督器中显式启动它。

评审结构见 [report-fields.md](../profiles/review/skills/telecom-review/references/report-fields.md)。六项分数为 0–10，置信度 0–1，`pass` 不允许未解决 blockers；需真实检索轨迹。无检索能力可以提交 `insufficient`、空检索记录和无法评价的 `null` 分数，在理由中说明缺口，不编造访问记录。

评委用 MCP `review_submit` 直接提交；管理者也能导入评委真实生成的 JSON：

```powershell
Invoke-Telecom review --runtime $reviewer.id --report (Join-Path $reviewDir 'review-report.json')
Invoke-Telecom status --project $projectId
```

`revise/reject/insufficient` 不开放执行。评审已提交后不能修改历史意见；作者读取 `research_context` 的当前稿件/反馈，修改后重新 `submission_submit`，管理者为新提交创建新评审身份。所有已分配初稿评委都通过才可执行；增加尚未完成的评委会收回当前执行能力，直到该轮全部满足条件。

## 8. 执行阶段：准备、申请与真实结果导入

只有初稿已经真正通过时，以下命令才成功：

```powershell
$execution = Invoke-Telecom runtime-create --project $projectId --role execution
$executionDir = Join-Path $workRoot ('execution-' + $execution.id)
Invoke-Telecom materialize --runtime $execution.id --harness claude `
    --profiles-root (Join-Path $telecomSource 'profiles') `
    --python-executable $telecomPython --destination $executionDir
```

任务说明要求先调用 `execution_context`，取得批准初稿、实验计划、现有运行和返修信息。执行 Skill 准备代码、基线、环境校验和协议。通过 `experiment_submit` 或管理命令提交真实实验请求；`spec.json` 格式如下，实际参数与代码版本由获批方案决定：

```json
{
  "kind": "simulation",
  "name": "按批准方案命名的仿真实验",
  "code_revision": "实际代码提交或内容摘要",
  "config": {"按方案填写的非空参数对象": true}
}
```

```powershell
$run = Invoke-Telecom experiment-submit --runtime $execution.id --spec (Join-Path $executionDir 'spec.json')
$run.id
$run.status  # 本原型为 pending_unconfigured，不表示实验已执行
```

`experiment_submit` 目前不启动 Python/Sionna/ns-3/MATLAB，也不控制 USRP。真实计算在经核实的外部程序/Worker 完成后，由管理者导入结果。以下代码读取实际存在的指标与原始产物，不生成虚构指标：

```powershell
$artifactPath = (Resolve-Path -LiteralPath (Join-Path $executionDir 'actual-results.json')).Path
$actualMetrics = Get-Content -Raw -LiteralPath (Join-Path $executionDir 'actual-metrics.json') -Encoding utf8 | ConvertFrom-Json
$resultRecord = @{
    origin = 'simulated'  # 真仿真 simulated；硬件实测 measured；合成演示仅 synthetic 项目允许
    source = '填写实际运行环境、日志定位和执行来源'
    code_revision = $run.spec.code_revision
    config_hash = $run.config_hash
    metrics = $actualMetrics
    artifacts = @(@{
        path = $artifactPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
    })
}
$resultFile = Join-Path $executionDir 'result-import.json'
Write-Utf8Text -Path $resultFile -Content ($resultRecord | ConvertTo-Json -Depth 20)
Invoke-Telecom experiment-result --experiment $run.id --result $resultFile
```

先将 `source` 改为真实来源，确认指标来自实际产物后才导入。后端检查 origin、代码版本、配置摘要、绝对文件路径与 SHA256，复制不可变快照；已完成结果不能被覆写。它不会验证这些数字是否科学合理。`synthetic` 不能导入普通研究项目，不能把测试夹具包装成真实论文。

USRP 额外需要管理者登记实际设备配置和租约：`device-register --device <id> --config <真实配置.json>`，随后 `device-lease --device <id> --runtime <执行id> --seconds <时长>`。配置中的 `operator_approved=true` 必须来自实际负责人核验。硬件 spec 必须含同一 `device_id`、登记返回的 `device_config_hash`，以及完全一致的 `hardware_config`；普通 `config` 只放算法参数。租约失效或配置改变会拒绝请求。当前仍无设备驱动执行器，不能仅凭登记就发射。

## 9. 完整论文、终审与返修

有当前批准稿对应的已导入实验结果后，执行会话可用 `paper_submit` 交付完整论文；管理者也可以导入文本：

```powershell
$final = Invoke-Telecom submit --runtime $execution.id --kind final `
    --manuscript (Join-Path $executionDir 'paper.md') `
    --evidence (Join-Path $executionDir 'paper-evidence.md') `
    --plan (Join-Path $executionDir 'executed-protocol.md')
$finalReviewers = @()
for ($index = 0; $index -lt $project.final_quorum; $index++) {
    $finalReviewers += Invoke-Telecom runtime-create --project $projectId --role review --submission $final.id
}
```

分别物化每个终审身份，填写“完整论文独立评审”任务，显式启动。`review_context` 提供该提交关联的实验来源与快照，评委仍需实际检查和独立检索。默认终审至少两人；全部已分配评委完成且都 `pass` 才会进入 `complete`。分数不自动平均覆盖 blockers，内部完成不等于期刊录用。

返修时执行会话通过 `execution_context` 读取 `current_final`、反馈和运行记录，补论证/补实验/改文稿后提交新的 final；旧评审身份变陈旧，应重新分配。若改的是关键初稿假设或协议，先提交新 draft 并重审，旧执行授权将撤销。

当前终稿提交关联本批准稿下全部已完成运行；细粒度“只选某些运行支撑某个主张”的关系需要继续扩展。正文与指标逐句对应仍由 Skill、作者和评委核验。

## 10. 常见状态与恢复

| 现象 | 检查/处理 |
|---|---|
| 研究/评审看不到实验工具 | 预期阶段控制；查看当前初稿及已分配评审是否全部通过 |
| execution grant stale | 初稿改变；重审后创建新的执行身份和目录 |
| 评审只能见自己报告 | 预期独立性；主审/管理者可查看总体状态 |
| pending_unconfigured | 没有真实 Worker；需要外部执行与合规结果导入 |
| 初稿或终稿返修后丢上下文 | 使用 research_context/execution_context，不依赖旧会话记忆 |
| mcp 导入失败 | 核对生成计划使用的 Python 是否安装可选 SDK，`--python-executable` 是否正确 |
| Codex 没有文献工具/自定义模型 | 检查 ignore-user-config 与显式启动参数，按第 3 节修适配 |
| 修改 launch-plan.json 不生效 | 监督器读数据库计划，需重新物化/实现可信配置路径 |
| 源码 ZIP 无 Git 历史 | 正常；运行测试可继续，重新打包需真实干净 Git 仓库 |

`status --project <id>` 读取课题/评审，`audit` 读取管理审计，运行日志位于外部状态目录。日志和状态可能包含未公开研究内容，不能自动加入源码包。

## 11. 扩展入口与必须保留的约束

| 文件/对象 | 扩展位置 | 保留的约束 |
|---|---|---|
| `src/telecom_research/store.py` / `Store` | 项目状态、提交、评审政策、设备、运行与结果 | 后端凭据决定身份、当前版本检查、不可变快照、陈旧授权撤销 |
| `src/telecom_research/runtime.py` / `materialize` | 宿主 argv、角色模型、连接器合并、任务引导 | 仅当前 profile、显式凭据、无 shell 字符串拼接、不静默读取全部用户配置 |
| `runtime.py` / `Supervisor` | 并行会话、队列上限、恢复与监督 | 只终止自己拥有的进程树，不按未验证旧 PID 操作，不自动调用模型 |
| `src/telecom_research/mcp_server.py` | 工具 schema、描述与协议适配 | list 与 call 都检查能力；不能仅隐藏工具而放任直接调用 |
| `src/telecom_research/cli.py` | 管理命令、可信配置入口 | 管理权限不交给研究进程；结构化错误与结果 |
| `profiles/` | 通信方向、评审规则、实验协议与论文模板 | 三阶段分开、参考按需读取、无虚构结果、独立评审 |
| `tests/` | 新连接器、状态变化、异常与并发测试 | 测实际行为，不用删旧断言掩盖回归 |

建议下一步先做一种 harness 的真实文献调研闭环，再接一个真实通信仿真 Worker，最后接指定型号 USRP；这只是建设顺序建议。实际服务化可考虑独立管理服务、数据库/对象存储、GPU/设备 Worker，但当前包没有部署这些服务。改动应保留原插件独立性，并同步 Skills、schema、测试与交接文档。

## 12. 再次打包与交付

本目录附带 [package-telecom-research Skill](../.agents/skills/package-telecom-research/SKILL.md)，限定本仓库源码打包。可在本源码上下文使用；若希望在任意工作目录自然语言调用，由同事按自己的 Skill 安装方式安装该 Skill，运行时仍要定位并核实真实仓库路径。分发文本不硬编码原开发机器路径。

在真实、干净 Git 仓库中，默认生成完整源码包：

```powershell
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --repo <仓库> --output-dir <仓库外目录> --scope repository
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --verify <生成的ZIP> --repo <仓库>
```

用户明确只要通信项目时用 `--scope telecom`。归档包含源码、profiles、测试、许可、文档和 Skill；不打状态、令牌或虚拟环境。脏源码先保留并审查处理，不自动清理/提交或默默交付旧版本。打包器元数据不会替你运行测试，实际测试结果应另行说明。提供 ZIP、`.zip.sha256` 和本交接入口，不擅自上传或向未指定渠道发送。
