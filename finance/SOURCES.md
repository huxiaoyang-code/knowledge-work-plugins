# 来源、许可与中国化修改

上游：[anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins/tree/2574e29377c7173d0cecffef29a6ecbd7f8ccb5d)，固定提交`2574e29377c7173d0cecffef29a6ecbd7f8ccb5d`，原finance插件版本1.3.0。中国化维护仓库为[huxiaoyang-code/knowledge-work-plugins](https://github.com/huxiaoyang-code/knowledge-work-plugins)。本项目不代表Anthropic对中国财税规则或结果背书。

2026-10-30修改：改编原8个finance Skill的触发描述、业务工作流、模板和复核方法；将`sox-testing`更名`internal-control-review`；替换美国ASC/GAAP、工资税及SOX默认适用表述，改用实际中国会计准则和后端规则；新增税费核对与按需参考。保留月结日历及依赖作为可调整指导，不建立运行时DAG。连接配置改为本机中国财税MCP，移除未配置和不相关的上游服务器。报告改为金额、凭证/计算、规则优先，调用和原件可深入索引。

原文件路径：`finance/skills/{journal-entry,journal-entry-prep,reconciliation,financial-statements,variance-analysis,close-management,audit-support,sox-testing}/SKILL.md`，以及`finance/README.md`、`CONNECTORS.md`、`.mcp.json`和`.claude-plugin/plugin.json`。各改编文件保留修改声明；本目录[LICENSE](LICENSE)为上游Apache-2.0原文，不翻译。上游finance及所采用文件目录未提供额外NOTICE；其他插件内容未改编。

中国法规、准则、税率、地区条件和引擎实现来自单独的taxes-agent后端及其当前规则来源。上游通用方法不是中国税法依据；这里只引用工作方法，不从上游示例推定适用政策。
