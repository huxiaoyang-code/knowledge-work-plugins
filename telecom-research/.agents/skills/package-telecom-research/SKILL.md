---
name: package-telecom-research
description: 为 huxiaoyang-code/knowledge-work-plugins 仓库中的通信研究项目打包并校验源码交付；用于该项目的“打包”“发给同事”“交付源码”请求。默认包含完整仓库与原有插件。
---

# 通信研究源码交付

只处理 `https://github.com/huxiaoyang-code/knowledge-work-plugins` 中包含 `telecom-research/` 的源码交付。使用仓库自带脚本生成可追溯源码包，不复制一套打包逻辑。

## 定位并确认源码

从用户明确路径或当前目录/其 Git 根目录定位仓库。个人安装的本 Skill 不携带源码，不把 Skill 安装目录当成仓库。当前会话已核实的源码路径可复用；仍无法定位时只询问该仓库路径，不扫描用户全部磁盘。

核对 Git 根、`origin` 的规范化 GitHub 地址及本仓库标记：Git 当前快照中有 `bio-research/`、`telecom-research/pyproject.toml` 中项目名为 `telecom-research-control`，且有 `telecom-research/scripts/package_source.py`。通过 `git ls-tree`/`git show` 核对快照标记；sparse checkout 隐藏原插件目录时不要求其在磁盘上可见。允许等价 HTTPS/SSH 和 `.git` 后缀；拒绝其他所有者或仓库。若是没有 `.git` 的解压源码，可读取 `PACKAGE-METADATA.json` 验证身份并运行/校验原包，但不能假装拥有原 Git 快照来重新打包。不要自动初始化或替换 Git 历史。

## 明确交付范围

默认 `--scope repository`：包含快照中所有原插件、通信目录源码、profiles、测试、文档、许可及本 Skill。用户明确只要通信目录时才使用 `--scope telecom`。不是只打补丁、已改文件、wheel 或生成产物。

输出目录放仓库外；使用用户指定目录，或会话已有的交付目录。没有偏好时选仓库同级的交付目录并说明，无须为可逆本地打包反复确认。

## 检查、打包、校验

按 [delivery-checks.md](references/delivery-checks.md) 检查状态和依赖，实际运行本地测试并记录通过/失败/跳过。真实模型、网络文献服务和设备不属于打包烟测，不自动启动。

打包前要求已跟踪工作区及非忽略未跟踪源码干净。若有修改，先看实际差异和当前任务授权，保留文件；不能把旧 `HEAD` 包冒充包含当前改动的交付物。按已有授权协调审查与提交，或说明阻塞并只询问缺失的处理决定。不要自动清理、stash、提交、合并或改 `.gitignore` 掩盖待交付内容。

在源码副本执行，路径作为独立参数传入：

```powershell
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --repo <仓库> --output-dir <外部交付目录> --scope repository
python -X utf8 <仓库>/telecom-research/scripts/package_source.py --verify <生成的ZIP> --repo <仓库>
```

默认快照是干净工作区的 `HEAD`；已锁定验证提交时可传其完整 `--ref` SHA，脚本要求它仍等于当前 `HEAD`。要交付历史版本应先在独立工作区准备并验证该版本，不能用当前测试冒充历史快照验证。脚本基于 Git 对象生成清单，不依赖 sparse checkout 当前显示的文件。默认完整仓库包必须保留 `telecom-research/`；通信专用包则让完整通信项目位于包根目录。

检查 ZIP 摘要、`.zip.sha256`、`PACKAGE-METADATA.json`、文件清单及 `handoff_entrypoint`。根目录生成的 `START_HERE_FOR_CODEX.md` 应指向正确范围的 AGENTS 和交接指南，并单独列在生成文件清单。用 `--repo` 的验证可与实际 Git 快照比对；无仓库的 `--verify` 只能证明包内结构和摘要一致。最终交付前确认源码不含本地状态、令牌、虚拟环境或运行日志；脚本安全扫描不能代替对新纳入源码的合理检查。

## 交付说明

返回源码 ZIP 和 SHA256 校验文件的可用链接，简述范围、版本、完整提交、校验状态和测试结果。告诉同事的 Codex 从元数据的 `handoff_entrypoint` 与通信目录 `AGENTS.md` 开始，特别说明仍需配置模型账号、文献源和实验后端。

脚本元数据的 `validation.tests` 是 `not_run_by_packager`，不得改写为已通过；另行报告本次真实运行的测试。失败不包装成成功，跳过项和真实宿主未联调要如实写明。用户要求本地打包不自动授权推送、合并、发布、上传或向外部收件人发送。
