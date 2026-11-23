# 本体智能平台 Ontology Platform

[English](README.en.md)

AI Native 的开源本体平台。把资料和数据交给平台，AI 识别出业务概念、关系和约束，生成带证据的变更建议；人审核后发布为标准本体（RDF、OWL 2、SHACL、SKOS），再供查询、问答和外部智能体使用。

> 当前状态：**重建中（M0 新地基）**。功能按[路线图](docs/roadmap.md)逐步交付，下文"能做什么"描述的是目标。

## 能做什么

- **AI 识别资料**：上传规程、标准、报告等资料，AI 分阶段识别术语、对象类型与层级、关系与约束，每条建议附原文证据和置信度。
- **人审核，AI 不越权**：AI 的一切修改都以变更集提交，逐项接受、修改或拒绝后才生效；发布的每个版本都可对比、可回滚。
- **标准语义，可互通**：本体以 W3C 标准导入导出，可与 Protégé 等工具往返。
- **连接数据**：把对象类型绑定到数据库表（PostgreSQL、Oracle、Doris、TDengine、Web API），按本体浏览和查询真实数据，对业务系统只读。
- **AI 分析**：用自然语言提问，回答给出数据与资料出处、假设与反证。
- **给智能体用**：通过 MCP 把本体作为语义上下文提供给外部 AI 智能体。

第一个行业案例是钢铁冶金质量分析（炼钢、精炼、连铸、轧制），见 [samples/steel](samples/steel)。平台本身不含行业概念，欢迎贡献其他行业的案例。

## 快速开始（开发环境）

需要 Docker（含 Compose）与 PowerShell 7。

```powershell
./dev.ps1 up
```

浏览器打开 `http://<Docker 主机>:28080`，开发账号见 [docs/development.md](docs/development.md)。

## 文档

- [架构说明](docs/architecture.md)
- [界面规范](docs/ui-guidelines.md)
- [路线图](docs/roadmap.md)
- [开发手册](docs/development.md)
- [协作规则](AGENTS.md)

## 许可证

[Apache License 2.0](LICENSE)
