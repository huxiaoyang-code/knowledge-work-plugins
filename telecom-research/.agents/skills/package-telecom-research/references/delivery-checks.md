# 本仓库交付检查

## 仓库身份与状态

以用户路径或当前目录定位后，分别执行并检查：

```text
git -C <仓库> rev-parse --show-toplevel
git -C <仓库> remote get-url origin
git -C <仓库> status --porcelain=v1 --untracked-files=all
git -C <仓库> rev-parse HEAD
git -C <仓库> ls-tree HEAD bio-research telecom-research
git -C <仓库> show HEAD:telecom-research/pyproject.toml
```

来源必须为 `huxiaoyang-code/knowledge-work-plugins`，且 Git 快照中有原 `bio-research`、通信项目包标记和打包脚本。sparse checkout 可隐藏原目录，通过 Git 树核验即可，不因磁盘未检出目录而拒绝正确仓库或要求完整检出。交付包由已审查的干净 Git 快照生成；忽略的本地运行数据不应纳入源码，意外被忽略的待交付源码应先修正流程，不能假定自动归档。

`--ref` 必须等于当前干净 `HEAD`，可用完整 SHA 锁定已验证提交。交付历史版本时先在独立工作区准备并验证它；测试当前工作区的结果不能冒充另一个历史提交的测试结果。

## 测试与依赖

核心后端需要 Python 3.11+。完整 MCP 传输测试需要 `mcp>=1.20,<2`；在已配置环境运行，或在仓库外的专用环境安装。不要读取用户模型密钥；这些测试使用合成数据和替代子进程。

先确认测试解释器导入的 `telecom_research.__file__` 位于本次已核实的源码副本，而非旧版或其他工作区；必要时在专用环境用 `python -m pip install -e "<仓库>/telecom-research[mcp]"` 安装此副本。依赖安装需要可用的软件源，失败如实报告，不更换为无关已安装版本来取得通过。

从通信目录或用绝对路径运行：

```powershell
python -X utf8 -m unittest discover -s <仓库>/telecom-research/tests -v
```

记录实际测试数量、失败和跳过原因。缺 MCP 时可报告核心测试通过、传输检查未运行；不得宣传为已完成宿主/硬件联调。有可用 `skill-creator` 时检查四个阶段 Skills 和本打包 Skill；结构验证结果不等于科研质量通过。

## 打包脚本接口

```text
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --repo <仓库> --output-dir <外部目录> [--scope repository|telecom] [--ref <当前HEAD完整SHA>]
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --verify <ZIP> [--repo <仓库>]
```

`repository` 为默认范围，包含全部原插件和独立通信目录。`telecom` 为用户明确要求的通信项目单独包。包根名包含版本与提交短摘要，ZIP 外另有 `.zip.sha256`。

脚本拒绝脏源码。收到该错误时保留现场，检查实际状态；不要尝试改用只打旧提交、排除文件或递归清理来掩盖用户修改。

## 元数据与验证含义

`PACKAGE-METADATA.json` 记录 `repository_url`、完整 `commit`、`branch`、`version`、`scope`、`archive_root`、提交时间 `snapshot_time`、交接入口 `handoff_entrypoint` 及 `source`/`validation`。`snapshot_time` 是提交时间，不是虚构的测试时间。

`files` 为每个源码文件记录包内路径、原仓库路径、Git 模式/对象、字节数和 SHA256；`generated_files` 单独记录根目录 `START_HERE_FOR_CODEX.md` 等生成入口的路径、字节数和摘要。元数据本身不递归列入自己的清单。验证应确认包内容恰好是源码清单、生成文件清单和元数据。

验证输出包括 `ok`、`archive`、`commit`、`scope`、`file_count`、`source_verified`、`sha256`、`sidecar_verified`。只有带 `--repo` 并成功完成 Git 对象比对时，才报告源码与原提交一致；不带该参数的包内校验不证明来源真实性。

## 给同事的简短说明

明确包中保留原插件，通信项目在 `telecom-research/`（或通信专用包根）。请对方 Codex 读取交接入口与 `AGENTS.md`，完成环境检查、依赖安装及真实测试，再确认账号/模型、检索工具和设备条件。不要发送状态库、模型认证、设备凭据、虚拟环境或研究原始数据。
