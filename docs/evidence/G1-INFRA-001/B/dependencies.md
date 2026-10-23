# B 新增依赖登记

核验日期：2026-10-23。精确 NuGet 版本由 Master 维护根 CPM；AppHost SDK 和 MSTest SDK 版本显式写入工程。未运行供应链工具的部分均 NOT_VERIFIED，不把官方来源等同无漏洞。

| 依赖 | 精确版本 | 许可与用途 | 官方来源 |
|---|---|---|---|
| Aspire.AppHost.Sdk、Aspire.Hosting.AppHost、Aspire.Hosting.PostgreSQL | 13.6.3 | MIT；本地资源编排及 PG 就绪/数据库创建 | [Aspire](https://github.com/microsoft/aspire)、[NuGet](https://www.nuget.org/packages/Aspire.Hosting.AppHost/13.6.3) |
| Microsoft.Extensions.Http.Resilience、Microsoft.Extensions.ServiceDiscovery | 10.11.0 | MIT；HTTP 弹性与发现 | [dotnet/extensions](https://github.com/dotnet/extensions) |
| OpenTelemetry.Exporter.OpenTelemetryProtocol、OpenTelemetry.Extensions.Hosting、OpenTelemetry.Instrumentation.AspNetCore、OpenTelemetry.Instrumentation.Http、OpenTelemetry.Instrumentation.Runtime | 1.20.1 | Apache-2.0；OTLP 与宿主/HTTP/运行时遥测 | [OTel .NET](https://github.com/open-telemetry/opentelemetry-dotnet)、[contrib](https://github.com/open-telemetry/opentelemetry-dotnet-contrib) |
| MSTest.Sdk / Microsoft.Testing.Platform | 4.5.1 / 2.5.1 | MIT；TestingExtensionsProfile=None，避免默认启用未批准扩展 | [testfx](https://github.com/microsoft/testfx)、[test platform](https://github.com/microsoft/testfx/tree/main/src/Platform) |
| postgres 官方镜像 | 18.6-trixie | PostgreSQL License；平台空库及 Keycloak 独立开发库 | [官方镜像](https://github.com/docker-library/postgres)、[PG18布局](https://hub.docker.com/_/postgres) |
| quay.io/keycloak/keycloak | 26.8.1 | Apache-2.0；仅开发身份资源，不实现产品登录 | [容器](https://www.keycloak.org/server/containers)、[健康](https://www.keycloak.org/observability/health) |
| rustfs/rustfs | 1.0.3 | Apache-2.0；本地单节点 S3 资源 | [Docker部署](https://docs.rustfs.com/en/installation/container/docker)、[源码](https://github.com/rustfs/rustfs/tree/1.0.3) |
| Apache Jena Fuseki | 6.2.0 | Apache-2.0；TDB2 开发数据集，官方发行包自建 | [发行包](https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz)、[SHA512](https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz.sha512)、[官方Docker工具](https://jena.apache.org/documentation/fuseki2/fuseki-docker.html) |
| eclipse-temurin | 21.0.12.1_1-jre-jammy | OpenJDK GPLv2 + Classpath Exception；Java21 运行时。发行包与OS层复合许可待完整SBOM审计 | [官方镜像](https://hub.docker.com/_/eclipse-temurin)、[构建来源](https://github.com/adoptium/containers) |

## 核验事实与边界

- Jena tar.gz 的官方 SHA-512：ba65f5867d2d4741b2ed9e2af5a0d4fbb447909894ab2a0c6bc4dac8997f4fe339c87b13c48d45d054977769f0f8bf763ea346b1f7792d5cdc458041bd43a132。Dockerfile 通过 sha512sum --check --strict 强制匹配。
- docker buildx imagetools inspect eclipse-temurin:21-jre-jammy 实际 exit0，报告版本21.0.12.1_1-jre-jammy，OCI索引 sha256:affcab5356e1270ac35d2361ee83135af2f03e8d580eca78a6d5d6fdbf048db0；Dockerfile 固定版本及该摘要。
- NuGet 恢复后生成项目 packages.lock.json；锁定恢复与漏洞审计结果见 validation.md。新引入传递依赖只按真实锁图登记，不伪造锁。
- 容器镜像 CVE 全量扫描、OS层 SBOM/复合许可清单、生产安全评估均 NOT_VERIFIED；开发启动成功不能替代这些工作。Keycloak 仅本地 start-dev；Fuseki 开发更新端点没有业务认证，不能用于正式发布。
- RustFS 就绪探针只能证明其报告就绪，不能替代实际 S3 写读/重启持久化测试。Keycloak 数据库健康须启用 metrics，管理健康端口9000，官方镜像中无 curl。
