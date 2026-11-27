# 本体智能平台 Ontology Platform

[English](README.en.md)

开源的本体平台。用户提交资料和数据，AI 识别业务概念并提出带证据的修改；人审核后发布标准本体，供查询、问答和外部智能体使用。

## 能做什么

- 上传资料，让 AI 识别术语、对象类型、关系和属性，生成带原文证据的变更集。
- 逐项审核变更集，把接受的修改合并到工作版本，再发布本体版本。
- 导入和导出 RDF、OWL 2、SHACL、SKOS 内容，并与 Protégé 往返。
- 把本体元素绑定到 PostgreSQL 表和列，按本体查询对象、沿关系浏览数据；外部数据源只读。
- 用访问令牌通过 MCP 读取本体、查询对象，或提交待审核的变更提议。
- 从已发布的绑定导出 R2RML 映射。
- 用自然语言提问，查看答案的本体、数据和资料依据。
- 定义指标与规则，在探索页查看计算和校验结果。
- 把问答发现的本体缺口生成待审核的变更提议。
- 记录本体应能回答的能力问题，并在发布后检验答案。

第一个行业案例是[钢铁冶金](samples/steel)。后续计划见[路线图](docs/roadmap.md)。

## 快速开始

需要 Docker（含 Compose）和 PowerShell 7；AI 识别与问答需要模型 API Key。按[快速上手](docs/quickstart.md)了解本机配置，再从仓库根目录运行：

```powershell
./dev.ps1 init-env
./dev.ps1 up
./dev.ps1 status
```

打开 `http://<OP_DEV_HOST>:28080`（端口可由 `OP_WEB_PORT` 覆盖）；开发账号见[开发手册](docs/development.md)。

## 文档

- [快速上手](docs/quickstart.md)
- [贡献指南](CONTRIBUTING.md)
- [架构说明](docs/architecture.md)
- [界面规范](docs/ui-guidelines.md)
- [路线图](docs/roadmap.md)
- [开发手册](docs/development.md)
- [协作规则](AGENTS.md)

## 许可证

[Apache License 2.0](LICENSE)
