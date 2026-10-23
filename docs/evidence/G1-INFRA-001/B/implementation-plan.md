# B 实施合同与验证计划

状态：DRAFT/PARTIAL。基线 968ab2a3378427cc4f2612ddb1dbb1b60b5ce9e2；分支 codex/g1-infra-001-aspire。Owner 为 B；Master 持有根 solution、CPM、global.json、CI 和 verify 单写权。依据为人类已明确批准的 authorization-v2.md，不重新启动设计审批。

## 设计与实现顺序

1. 四个最小工程：AppHost 负责开发编排；ServiceDefaults 只负责 OTel、健康、发现和 HTTP 弹性；InfrastructureApi 只有开发健康路由；MSTest 使用真实回环 Kestrel 验证端点、故障就绪/存活隔离、生产默认关闭和服务发现。
2. 先写健康与发现测试。当前精确 SDK 10.0.402 未就绪，不能以机器 10.0.401 替代，测试红阶段为 NOT_RUN（工具链前提缺失）；后续 SDK 就绪后运行并如实记录，不将编译错误算预期断言失败。
3. PG 18.6-trixie 使用 PostgreSQL 官方镜像和版本感知卷目录；Keycloak 26.8.1 使用独立 PostgreSQL 数据库，start-dev 仅限本地，不实现业务登录；RustFS 1.0.3 使用命名卷；Jena 6.2.0 从 Apache 官方 tar.gz 固定 SHA-512 构建 Java21 镜像。
4. 参数密码均为 Aspire secret parameter，从用户秘密存储或进程环境引用；不得提交固定密码或认证配置。Keycloak 管理探针由宿主 HTTP 探测，不能依赖镜像内 curl。
5. 实际 restore/build/MSTest、verify -SelfTest、容器启动、健康、最小开发数据重启持久化验证；可验证里程碑 commit/push，独立 Review 后由 Master 集成。

## 选择与替代

采用官方 Aspire C# 资源模型及通用容器资源，避免引入未经批准的第三方集成。Jena 没有已核实官方预构建镜像，采用官方发行包自建镜像，不把社区镜像冒充官方。业务 API、OIDC/BFF/Web、发布语义、MCP/Agent/SSE 和完整 LGTM 均不进入本任务。

## 待审查重点

PostgreSQL18 卷路径、密码缺失失败与密码稳定性、Keycloak 外置数据库与管理端口、Jena 下载校验与 TDB2 重启、RustFS 数据卷权限及就绪探针。就绪不代表完整 S3/语义功能或生产可用性；生产依赖审计与备份恢复仍为后续关口。
