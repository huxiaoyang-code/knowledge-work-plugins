# 中国财税插件

基于 Anthropic 官方 finance 插件中国化改编，沿用插件清单、业务 Skill、连接类别和工作底稿格式。Agent自主判断和选择业务工具；本机中国财税后端负责已支持的计算、账务操作和自动调用记录，不要求手工事实登记或运行时任务图。来源和许可见 [SOURCES.md](SOURCES.md) 与 [LICENSE](LICENSE)。

## 安装与连接

```sh
claude plugin marketplace add huxiaoyang-code/knowledge-work-plugins
claude plugin install finance@knowledge-work-plugins-cn
```

先按 [连接说明](CONNECTORS.md)配置明确的本机后端、账库和记录目录。Pi使用同一finance MCP及本插件技能目录，由后端宿主生成器设置`--plugin-root <本finance目录绝对路径>`。配置文件存在不代表已连接；核对实际工具和目标。

## 业务入口

| 入口 | 用途 |
|---|---|
| `/finance:journal-entry` | 凭证草稿、支持计算和科目核对 |
| `/finance:reconciliation` | 总账、往来、银行、库存及资产差异 |
| `/finance:financial-statements` | 中国适用准则报表及期间比较 |
| `/finance:variance-analysis` | 金额差异、业务驱动及待调查项 |
| `/finance:internal-control-review` | 中国企业内控资料取样与异常核对 |
| `/finance:tax-review` | 增值税抵扣、季度小规模、所得税、工资个税、印花及其他税费依据 |

名称遵守实际Skill frontmatter；`journal-entry-prep`、`close-management`、`audit-support`按相关任务自动读取。原`sox-testing`已改为`internal-control-review`，不声称SOX为中国企业普遍义务。

## 核对方式

先明确企业、账套、期间、币种和业务，再选择需要的Skill与工具。月结日历与依赖是可调整业务参考，不强制编排。已有数据不足时列具体缺件；可支持部分照常核对，不能把独立模型计算冒充原生引擎已完成。

交付默认依次展示账本金额、凭证/计算结果、规则依据。调用链及输入原件始终自动保存，在深入排错时展开，见 [报告顺序](skills/shared/references/reporting.md)。本版本提供本机账税核对和申报依据；不进行税局登录、正式申报、缴款或开票。

完整季度业务见[完整账期与中文复核交付](skills/shared/references/quarter-review.md)。客户提供中文原始业务资料，读取时留原表结构、调用时留参数与规则映射；实际账库生成完整科目余额表、利润表、资产负债表、现金流量表及HTML/XLSX。工具未完成、未核或未分类的事项保留实际状态，不能把金额试算或模型计算升级为完整账务验收。

税率和公式统一由后端规则与计算工具维护。福建漳州是当前业务起点，具体地点、税务资格和地区参数须来自实际证据；地名不能替代市区分类或优惠资格。后端义务目录及限制见 [税费范围](skills/tax-review/references/supported-obligations.md)。

## 无模型验证

`node --test finance/tests/structure.test.mjs`检查插件结构、来源、业务引用和报告顺序。设置`TAXES_AGENT_ROOT`为对应后端绝对路径后，同一命令还会核真实29项工具合同，并经实际MCP逐份读取技能与业务参考；未提供后端时相应集成项明确跳过，不称已验证连接。该验证不调用Pi或任何模型。
