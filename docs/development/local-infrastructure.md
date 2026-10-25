# G1-INFRA 本地开发基础设施

历史G1交付见 [原B验证记录](../evidence/G1-INFRA-001/B/validation.md)，Mac原生ARM64实测见 [M0容器验证](../evidence/M0-MAC-PORTABILITY-001/B/validation.md)。此编排仅用于本机开发。Keycloak 的 start-dev、不带认证的 Fuseki 开发数据集和非 TLS 内部端点不构成生产部署方案；不实现业务登录、业务表、语义发布、Web、MCP/Agent/SSE 或完整 LGTM。

## 工程与端口

| 资源 | 启动方式/镜像 | 本机端口 | 容器端口/探针 | 数据持久化 |
|---|---|---|---|---|
| AppHost | .NET10 / Aspire13.6.3 | 15888 dashboard | 本机开发仪表盘（保留默认认证） | 不存业务数据 |
| InfrastructureApi | .NET10 | 15080 | /health、/alive，仅 Development | 无 |
| PostgreSQL | postgres:18.6-trixie | 15432 | 5432，Aspire 内置数据库就绪检查 | ontology-platform-postgres-data → /var/lib/postgresql；PGDATA=/var/lib/postgresql/18/docker |
| Fuseki/TDB2 | 本地官方发行包构建，6.2.0 | 13030 | 3030，/$/ping | ontology-platform-fuseki-data → /fuseki/databases |
| RustFS | rustfs/rustfs:1.0.3 | 19000 S3 / 19001 console | 9000 / 9001；S3 /health/ready | ontology-platform-rustfs-data → /data |
| Keycloak | quay.io/keycloak/keycloak:26.8.1 | 18080 HTTP / 19090 management | 8080 / 9000；management /health/ready | PostgreSQL 中独立 keycloak 数据库 |

固定本机端口仅用于避免不同资源默认端口冲突。启动前确认空闲；Aspire 默认代理端点供本机使用。不要把开发端口转发至公网或共享网络。PG18 不复用 PG17 旧数据卷；跨主版本升级需独立备份迁移，不删除已有数据来掩盖问题。

## 前提与密码配置

使用仓库 global.json 精确指定的 .NET SDK 10.0.402。项目隔离 SDK 可以通过绝对路径调用，不修改机器 PATH。需要已运行且获准访问的 Docker Linux daemon。本项目不负责安装 Docker、改变 WSL 或虚拟化。

AppHost 声明四个没有默认值的秘密参数：

- Parameters:postgres-password
- Parameters:rustfs-access-key
- Parameters:rustfs-secret-key
- Parameters:keycloak-admin-password

将真实值通过操作系统用户秘密存储或进程环境配置注入。AppHost 已声明 UserSecretsId，使用 dotnet user-secrets --project backend/src/AppHost 设置以上键；不要把真实值放入仓库、命令记录或工单。环境变量键使用 Parameters__ 前缀及原参数名（保留连字符），PowerShell 可用 [Environment]::SetEnvironmentVariable 在当前进程设置，避免写入机器环境。

首次启动前设置稳定的秘密值，后续使用同一命名卷时保持一致。PostgreSQL 镜像的初始化密码只对空卷生效，Keycloak bootstrap 密码也只引导首次管理员；修改环境变量并不能重置已存在的数据库密码或管理员。RustFS 禁止使用公开默认凭证。测试可在单次进程中生成随机值，跨 AppHost 重启仍保留该进程配置；不读取现有 Docker 认证文件。

## 启动与健康

在仓库根执行（dotnet 可替换为隔离 SDK 的绝对路径）：

```powershell
dotnet restore backend/src/AppHost/OntologyPlatform.AppHost.csproj --locked-mode
dotnet run --project backend/src/AppHost/OntologyPlatform.AppHost.csproj --no-restore
```

AppHost 自动构建 infra/development/fuseki/Dockerfile。该 Dockerfile 验证 Apache 官方 tar.gz 的固定 SHA-512，并固定 Temurin Java21 镜像摘要。首次网络拉取/构建可能较慢；校验失败必须停止，不能跳过散列或换成未批准镜像。

PostgreSQL 就绪后创建开发空库 ontology_platform 与 keycloak；Keycloak 等待自身数据库可用。Fuseki 和 RustFS 可以并行启动。InfrastructureApi 等待上述资源的就绪检查后才启动。API 不执行 SQL、SPARQL 或 S3 业务操作，其 /health 只反映自身注册的健康检查，不能代表整个资源栈。依赖状态以 Aspire 各资源探针和下述实际操作核验为准。

```powershell
Invoke-WebRequest http://localhost:15080/health
Invoke-WebRequest http://localhost:15080/alive
Invoke-WebRequest 'http://localhost:13030/$/ping'
Invoke-WebRequest http://localhost:19000/health/ready
Invoke-WebRequest http://localhost:19090/health/ready
```

Keycloak 镜像没有 curl，不能以 docker exec curl 失败判断服务失败。探针必须从宿主或 Aspire HTTP 健康系统访问9000端口。ServiceDefaults 在配置 OTEL_EXPORTER_OTLP_ENDPOINT 时启用 OTLP 日志、指标和跟踪导出；Aspire 自动注入。健康请求排除跟踪。基础遥测不等于 LGTM 管线、生产审计或中文运维已完成。

## 重启、恢复与验收

容器使用 --restart unless-stopped 处理进程退出；Docker 不会因为 HTTP readiness 失败自动重启容器。Aspire 会话停止可移除会话容器，但命名卷保留。再次启动仍用同一秘密值和固定卷名；不要执行 docker volume prune 或删除卷。

正式重启验证只使用专门开发探针数据，不能连接生产系统：

1. 在 ontology_platform 建专门 probe 表并写随机标记；在 Fuseki /ontology 通过 SPARQL UPDATE 写入独立测试 IRI。
2. 用支持 SigV4 的临时测试客户端在 RustFS 建 probe bucket，上传随机标记对象；只记录对象名和校验结果，不记录密钥。
3. Keycloak 的数据库配置与初始 realm/管理员数据应在 PostgreSQL 中。仅核验数据库存在和重启后健康，业务 OIDC 登录归 SEC。
4. 记录资源名和命名卷，停止/重启 AppHost 或对应容器，重新检查所有探针和原随机标记；不要只凭容器 Running 判定通过。
5. 当前开发探针可保留为证据，清理只限明确创建的测试实体。真实结果、命令和退出码写入 B 验证记录；未执行必须 NOT_RUN。

## 本机测试与故障处理

```powershell
dotnet test --project backend/tests/OntologyPlatform.InfrastructureTests/OntologyPlatform.InfrastructureTests.csproj
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
```

MSTest 使用真实回环 Kestrel，不要求容器，覆盖开发探针、就绪失败但存活成功、生产默认无探针、逻辑服务发现。容器集成验收另记，不能用四个宿主测试替代。端口占用、镜像不可取、Docker 权限或包恢复失败均保留现场并报告 BLOCKED/NOT_RUN；不降低版本，不自动安装系统组件，不无审查进入下游关口。

## 复现本阶段资源重启验证

```powershell
pwsh -NoProfile -File infra/development/test-resource-persistence.ps1 -PostgresContainer <本次PG容器名> -FusekiContainer <本次Fuseki容器名> -RustfsContainer <本次RustFS容器名> -KeycloakContainer <本次Keycloak容器名>
```

该脚本从当前进程读取已注入的PostgreSQL及RustFS秘密，PostgreSQL密码只传Docker子进程环境，S3签名异常不回显原始头。它会写独立开发探针并重启明确指定的四个容器；只针对本任务专用开发资源运行。可用DevelopmentInfrastructure:VolumePrefix覆盖默认ontology-platform前缀创建独立测试卷，须同时向脚本传同一-VolumePrefix。前缀只允许1至48位小写字母、数字和连字符且首位为字母或数字，不自动删除卷。

本机HTTP profile显式设置ASPIRE_ALLOW_UNSECURED_TRANSPORT=true，仅允许回环开发明文传输，保留Dashboard默认认证。不要外推为生产或公网配置。资源容器后端与Aspire固定代理端口已实际核验仅绑定127.0.0.1/::1，见本阶段运行证据。

AppHost官方NuGet回退工具包含平台专用Dashboard/DCP，当前锁定支持win-x64、linux-x64与osx-arm64，分别使用packages.win-x64.lock.json/packages.linux-x64.lock.json/packages.osx-arm64.lock.json（Mac锁由M0 Master生成并集成）。osx-x64及其他RID尚未验收。Windows执行Linux包恢复不等于Linux运行成功，后者等待实际CI。

## M0 Mac 实测与遥测查询

macOS27.0.1/arm64，Docker29.9.2 linux/aarch64，四固定index真实提供ARM64，实际四资源均linux/arm64；未使用amd64模拟或更换摘要。AppHost官方NuGet平台DCP/Dashboard实际启动，健康、会话网络、只回环监听和四资源重启持久化均已运行。开发证书/DataProtection警告保留，不能外推生产安全或灾备验收。

Dashboard telemetry API默认保留ApiKey认证。可在启动AppHost的当前进程中设置随机AppHost__DashboardApiKey并以内存值发送X-API-Key header查询/api/telemetry/traces/{traceId}；不要把值放URL、命令记录、Git或审查包，不要关闭认证。M0已用真实404请求的traceparent核对Dashboard返回TraceId/parent/service.name；健康路径排除跟踪，不用/health测试请求Trace。完整LGTM仍归未授权OBS。

本轮专用卷前缀m0-mac-b-20261025及m0-mac-b-trace-20261025仅保留随机测试数据，临时秘密值不主动写入源码、日志、证据或独立秘密文件；容器与运行时内部存储按Docker及服务机制处理；不要拿它们当可复用日常开发配置。正常日常卷用稳定本机秘密。AppHost停止后卷保留，重启探针不等于生产备份恢复。M0真实状态、限制和清理来源见上方证据，Windows本轮未重跑，历史结果不改写。
