# Wave2 依赖来源/许可与批准范围

2026-10-25 Master只读查询官方NuGet/npm metadata。维持SDK10.0.402、Node24.22.1、pnpm11.28.8、Aspire13.6.3、OTel1.20.1。下列依赖对应本轮明确批准的OIDC/YARP/EF Core+PG/Next/React/Tailwind/Base UI/测试技术栈，不引第二套框架。

| 精确依赖 | 来源/许可 | 用途及替代 |
|---|---|---|
| Microsoft.AspNetCore.Authentication.OpenIdConnect/OpenApi、Microsoft.EntityFrameworkCore/Design 10.0.13 | nuget.org / MIT | 内置微软方案，OIDC/OpenAPI3.1、EF模型及迁移工具；不换SDK主版本 |
| Yarp.ReverseProxy2.3.0 | 微软YARP官方NuGet/GitHub / MIT | 已明确批准同源BFF Web代理 |
| Npgsql.EntityFrameworkCore.PostgreSQL10.0.3 | 官方Npgsql NuGet、github.com/npgsql/efcore.pg / PostgreSQL license | 已批准EF Core+PostgreSQL的必要官方provider；.NET无内置PG provider，不是新架构/Repository层。实施前核实实际nuspec/EF兼容图、漏洞与许可 |
| Microsoft.OpenApi.Kiota1.36.1 | 官方NuGet / MIT | 项目隔离真实客户端PoC工具，非全局安装；当前TS官方运行包latest为1.0.0-preview.111，不直接采用预览runtime，不引Hey API。以PoC/ADR记录内置fetch+OpenAPI类型适配取舍 |
| Next16.4.3、React/ReactDOM19.3.1、Tailwind/@tailwindcss/postcss4.3.3、@base-ui/react1.9.0 | 官方npm / MIT | 批准Web/DesignSystem线，shadcn风格自研组件，无商业模板源码/图像、无新增图标库 |
| Playwright1.64.1、TypeScript7.0.2 | 官方npm / Apache-2.0 | 批准的浏览器验收/类型工具 |
| Vitest5.0.5、ESLint10.13.0、eslint-config-next16.4.3 | 官方npm / MIT | 分离真实test/lint，与实际peer兼容及恢复结果为准 |

最新版本只作官方观察，真实批准采用精确上表版本且恢复peer/哈希/漏洞必须验证；若不兼容提出基于官方稳定线的最小修订并登记，不能擅自浮动升级。全部传递依赖许可/漏洞与镜像digest/SBOM在恢复/OBS提案后补实际清单；目前NOT_VERIFIED，不把registry发布当运行PASS。新专业组件容器仅Alloy/Loki/Tempo/Prometheus/Grafana，本地部署，OBS登记精确官方稳定版/ARM64 index digest/许可后Master审核，禁止Cloud或额外框架。
