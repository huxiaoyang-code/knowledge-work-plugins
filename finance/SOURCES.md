# 来源、许可与中国化修改

上游：[anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins/tree/2574e29377c7173d0cecffef29a6ecbd7f8ccb5d)，固定提交`2574e29377c7173d0cecffef29a6ecbd7f8ccb5d`，原finance插件版本1.3.0。中国化维护仓库为[huxiaoyang-code/knowledge-work-plugins](https://github.com/huxiaoyang-code/knowledge-work-plugins)。本项目不代表Anthropic对中国财税规则或结果背书。

2026-10-30修改：改编原8个finance Skill的触发描述、业务工作流、模板和复核方法；将`sox-testing`更名`internal-control-review`；替换美国ASC/GAAP、工资税及SOX默认适用表述，改用实际中国会计准则和已核中国规则；新增税费核对与按需参考。保留月结日历及依赖作为可调整指导，不建立运行时DAG。连接配置改为本机中国财税MCP，移除未配置和不相关的上游服务器。报告改为金额、凭证/计算、规则优先，调用和原件可深入索引。

原文件路径：`finance/skills/{journal-entry,journal-entry-prep,reconciliation,financial-statements,variance-analysis,close-management,audit-support,sox-testing}/SKILL.md`，以及`finance/README.md`、`CONNECTORS.md`、`.mcp.json`和`.claude-plugin/plugin.json`。各改编文件保留修改声明；本目录[LICENSE](LICENSE)为上游Apache-2.0原文，不翻译。上游finance及所采用文件目录未提供额外NOTICE；其他插件内容未改编。

2026-10-31修改：再次逐项核对固定基线的financial-statements、journal-entry-prep与reconciliation原文，保留资料收集、报表比较和差异、常见凭证支持、两侧余额调节及复核方法；移除原生工作底稿、JSON绑定和季度bundle作为交付必经路径。模型自主选择Python、表格或可选计算器，系统记录实际计算，派生账簿与原生入账状态分列；用户产物使用中文。

中国法规、准则、税率和地区条件按需取自已核官方资料或taxes-agent可选规则服务，保留本次适用依据；引擎实现及接口能力以实际后端为准。上游通用方法不是中国税法依据；这里只引用工作方法，不从上游示例推定适用政策。
