# Knowledge Work Plugins

本仓库是 Anthropic knowledge-work-plugins 的中国化 fork。首批改造 [finance 中国财税插件](finance/README.md)，连接本机中国财税工具，使用 `knowledge-work-plugins-cn` marketplace；其他插件保留上游内容。来源与修改见 [finance/SOURCES.md](finance/SOURCES.md)。

中国财税插件按 [finance 安装与连接](finance/README.md#安装与连接)接入，并先配置[本机后端、账库和调用记录目录](finance/CONNECTORS.md)。默认使用 direct MCP，自动记录调用；有来源汇总可按合同作独立条件试算，不能据此声称完整账务或正式申报已完成。

以下英文介绍保留上游插件集合的背景；中国 finance 的实际能力、连接器和运行依赖以上述中文入口为准。

Plugins that turn Claude into a specialist for your role, team, and company. Built for [Claude Cowork](https://claude.com/product/cowork), also compatible with [Claude Code](https://claude.com/product/claude-code).

## Why Plugins

Cowork lets you set the goal and Claude delivers finished, professional work. Plugins let you go further: tell Claude how you like work done, which tools and data to pull from, how to handle critical workflows, and what slash commands to expose — so your team gets better and more consistent outcomes.

Each plugin bundles the skills, connectors, slash commands, and sub-agents for a specific job function. Out of the box, they give Claude a strong starting point for helping anyone in that role. The real power comes when you customize them for your company — your tools, your terminology, your processes — so Claude works like it was built for your team.

## Plugin Marketplace

We're open-sourcing 11 plugins built and inspired by our own work:

| Plugin | How it helps | Connectors |
|--------|-------------|------------|
| **[productivity](./productivity)** | Manage tasks, calendars, daily workflows, and personal context so you spend less time repeating yourself. | Slack, Notion, Asana, Linear, Jira, Monday, ClickUp, Microsoft 365 |
| **[sales](./sales)** | Research prospects, prep for calls, review your pipeline, draft outreach, and build competitive battlecards. | Slack, HubSpot, Close, Clay, ZoomInfo, Notion, Jira, Fireflies, Microsoft 365 |
| **[customer-support](./customer-support)** | Triage tickets, draft responses, package escalations, research customer context, and turn resolved issues into knowledge base articles. | Slack, Intercom, HubSpot, Guru, Jira, Notion, Microsoft 365 |
| **[product-management](./product-management)** | Write specs, plan roadmaps, synthesize user research, keep stakeholders updated, and track the competitive landscape. | Slack, Linear, Asana, Monday, ClickUp, Jira, Notion, Figma, Amplitude, Pendo, Intercom, Fireflies |
| **[marketing](./marketing)** | Draft content, plan campaigns, enforce brand voice, brief on competitors, and report on performance across channels. | Slack, Canva, Figma, HubSpot, Amplitude, Notion, Ahrefs, SimilarWeb, Klaviyo |
| **[legal](./legal)** | Review contracts, triage NDAs, navigate compliance, assess risk, prep for meetings, and draft templated responses. | Slack, Box, Egnyte, Jira, Microsoft 365 |
| **[finance](./finance)** | 中国财税：凭证、对账、报表、差异、月结、审计支持及税务核对；范围见中文入口。 | 本机 taxes-agent direct MCP；其他类别按实际连接核实 |
| **[data](./data)** | Query, visualize, and interpret datasets — write SQL, run statistical analysis, build dashboards, and validate your work before sharing. | Snowflake, Databricks, BigQuery, Definite, Hex, Amplitude, Jira |
| **[enterprise-search](./enterprise-search)** | Find anything across email, chat, docs, and wikis — one query across all your company's tools. | Slack, Notion, Guru, Jira, Asana, Microsoft 365 |
| **[bio-research](./bio-research)** | Connect to preclinical research tools and databases (literature search, genomics analysis, target prioritization) to accelerate early-stage life sciences R&D. | PubMed, BioRender, bioRxiv, ClinicalTrials.gov, ChEMBL, Synapse, Wiley, Owkin, Open Targets, Benchling |
| **[cowork-plugin-management](./cowork-plugin-management)** | Create new plugins or customize existing ones for your organization's specific tools and workflows. | — |

Install these directly from Cowork, browse the full collection here on GitHub, or build your own.

## Getting Started

### 本 fork 的中国财税插件

```bash
claude plugin marketplace add huxiaoyang-code/knowledge-work-plugins
claude plugin install finance@knowledge-work-plugins-cn
```

安装后继续完成 [finance 连接配置](finance/CONNECTORS.md)，核对实际 MCP 工具和目标账库。Pi 使用后端宿主生成器的 `--plugin-root <finance绝对路径>`。下列 Cowork 与 Claude Code 示例保留为上游插件安装方式，不会安装本 fork 的中国 finance。

### Cowork

Install plugins from [claude.com/plugins](https://claude.com/plugins/).

### Claude Code

```bash
# Add the marketplace first
claude plugin marketplace add anthropics/knowledge-work-plugins

# Then install a specific plugin
claude plugin install sales@knowledge-work-plugins
```

Once installed, plugins activate automatically. Skills fire when relevant, and slash commands are available in your session (e.g., `/sales:call-prep`, `/data:write-query`).

## How Plugins Work

Every plugin follows the same structure:

下图保留上游结构示意；本 fork 的 finance 使用 `skills/` 作为业务入口，具体目录见 [finance/README.md](finance/README.md)，不要求存在 `commands/`。

```
plugin-name/
├── .claude-plugin/plugin.json   # Manifest
├── .mcp.json                    # Tool connections
├── commands/                    # Slash commands you invoke explicitly
└── skills/                      # Domain knowledge Claude draws on automatically
```

- **Skills** encode the domain expertise, best practices, and step-by-step workflows Claude needs to give you useful help. Claude draws on them automatically when relevant.
- **Commands** are explicit actions you trigger (e.g., `/finance:reconciliation`, `/product-management:write-spec`).
- **Connectors** wire Claude to the external tools your role depends on — CRMs, project trackers, data warehouses, design tools, and more — via [MCP servers](https://modelcontextprotocol.io/).

上游插件配置主要由 Markdown 与 JSON 文件组成。本 fork 的 finance 另有结构与集成测试，并依赖已启动的本机财税后端；插件安装本身不等于后端、账库或业务能力已经接通。

## Making Them Yours

These plugins are generic starting points. They become much more useful when you customize them for how your company actually works:

- **Swap connectors** — Edit `.mcp.json` to point at your specific tool stack.
- **Add company context** — Drop your terminology, org structure, and processes into skill files so Claude understands your world.
- **Adjust workflows** — Modify skill instructions to match how your team actually does things, not how a textbook says to.
- **Build new plugins** — Use the `cowork-plugin-management` plugin or follow the structure above to create plugins for roles and workflows we haven't covered yet.

As your team builds and shares plugins, Claude becomes a cross-functional expert. The context you define gets baked into every relevant interaction, so leaders and admins can spend less time enforcing processes and more time improving them.

## Contributing

Plugins are just markdown files. Fork the repo, make your changes, and submit a PR.
