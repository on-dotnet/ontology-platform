# 工具、依赖与官方证据登记

核实日期2026-10-23。仅工程基线；没有引入产品包、安装OS工具或生成器。官方观察不是完整供应链审计；实际恢复、包哈希及完整漏洞扫描NOT_RUN。

| 项目 | 固定目标/用途 | 官方来源与许可 | 观察/验证边界 |
|---|---|---|---|
| .NET10 | SDK10.0.402 / 运行时10.0.13，未来后端 | [发布页](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)、[MIT及组件许可](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT) | 官方10月13日安全补丁；本机SDK10.0.401，目标未安装，BLOCKED |
| Node24 LTS | 24.22.1，未来Web及工具 | [安全发布](https://nodejs.org/en/blog/release/v24.22.1)、[安全公告](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)、[许可](https://github.com/nodejs/node/blob/main/LICENSE) | 10月21日安全发布；本机24.21.0落后；不全局升级 |
| pnpm11 | 11.28.8，工作区管理 | [发布](https://github.com/pnpm/pnpm/releases)、[MIT](https://github.com/pnpm/pnpm/blob/main/LICENSE)、[安全公告](https://github.com/pnpm/pnpm/security/advisories/GHSA-vq4v-j7r6-jq4m) | 本机11.25.0；目标高于该公告修复11.11.0，但不代表全量无漏洞；未安装目标 |
| dotnet-ef | 10.0.13局部工具目标 | [EF工具官方说明](https://learn.microsoft.com/en-us/ef/core/cli/dotnet)、[EF MIT](https://github.com/dotnet/efcore/blob/main/LICENSE.txt) | 不使用全局9.0.7；精确包元数据/下载及恢复未验证，NOT_VERIFIED；不生成工具锁定通过证据 |
| PowerShell | 本机7.6.5；脚本要求7+ | [官方仓库/MIT](https://github.com/PowerShell/PowerShell) | 实际执行静态检查；不是产品运行时依赖 |
| Codex | 本机0.163.0-alpha.11.2 | [配置官方](https://learn.chatgpt.com/docs/config-file/config-reference)、[角色官方](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[更新日志](https://learn.chatgpt.com/docs/changelog) | 官方索引与正文版本不一致，最新稳定精确版NOT_VERIFIED；不升级；角色实例化NOT_RUN |
| checkout | v7.0.1提交3d3c42e5aac5ba805825da76410c181273ba90b1 | [官方提交](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1)、[MIT](https://github.com/actions/checkout/blob/main/LICENSE) | CI仅此Action，contents:read、无持久凭证；远程执行前NOT_RUN |
| Aspire | 13.6.0研究基线，未安装 | [官方说明](https://aspire.dev/integrations/frameworks/javascript/) | PATH未发现；通用JavaScript路线获批，服务编排未执行 |
| Turbo | 2.11.10未来候选 | [发布/MIT](https://github.com/vercel/turborepo)、[安全公告](https://github.com/vercel/turborepo/security/advisories/GHSA-3qcw-2rhx-2726) | 本任务未安装/引用；保留turbo.json配置，不声称任务图运行；候选高于该公告修复2.9.14 |

MSTest/MTP、Kiota、Hey API均只批准验证原则/顺序，未选精确包、未安装、兼容PoC NOT_RUN。Next/React/Tailwind/shadcn/Base UI等保留冻结方向，但本轮不引包、不初始化页面。

根和apps/web清单均无真实包依赖，故没有pnpm-lock.yaml；无NuGet项目，故无packages.lock.json。首次引包时先登记、恢复真实依赖、检查完整性/漏洞，再提交锁图；不能手工伪造空锁。Directory.Packages.props只有CPM开关，不伪造未使用PackageVersion。

CI仅运行PowerShell静态门禁，不安装Node/.NET或执行OS升级。ubuntu-24.04为显式托管Runner系列而非不可变镜像digest，GitHub会维护镜像；远程运行需核实Runner兼容checkout实际运行时。供应链检查限于固定Action引用、源约束和有限机密模式，不宣称SBOM/完整依赖审计通过。
