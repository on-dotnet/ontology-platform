# G4-M1 · Docker Compose 双平台实验与资源收尾

## 历史冲突裁决

仓库原 `infra/development/README.md` 说明已有 AppHost 是唯一现行**基础设施开发入口**，并不意味着已完成用户后来提出的统一Docker Compose交付要求。M1 **不删除也不复制 G3现有共享资源**；新增一个 `experiments/g4-m1/compose.m1.yaml`（确切路径由P1确定）只用于独立任务、合成Source PG及必须的隔离认证/平台测试，既不把它宣传为 G8 正式一键部署，也不让现有 AppHost配置因其漂移。

### 拟议 M1 Compose 资源

| 服务 | 用途 | 真实测试要求 |
|---|---|---|
| `pg-source` | PostgreSQL 18.6 synthetic only，独立只读源 | `linux/arm64`/`linux/amd64` 镜像候选实际查询平台manifest；TLS VerifyFull合成CA；无外网 |
| `pg-platform-test` | G4 Metadata+Governance审计的**独立测试数据库** | 与现有G3生产/测试卷物理隔离、可迁移/回滚 |
| `keycloak-test` | 独立合成OIDC角色与org/sites | 需要真实登录/403/CSRF，且不复用G3持久身份配置 |
| `api-test` | G3 Host 加载本次 Connections模块 | 实际服务端OpenAPI + HTTP，镜像复用批准的dotnet10来源 |
| `web-test` | 现有 Next/Shell 加载 G4 UI | Playwright连接到真实服务而非fixture伪网关 |

如 P0 证明现有 G3 canonical 开发资源已具有可安全分离的 TaskId实例与不共享持久存储，可复用其不可变镜像/代码路径，**但必须在实际对象ID与预期操作记录后才允许运行**。若需要增加 Fuseki/RustFS 仅为G3宿主可启动性，则需记录该服务是否真必要、版本/镜像和预算，不默认创建。

首期试验用 `docker compose -p ontology-g4-m1-connection-001 -f <任务专属文件> ...` 设唯一project，优先Docker Linux容器。Windows Docker Desktop/WSL2 AMD64与Mac ARM64分开报告：Mac上的QEMU amd64不是Windows机器的原生验证。`.NET SDK 10.0.402`、Node24.22.1、pnpm11.28.8 按仓库当前global/lock核实；不能因为换平台而自动升级。

### 镜像与包的拟议准入门禁

- 源PG候选 `postgres:18.6-trixie`（在仓库G3已有PG18镜像策略的基础上验证真实registry manifest、`linux/arm64` 和 `linux/amd64` 平台digest、完整镜像许可、各服务所需OS工具）。**没有真正读到的 digest 不许写假sha256；若无法安全取得则只做静态合同并停在下载关口。**
- NuGet候选 `Npgsql 10.0.3`，现有 `Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3`；除现有锁/精确获批包外不引入新依赖；恢复必须按NuGet签名/源和锁模式，不能无范围 `dotnet add package`。
- .NET / Node/Web 镜像优先复用仓库已批准的版本及完整凭据/签名/SBOM来源。不能启用`latest`、不明镜像、透传用户全局Docker socket到服务容器、匿名云下载和系统级daemon修改。
- 批准的任务资源上限为**提案而非已批准事实**：新增任务卷≤3GiB逻辑空间、任务镜像拉取≤3GiB、全部运行容器数≤6、总内存soft cap≤6GiB、GPU=0、公开互联网端口=0、宿主调试端口仅 127.0.0.1 精确映射、真实E2E完整运行预算≤一轮稳定输入。外部curl请求仅官方NuGet/OCI registry/仓库批准域名；不得发送真实客户数据。

### Docker Secret 与网络

Compose secrets用明确任务目录下的本机权限文件加载（路径不进Git），仅挂载给需要的容器。原始文件可能仍是宿主普通文件，不能宣称 Docker 自动提供宿主加密。合成 `pg-source` 使用固定合成用户名/密码由合成fixture生成；真用户的token/生产凭据不在本批。Secret文件/证书/PG data卷均不进入ZIP。PG source服务不对外网监听，API仅连任务内 DNS service；如为方便本机PG客户端暴露回环端口，需明确单一端口并防止撞已有 G3端口。

### 资源生命周期 / 防误删

真实执行前生成 `resources-before.json`，列 Docker Engine/context、containers、images、volumes、networks、build cache/history、Worktree 等现态；另记录 TaskId/RunId/project labels、容器准确ID、镜像digest、卷准确名称、配置指纹和创建时间。每个资源状态 `ACTIVE/KEEP/SAFE_CANDIDATE/AMBIGUOUS`，恢复依据与移除条件明确。

运行结束先提交/推送有效实现、独立Review、完整验收、唯一V3，随后针对任务专属已证实不再使用的资源**精确销毁**（Compose `down` 默认不删命名卷；`down -v` 可能删有数据的卷，必须按名单单独审查）。可能复用到下轮M2的某个已备份且确切共享资源，可记录KEEP及解除时点，但不能长期只写“也许有用”。所有生产/跨项目/未知所有权/旧G3/G6 resources 默认KEEP，禁止`docker system prune -a --volumes`、重启全局DockerDaemon或清历史数据库。

**Before / command-exit / After** 独立复验：核对精确容器/卷不存在或处于计划KEEP，没有多删；若 Docker context changed/权限不足/默认bridge变化等，输出 NOT_VERIFIED 不推断。Worktree包含未合main成果，必须保留直到审查+明确集成及证据恢复确认。最终需给唯一Review ZIP V3（不入Git）和资源回执。
