# 工具连接

插件沿用官方 `~~category` 类别引用格式：它表示已连接的工具类别，不是可执行工具名。MCP配置见 [.mcp.json](.mcp.json)。没有连接的类别须保留缺项，不能报告为已调用。

| 类别 | 占位 | 本中国化版本的实际接入 |
|---|---|---|
| ERP/中国财税 | `~~erp` | 本机 taxes-agent 的 finance MCP，profile为`direct`；账套、凭证、查询、报表和已支持税费 |
| 规则与税费 | `~~tax tools` | 同一finance MCP的`finance_rules`、`finance_tax_calculate`、`finance_tax_summary_calculate`、`finance_record_contract` |
| 业务底稿 | `~~workpapers` | 可选`finance_workpaper`、`finance_annual_workpaper`；模型也可自主计算 |
| 自主计算记录 | `~~workpapers` | `finance_calculation_run`执行Python/JavaScript并记录脚本、输入原件快照、结果与中文计算记录/文件索引页 |
| 完整季度账目 | `~~erp` / `~~workpapers` | 可选`finance_quarter_review`读取真实账库；也可由Python/表格直接交付完整派生账表。草稿/FIFO可按`finance_workpaper_details`分页查询 |
| 文档/表格 | `~~documents` / `~~spreadsheets` | 按宿主实际解析/表格工具及本次授权使用；模型可直接生成含公式工作簿或配套计算脚本 |
| 数据仓库/沟通 | `~~data warehouse` / `~~chat` / `~~email` | 本版本不预配；确有需要时由操作者另接，不以官方示例地址表示已经连接 |

## 运行配置

由操作者明确提供`TAXES_AGENT_ROOT`（后端仓库绝对路径）、`FINANCE_DATABASE_PATH`（目标SQLite绝对路径）、`FINANCE_API_BASE`（本次后端实际loopback端口地址）和`FINANCE_AUDIT_DIR`（独立本机记录目录）。`node`须满足后端运行资格。Claude加载插件时`CLAUDE_PLUGIN_ROOT`指向本finance目录；Pi使用后端宿主生成器的`--plugin-root <finance绝对路径>`，生成实际技能目录，不依赖Claude变量。

`.mcp.json`仅连接已实现的本机服务，不含密钥，不修改用户全局配置。精确的参数、可用工具和支持状态以当前后端schema为准；正常业务无需`harness_*`、Store、事实登记或DAG。原有开票、税局登录、在线采集、申报提交和缴款未接通，本插件不把占位工具列作可用。

## 按任务选择工具

- 已有账库任务用`account_context`核实账套，`finance_query`或`ledger_query`取实际账簿。
- `finance_record_contract`按需要取得某种业务记录合同；可选`finance_workpaper`计算原件支持的业务，不先做元数据编排。
- 按需用`finance_rules`或已核官方资料取得中国规则、来源、期间和限制；可选`finance_tax_calculate`，缺件保留原生状态。工具字段缺口不证明企业事实缺失。
- `finance_tax_summary_calculate`独立处理有来源税务汇总的条件试算；按需读`finance_record_contract(recordType=tax_summary)`，输入绑定精确JSON位置，不要求编造完整业务记录，试算不等于完整账或资格已核。
- `voucher_check`校验明确分录；凭证、资产、导入、期间等写入只通过实际业务工具及本次授权。

使用已连接工具时系统记录实际调用过程；自主计算优先使用下述记录入口，记录能力未接通或失败时如实披露。金额、凭证和规则优先显示，调用与原件通过本机引用深入查看；字段和回读工具以实际返回为准，不猜引用路径或内部ID。

普通账簿/凭证工具仍连接该明确的本机HTTP后端：先按taxes-agent运行资格与启动说明启动所选数据目录，记录实际监听端口，再设置`FINANCE_API_BASE`。宿主生成器的`--api-base`应与它一致，`--database`应指向同一后端数据目录；不能用默认8787代替现场端口或将计算工具连到另一账库。配置、原生无模型加载、合成业务和模型测试分别核验。

本机客户端不等于模型离线；真实账库、原件与个人明细只在本次获准范围使用。完整本机结果与调用记录并不自动成为允许外发给模型的内容。

## 可选原生计算器的合同

仅选择`finance_workpaper`或`finance_tax_calculate`时，按其合同提交`{target:{accountSetId,period},originals:[{id,path}],records:[...]}`：账套ID来自实际查询，后台据`FINANCE_DATABASE_PATH`或明确`dbPath`绑定真实企业及数据库实例。记录的`enterpriseKey`可省略，显式身份冲突会拒绝；不要求客户提供内部scope或manifest。原显式scope与manifestPath保留兼容，三种载体不混合；年度工具仍用真实`manifestPaths`。同一主体事实跨期应共享同一原件/事实文件引用，不复制成不同来源版本。

`finance_record_contract`可按需发现原生类型，并明确`contractCompleteness`。`verified_fields_with_conditional_native_validation`为已核字段说明，仍受实际条件校验；`common_schema_and_rule_references_only`表示目前仅通用结构和原生规则引用，专用字段未完整披露，不表示算法未实现。没有完整示例不能直接判引擎不支持；应记录具体披露缺口，不猜字段，也不据此要求企业补造资料。原生专供生成的`inputRole:native_generated_only`不可由Agent伪造。

## 自主计算及系统记录

业务计算可自主选择Python、表格公式或已有计算器；不要求先用`finance_workpaper`、精确JSON绑定或原生季度导出。普通读算产出不要求建立账库，正式写账仍遵守现有工具控制。

`finance_calculation_run`可执行并记录自主计算，业务账簿、四表和中文复核材料由脚本或表格生成。文件来源须位于获准的`FINANCE_SOURCE_ROOT`；仅Python执行需要`FINANCE_PYTHON_PATH`绝对路径，宿主继承这些环境变量。完整字段、脚本读取参数、输出索引及记录边界按需见[自主计算及系统记录](skills/shared/references/connectors.md#自主计算及系统记录)。
