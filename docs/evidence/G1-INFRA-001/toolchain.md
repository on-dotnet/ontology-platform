# C · 工具链调查与隔离准备

2026-10-23；Master执行隔离准备，只读研究Agent infra_toolchain_research核实官方资料。旧G1-ENG doctor exit2保持历史事实，不重写。

## 实际结果

| 项目 | 目标与结果 | 证据/边界 |
|---|---|---|
| .NET SDK | 10.0.402，已下载到忽略目录.tools/dotnet并存解压，list-sdks实际输出10.0.402，退出0 | 官方zip SHA512实测匹配；不执行OS安装器、不改默认SDK |
| Node | 24.22.1，.tools/node-v24.22.1-win-x64，实际--version匹配，退出0 | 官方zip SHA256实测匹配；未改全局Node |
| pnpm | 11.28.8，.tools/pnpm/package/bin/pnpm.cjs配项目Node，实际版本匹配，退出0 | npm官方tarball SHA512 integrity实测匹配，MIT；未安装standalone内嵌Node26版本 |
| Docker | 客户端和宿主server均29.8.2；提升只读info退出0 | 原沙箱管道拒绝退出1不等于daemon未启动；未安装/启动Docker或修改WSL |
| Aspire CLI | PATH未发现，NOT_RUN | AppHost通过精确SDK/包运行，不强制全局CLI安装 |
| 局部EF | 项目manifest恢复10.0.13，tool run dotnet-ef --version实测10.0.13，退出0 | DOTNET_CLI_HOME/NUGET_PACKAGES均项目隔离；无迁移命令，不使用全局9.0.7冒充 |

doctor新增只读项目工具优先解析，支持-ToolRoot指定已准备目录，-CheckDocker显式检测daemon。只在调用进程传入DOTNET_CLI_HOME/NUGET_PACKAGES等隔离位置，不修改用户/机器PATH或默认工具。

## 官方发行物与实际校验

- SDK：[zip](https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.402/dotnet-sdk-10.0.402-win-x64.zip)，[官方metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json)。SHA512：`ae4fd528cb7e9f6af6aaf7de36715a69f761f183744f1bb3025d19f5a92447090ec561410e46266c1d10a63781ed6f3de771760bc76c876d87daabc367b898cd`。
- Node：[zip](https://nodejs.org/dist/v24.22.1/node-v24.22.1-win-x64.zip)，[安全发布说明](https://nodejs.org/en/blog/release/v24.22.1)。SHA256：`d2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5`。主体MIT及附带组件许可；是安全补丁，不降低锁定目标。
- pnpm：[metadata](https://registry.npmjs.org/pnpm/11.28.8)，[tarball](https://registry.npmjs.org/pnpm/-/pnpm-11.28.8.tgz)。integrity：`sha512-9piKMgRrmj9419fuB0eSa76QX/nf9zvxmruHvX0ZBqKskNk/c74ytfnhTCiZVpvLDJxeyKGeCD9dcburbdnguA==`；官方shasum：`410c60135d333d7a0c950c4108142d002808ddb2`。实际校验使用SHA512，未声称另做SHA1或PGP验证。

下载均使用官方HTTPS并校验上述值；签名/完整供应链审计未完成，不冒称全面安全。发行物、包缓存和工具目录不入Git或审查ZIP。

## 当前阶段依赖登记

| 包族 | 精确版本 | 官方来源/许可 | 目的 |
|---|---|---|---|
| Aspire.AppHost.Sdk、Hosting.AppHost、Hosting.PostgreSQL | 13.6.3 | [官方NuGet](https://www.nuget.org/packages/Aspire.Hosting.AppHost/13.6.3)、[SDK](https://www.nuget.org/packages/Aspire.AppHost.Sdk/13.6.3)，MIT | 已核实13.6.0研究基线之后的稳定修订，统一锁版，不是实验Next helper |
| Microsoft.Extensions.Http.Resilience、ServiceDiscovery | 10.11.0 | [Resilience](https://www.nuget.org/packages/Microsoft.Extensions.Http.Resilience/10.11.0)、[Discovery](https://www.nuget.org/packages/Microsoft.Extensions.ServiceDiscovery/10.11.0)，MIT | ServiceDefaults启动设施 |
| OTel OTLP/Hosting/ASP.NET Core/Http/Runtime | 1.20.1 | [官方NuGet](https://www.nuget.org/packages/OpenTelemetry.Exporter.OpenTelemetryProtocol/1.20.1)，Apache-2.0 | 基本OTel钩子，不实施完整LGTM |
| MSTest.Sdk / MTP | 4.5.1 / 2.5.1 | [SDK官方](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-mstest-sdk)、[CLI](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-with-dotnet-test)，MIT | 适当基础设施测试，TestingExtensionsProfile=None，不默认coverage扩展 |

13.6.3、微软10.11.0、OTel1.20.1为本阶段正式选用精确稳定候选，真实restore/build和锁图才证明兼容；结果后续记录。CPM由Master单写，项目内锁由对应Owner生成并审查；类库锁不是消费者依赖图的替代。所有项目锁是本阶段加严可重复策略，不冒充NuGet官方必须每库锁。

MTP global.json字段为test.runner；不使用旧VSTest桥。未引入Kiota/Hey API或业务SDK。容器发行物/镜像digest及许可由B专项登记，不把发行版存在视为镜像拉取或运行通过。

## V2结构化文件语法门禁补充依赖

G1-ENG仅有TOML单次检查及YAML有限策略，V2明确要求真实语法解析。为此登记PyYAML6.0.3（MIT，普通验证工具，不是产品框架），配Python3.11+标准库tomllib；本机CPython3.13 x64、CI Ubuntu24.04 CPython3.12 x64。精确wheel SHA256写scripts/verification-requirements.txt，只在.tools/pythonlibs隔离恢复，不装用户全局环境，不引其他包。

官方来源：[PyPI精确metadata](https://pypi.org/pypi/PyYAML/6.0.3/json)、[维护者仓库](https://github.com/yaml/pyyaml)、[安全公告页](https://github.com/yaml/pyyaml/security/advisories)。官方旧wiki仍显示5.x，不能据此降级；使用精确PyPI发布。safe_load_all不启用任意Python对象构造，错误只输出路径和异常类型，不回显配置行。该检查是语法门禁，不声称全面安全或运行兼容。

## 结构化门禁真实验证和审查

Master执行`python -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes --no-cache-dir --target .tools/pythonlibs -r scripts/verification-requirements.txt`退出0。沙箱读取隔离包受限，宿主获准执行同一项目入口，不改ACL或全局环境。

独立Reviewer发现解析器文件缺失会静默跳过的Important问题；新增进程内只隐藏解析器的回归，先实测exit1并报告Missing structured parser was not rejected，再补明确FAIL与required-files。复验4项真实正反例exit0；有效YAML通过，无效YAML/TOML和缺失解析器被拒绝。README明确当前哈希覆盖的两个Python/平台组合。`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`完整实测exit0，包括历史8项、doctor缺Node回归及新解析器测试；不将这些工程检查冒充应用/容器通过。

局部EF实测命令为`dotnet tool restore --tool-manifest .config/dotnet-tools.json --configfile NuGet.Config`及`dotnet tool run dotnet-ef --version`，均使用项目隔离SDK/缓存，exit0，显示10.0.13。没有初始化数据库或执行迁移。
