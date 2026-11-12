# G4-M2-DORIS-01｜A–F 裁决与条件执行授权

## 0. 生效方式与本次结论

本文件是 ChatGPT 对 P0 申请的审查意见及供用户确认的执行授权文本。**只有用户在 Codex 会话明确同意本文件，授权才生效。** 不代表元数据、资源或产品测试已经通过；不代替平台/系统的权限审批。

接受 P0 文档交付；建议按下列修订批准 A–F，在原会话、原分支、原 Worktree 继续。同意范围内不逐补丁申请、不另建工程优化/恢复任务。条件通过后自动进入已批准的下一步；条件缺失只停止依赖它的操作，不反复生成申请或 BLOCKED ZIP。

依据：本次 `admission-request.md`（SHA-256 `588fb813d5dab1f3325177a158d72c441c7408afa3a8cc0978396b2e2e2b5b79`）、任务卡、现行工程政策。本文件对授权边界的明确修订优先；旧事实、失败、已审源码和 ZIP 不改写。

## 1. 会话、身份及写入范围

| 项目 | 本次设置 |
|---|---|
| 新建会话 | 否，继续 `G4-M2-DORIS-01-MASTER` |
| 模型 / 强度 | 沿用客户端当前可用的 GPT-6 Astra，Medium；复杂安全/权限独立审查按需 High，不默认 Max |
| 执行方式 | Code / Agent，Local Mac ARM64；先一页以内更新清单，随后范围内直接执行，不开启新一轮 Plan 审批 |
| Worktree / 分支 | 复用原托管 `g4-m2-doris-01` / `codex/g4-m2-doris-01` |
| main 基线 | `11595ecb6560f7ed6ceca54666d32b7afcae7f35` |
| 本次 P0 Head | `6f985b6a3c9558213a63a428ddec5eca3e05057b` |
| 分工 | Master 单写公共合同、锁和部署配置；非作者 Reviewer 审核准入及最后增量，不为普通小修复另派团队 |
| main / 生产 | 均不授权更新、部署或连接 |

开工窄 fetch 复核身份与保护文件。只更新本任务当前状态/授权段；保留历史授权。产品、工程及部署写入范围采用申请第6节，补充允许 `apps/web/vitest.config.ts` 的任务缓存/报告绑定和对应定向测试。准确 owned_paths 在任务卡一次列清；日常必要修复不再绑定每个补丁 SHA。新增业务、公共 wire 字段/路由/权限、迁移语义、依赖名单、资源预算或系统级动作越界时，汇总差异另请批准。

## 2. A、B、F：把制品获取和运行分开

### 2.1 A：固定候选，不自动追随版本

批准下列候选进入核验和条件获取，不是确认已可运行：

| 制品 | 固定身份 |
|---|---|
| Doris FE | `apache/doris:fe-4.0.8`；index `sha256:390413325a93d9121768bda153ccaa3c7a8da4aa0fd2a466406cddc14a6399b2`；ARM64 manifest `sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02` |
| Doris BE | `apache/doris:be-4.0.8`；index `sha256:d911ae3826491598be4e383cba83011a266091b8fdc6c34c036280220cc4fea9`；ARM64 manifest `sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7` |
| 直接 NuGet 包 | `MySqlConnector 2.6.2` |
| 待闭合的传递候选 | `Microsoft.Extensions.Logging.Abstractions 8.0.2`、`Microsoft.Extensions.DependencyInjection.Abstractions 8.0.2` |

上述 OCI 值来自申请的标签元数据，本轮未独立取得 manifest 原始字节。必须核验 index→ARM64 manifest→config→layers 的引用、内容散列与 OS/arch；不只验标签。身份不符停止，不换镜像/tag/架构规避。

`>=8.0.2` 是依赖下限，不证明整个仓库最终只解析三个包。以 net10.0 适用组、现有直接依赖和各项目锁为准；不为了凑这三项而降级现有包、删依赖或忽略冲突。现有已批准、已锁定且兼容的版本可原样保留；任何新增名单/版本之外的载荷、锁内现有版本变化，先列一次差异，不自动放行。Logging 的确切闭包仍待补证，超时记录保留，改用官方元数据入口而非反复刷新同页。

### 2.2 B：立即允许有界元数据读取及落盘

明确允许 HTTPS GET/HEAD 读取并保存公开 index/manifest、其指向的 **config JSON**、layer 描述符列表、nuspec、公开校验值、许可、漏洞通告及签名元数据。允许本任务目录新增这些小型证据文件。

- 单个元数据响应体上限 **8 MiB**，本次累计上限 **64 MiB**；流式限长，超限停止相关读取。此预算是本任务新增限制，不是 OCI 标准。
- config 可以位于 `/blobs/<digest>`：只准读取已验证 manifest 的 `config` 描述符指定的 JSON，校验 mediaType、size、digest。**不得将 `/blobs/` 全路径放行，也不得读取 `layers[]` 响应体。** 可做层的 HEAD/响应头查询，探明长度与转向；元数据阶段不跟随取层内容。
- 这仍是网络读取，实际字节照实记录；“无镜像层/包载荷下载”不写成“网络流量为零”。
- 固定来源：`registry-1.docker.io` 的 `apache/doris` 仓库、`auth.docker.io`（公开 pull scope）、`hub.docker.com` 对应仓库；NuGet 官方 `api.nuget.org`、`www.nuget.org`；Apache Doris、MySqlConnector、Microsoft 官方资料及其官方 GitHub 仓库。
- 补充允许 Docker 官方 allowlist 列出的 `production.cloudfront.docker.com`，仅接受由上述注册表返回、绑定获准 digest 的 HTTPS 转向。不得放开任意 CDN、`*.cloudfront.net` 或任意 IP；其他域名先记录 Location 和官方归属，汇总申请，不能自动跟随。跨域不转发 Authorization/Cookie，签名 URL 和 token 不公开归档。
- 不关闭 TLS 校验、不改代理/全局信任、不安装获取工具、不读取用户凭据正文。走正常平台权限确认；新授权后若仍被拒绝，停该操作，不伪装命令或换通道绕过。

### 2.3 下载准入与下载后检查

不能要求“下载前已完整核验镜像内部组成”，再以未核验内部组成为理由禁止取证。采用两个明确门槛：

**获取门槛：**固定官方来源/版本/架构、manifest/config 引用及散列闭合、准确层清单和保守新增量、NuGet 适用闭包及 URL 已登记、下载域名受控、磁盘预算可执行、非作者准入核对通过。满足后，允许获取上述精确制品至本地隔离缓存；不需再次人工批准同一清单。

- 下载载荷总上限 **5 GiB**，NuGet 部分另限 **10 MiB**；NuGet 解包/缓存另限 **100 MiB**。层列表按 digest 去重，本地命中必须证明，不能靠 image 列表推定。提前评估余量，登记已知重试/未完成载荷，不以去重掩盖实际重传；不可测的底层网络流量标 NOT_VERIFIED。
- 只获取当前缺失的 ARM64 层和获准包；不全平台拉取、不 tarball 自编译、不新增 JDK/SDK/EF Provider/镜像构建工具，不升级 SDK、Node、pnpm。
- 获取本身不启动镜像 entrypoint、不执行包脚本/targets。下载后校验原始字节、包 ID/version/适用组、官方来源证据及可得的签名；必要的只读解包须防路径穿越/符号链接，不运行其中程序。
- 镜像实际解压占用下载前未必可精确得知，允许保守预留并在受控获取/存储过程中量测；新增磁盘总额 **25 GiB**，过程产物 **1 GiB**。容量不可监控或余量不足则不继续，不靠全局清理解决。

**执行门槛：**获取后的身份/内容检查通过，已检查可得的 LICENSE/NOTICE、OS/JDK/第三方组成及漏洞/签名信息，无已知适用重大风险未处置，资源及隔离就绪，非作者确认。本任务风险接受仅在用户发送本授权后生效：

`DORIS-LOCAL-01 = 限上述精确制品、本机隔离、合成数据、非分发、无生产凭据`。

这一新接受允许完整 SBOM/签名可得性/全量 CVE 研究仍有明确列出的 NOT_VERIFIED 项；**不等于安全扫描 PASS，也不是继承历史 AMBER-A1。** 来源不明、内容散列不符、验签明确失败、已知适用高危漏洞或许可禁止，不能按此放行。新风险超出本接受则一次汇总停止。不得上传私有代码/数据到扫描服务或使用收费服务补证。

F 的生产/分发风险不接受；保留后续生产准入缺口。不把“零已知漏洞”写成“无漏洞”。

## 3. C：单机缩减合成试验，不是生产配置承诺

批准单机 1FE+1BE、单副本缩减实验；不保证成功、不宣称达到官方开发建议。

| 对象 | 本次上限/条件 |
|---|---|
| 并发容器 | 4：FE、BE、平台PG、OIDC |
| 容器内存 | 合计12 GiB：FE4、BE6、PG0.5、OIDC1，余量0.5；实际 inspect 验证限额 |
| Docker VM | 用户自行在 Docker Desktop 设置16 GiB；运行前读回 Engine 可见内存及压力。计入VM开销，要求可见至少15 GiB、任务容器总额不超过12 GiB，并确认不存在挤占预算的其他工作负载；这不是保证可用空闲内存 |
| 宿主 | API/Worker、Web、串行测试三个工作负载，合计额外≤4 GiB；子进程/浏览器同样计入与监测，不隐去 |
| 存储/费用 | 新增≤25 GiB，过程产物≤1 GiB；GPU0、费用0，无云主机 |

目前申请记录 Engine 仅约7.75 GiB，不能直接运行本配置。元数据及不依赖新设施的文档/静态合同工作可先进行。**Agent 不改 Docker 全局设置、不重启 daemon、不停其他任务；用户调整前须确认不会中断其他任务。** 调整后只重验 Engine/context/资源和受影响运行身份，不清空内容缓存。

FE JVM heap、BE 原生内存/嵌入JVM、线程数和磁盘保留值必须明确处于各自 cgroup 上限内，留出非堆/系统余量；禁止仅给容器设4 GiB却沿用更大的JVM堆。预算内的本任务配置修正允许持续完成，不能关闭TLS/权限/审计来省内存。

先登记有界就绪窗口和健康标准。启动期 `starting` 或一次未就绪探测不等于最终失败；首次OOM、进程退出、最终健康失败或就绪超时，立即停昂贵长链，保留证据并做短定位。同条件不重复整链；需超预算时才汇总请批，不自动扩容/仿真/换版本。

平台PG与PG源兼容测试串行安排，不偷偷新增第五容器。连接及取消辅助连接都在网络/并发预算中。容器内部网络与精确loopback映射按申请冻结；API在宿主时，必须实证连接地址、DNS、SAN/SNI和发布端口一致，不将容器内DNS名当作宿主必可解析。不改全局hosts，不用不验主机名来弥补。

允许本任务私有 CA/FE 服务证书及错误证书负例，数量沿申请；不安装全局信任，不归档私钥，不复用发行默认密钥。

## 4. D：批准 DORIS_READONLY 完整生命周期

批准新增用途 `DORIS_READONLY` 和对应公开 Intake 校验、服务端分发、UI Intake 与定向合同测试。无新增 wire 字段/路由/权限、无迁移、无持久字段语义改变；现有 Purpose 字符串承载不代表其它变更也获准。

- PG/Web/Doris 三用途双向隔离。所有绑定、解密和源IO前都验证类型、目标、组织/厂区及用途；客户端不能自行扩大服务器目标白名单。
- Doris Profile 或规范化 scope 变化不自动重绑旧 secret；新目标重新 Intake/新建，原目标轮换使用既有流程。展示名普通编辑不误判为目标变化。
- 沿用未绑定凭据TTL、已绑定凭据生命周期、CAS、幂等、撤权/禁用取消、审计原子性。审查 Intake→Create/Probe→Enable→Worker→Catalog 回读，不只放行一个用途字符串。
- 只固定 FE/internal/fixture 元数据；源端合成管理员仅建夹具与观察，不交给应用。禁止生产源、用户SQL、外部catalog与M4数据查询。
- 采用申请第5节的对象/字段/结果预算，Doris独立限额不扩大PG/Web。**10秒采用覆盖解析/连接/读取的总deadline；CommandTimeout不能代替整个结果集的总期限。** 取消清理另有有界时间，辅助连接同目标、同TLS和同安全身份。
- TLS必须直接在FE MySQL端口验证VerifyFull、私有CA和SAN；坏CA/SAN/过期/降级拒绝。只读核验覆盖有效继承角色、跨库与管理员/写权限拒绝；未知权限格式失败关闭，不试写业务数据证明只读。
- 取消需源端query/connection身份与消失/终止见证，不能只看客户端异常；取消不支持时不能给应用管理员权限兜底。

## 5. E：实现和部署源码交付，明确生产边界

批准申请第6节列出的 adapter、公共消费链、现有UI、受影响锁、TaskId/gate准入、测试，以及 `infra/doris/`、`docs/deployment/doris.md`。Master只做必要变更；不复制公共执行/证据框架，不建另一套生命周期。

部署源码要求：同机1FE+1BE/单副本；base/test/production覆盖层清楚，镜像按digest锁定，证书与secret外置，持久卷/权限/健康/资源/网络清楚，部署、备份恢复、升级回滚说明可执行。测试管理员/fixture初始化只在test配置。生产配置默认不得包含测试账号、弱口令、合成CA私钥或自动删卷步骤。

**特别澄清：**本次生产模板指 Doris 服务的部署配置来源及平台接入前提，不是整个平台的生产启用许可。基线 `G4Composition.AddG4Module` 在非Development且G4启用时拒绝；本轮不得删除该限制，也不得把Production环境伪装成Development。Doris生产模板可做静态渲染检查/在隔离环境演练，实际生产接入、容量/SLA、高可用和生产备份恢复仍 NOT_RUN。若目标要求平台本轮直接在Production运行Doris连接器，另列准确生产准入差异，不悄悄改Guard。

生产配置不得默认沿用合成FE4/BE6资源。ARM64实测不代表未来Linux x64生产已验收；未获准下载其他架构镜像。参数化地址不等于允许任意外联。

## 6. 条件通过后在同一任务直接推进

1. 更新一页清单，补齐元数据、有效NuGet闭包、受控域名、源/缓存身份、预算和风险登记；Reviewer一次核查。无重复历史全链。
2. 满足获取门槛后精确下载/校验；满足用户VM确认与执行门槛后，以最短真实服务探针证明ARM64启动、直接TLS、有效只读权限和取消可行。失败先短定位，不先铺开长生命周期测试。
3. 补本任务执行入口、TaskId/gate映射和Vitest缓存/report绑定；复用DELIVERY-002执行/止损/双流/结构化结果/计时。首份证据立即验证生成→解析→归档路径。
4. 公共凭据合同/分发先测试和非作者审查，然后adapter/UI和Compose实现；以影响图选PG/Web兼容，不把新Head等同全部证据失效。锁或共享输入变化确实影响的测试必须新执行；未变、可恢复证据重新核验后标REUSED。
5. 真实Doris生命周期、TLS/权限/取消、部署配置与合成恢复演练闭合；自然TTL只有其实现/预期输入未变且证据有效时复用，不用旧Web结果证明Doris特有绑定逻辑。
6. 稳定输入独立Review、普通push任务分支、唯一最终V3和独立重开、包外回执。只回收本任务闲置资源；保留活跃缓存，不每Run销毁重建。main仍等待单独批准。

本次允许的下载是准确的阶段例外；依赖获取结束后，build/restore/tests继续使用本地已准入来源及原离线边界。禁止SDK resolver/包管理器隐式新增下载。

最终完成标准：功能、安全、部署源码和所有适用门禁均有FRESH或有效REUSED证据；计时覆盖主要阶段，未知如实UNKNOWN；依赖和新资源准确登记；无开放P0/P1；CI/Windows/Intel/生产未运行分列；历史Web/M1/工程ZIP不改。未达到则只报告差异与原始见证，不以Mock/容器Running/文档齐备替代成功。

最终只交唯一Review ZIP与包外回执（含验收、下载/风险、资源及效率索引）。元数据或等待VM期间不生成中间ZIP，不再申请同范围普通代码/配置修复。

## 7. 审查依据与未验证项

本轮ChatGPT已核对两份附件、仓库分支差异及基线G4启动Guard，并读取下列官方资料。**未下载Doris层/NuGet载荷，未核验申请的OCI原始manifest、未在用户Mac调整或启动任何设施。** Logging 8.0.2页面/原始nuspec本轮未成功取得，不能据此声称闭包完成。

- OCI image manifest（config与layers分离）：https://github.com/opencontainers/image-spec/blob/main/manifest.md
- Docker官方域名清单：https://docs.docker.com/desktop/enterprise/allow-list/
- Docker内存设置：https://docs.docker.com/desktop/settings-and-maintenance/settings/
- Doris开发/测试资源说明：https://doris.apache.org/docs/4.x/install/preparation/env-checking/
- MySqlConnector2.6.2依赖分组：https://www.nuget.org/packages/MySqlConnector/2.6.2
- DI8.0.2依赖分组：https://www.nuget.org/packages/Microsoft.Extensions.DependencyInjection.Abstractions/8.0.2
- MySqlConnector取消/总期限边界：https://mysqlconnector.net/overview/command-cancellation/
- Doris MySQL TLS：https://doris.apache.org/docs/4.x/admin-manual/auth/certificate/

以上是设计核查来源，不是本任务实际运行证据。首次制品内容核验、资源读回和真实能力验证仍由Codex按本授权完成。
