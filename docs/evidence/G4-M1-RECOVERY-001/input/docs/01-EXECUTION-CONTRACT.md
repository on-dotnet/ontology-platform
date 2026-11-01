# G4-M1-RECOVERY-001 · 正式执行合同草案 V1.0

**状态：AWAITING_EXPLICIT_USER_AUTHORIZATION**。本合同是给下一次人工审批的精确范围文件。本文件自行不能替代批准。仅在用户明确批准后，允许以下受控操作；未批准时仅可做只读解释、计划与审查。

## 目标与切片

在不重做已审 G4-M1 DRAFT 源码的前提下，用**一次受控恢复任务**解决镜像许可取证循环门禁，完成 `P3(真实PG/OIDC/HTTP)→P4(目录Job及UI)→P5(49项稳定本地产品验收)`。若新取证仍发现实质法律/高危依赖阻断，精准止损并交最小差异证据，不重复做纯元数据观察任务。

本次继承用户对上一 G4-M1 P0–P5 的明确批准，但原 `docs/06-M1-COMPOSE-RESOURCES.md` 的**“全部镜像许可证据在任何层拉取前完成”**仍须经本合同的新明确授权才能改为分层准入。只有该条及本合同明确定义的取证下载权限被覆盖，其他用户原授权、资源界限、G3/G6禁止边界保持。

## 正确的工作阶段 DAG

### R0 · 真实基线和前置证据检查（零新下载）

1. 重新 Git fetch，确认 protected main、G4-00、M1 Head、TestedCommit 及所有活跃树。拒绝不明本地修改及复写其他树。
2. 只读核对 `G4-M1` V3 Base/Head/Manifest，复用既有源与合成组件成功证据。不要重复大规模全仓测试；只在运行输入/产品源码变化时做对应的受影响检查。
3. 查看真实 Docker Engine/context/`docker scout version`/已有镜像 digest/剩余磁盘、网络/卷、端口及授权的 TaskId 资源；默认不更改 Docker 全局设置。
4. 精确复核本包中的四个镜像候选及最新实际 registry digest。**若 tag 已漂移，只能使用本包固定的 index/platform digest，若不能取得该 digest 必须停止该镜像**；不静默升级镜像版本。
5. 冻结将来能回收的任务专属资源 ID/labels，登记 `resources-before.json`；独立 Reviewer 审查这份 R0 准入合同。

### R1 · 官方镜像来源/预算准入（可读远程元数据）

- Registry 仅 Docker Hub official（postgres/node）、`quay.io/keycloak/keycloak`、`mcr.microsoft.com/dotnet/aspnet`，以及这些官方 registry 解析所必须的明确镜像层/CDN域名；域名重定向实时列清并独立审查，不自动外联任意站点。
- 仅四个候选镜像：postgres 18.6-trixie、Keycloak 26.8.1、ASP.NET Runtime 10.0.13、Node 24.22.1-trixie-slim。Digest 必须与 `evidence/image-candidates.json` 的 approved snapshot 一致，或进行准确用户授权的新裁决；不添加 Fuseki/RustFS/额外依赖镜像。
- 在任何层下载前，验证发布者、许可（顶层项目）、签名/attestations **实际可验证的部分**、index+`linux/arm64`/`linux/amd64`平台digest、压缩层预算、隐私、网络和 Docker 当前上下文。**这不是“已完成所有依赖许可”的断言。**
- 默认只选择本机 `linux/arm64` 的精确平台digest和其关联的 4 个固定 index refs 拉取；`linux/amd64` 保持远程元数据观察，不在 Mac 上冒充 Windows 原生测试。若确需额外下载 AMD64 层另提授权，不以用户已要求跨平台为由直接扩大下载。
- 下载不超过原批准的 **3 GiB**（含 registry scanner 远程层请求）；任务新增正式命名卷不超过 **3 GiB**；至多 6 个容器/6 GiB 内存，公开互联网端口0，GPU0。下载前须量化剩余磁盘/CPU/现有 Docker 实际能力；不能在资源失控时继续拉取。

### R2 · 任务隔离取证下载（**新用户授权后**；未准许运行容器）

- 允许先用现有 `docker scout sbom registry://<exact ref>` 解析精确镜像；**registry:// 可能获取层，计入下载预算**。未安装 Scout 不得自行下载不明脚本，不通过第三方网盘或云扫描传送本项目源码/凭证。
- 只有当远程 attestations/SBOM 不足以提供完整包级证据时，允许对 R1 已批准的 `linux/arm64` 官方 index digest 执行受控 `docker pull --platform linux/arm64 <name>@sha256:<approved-index>`。每次只拉一个，记录实际新 image ID/digest、时间、网络/磁盘变化；先核验再继续下一个。
- **取证下载阶段不执行 `docker compose up`、`docker run`、镜像内脚本或入口程序**；优先用 Docker Scout 对已下载本地镜像生成 SPDX/CycloneDX/SBOM 和逐包 license。没有准确证据时使用 `NOT_VERIFIED`、`NOASSERTION` 与逐项标记，不用相近版本或另一平台推断。
- Docker Scout 若不可用，只允许使用已批准的本地只读工具或安全提取 Docker image archive 进行只读取证；不得静默增加依赖、运行容器或修改 Docker daemon。无法完成则停止且输出工具能力与最小授权缺口。

### R3 · 非作者 License/安全准入（禁止“自动全绿”）

- 出具每个精确 `platform digest` 的 `SBOM`（数量与有效覆盖范围）、包/版本/来源/许可证/版权通知/适用的商用义务、许可证缺失清单与风险。签名、provenance、CVE扫描是**独立**维度，不得拿其替代许可证据。
- `GREEN`：本次研究使用及后续再评估的许可来源可信，当前设计政策允许且没有未解释的实质阻断。`AMBER-A1`：仅常见 SPDX `NOASSERTION` 或未齐全 NOTICE 元数据，官方来源与顶层使用权可查、无已知禁止测试条款、宿主完全隔离、不向客户分发镜像；经**本合同获用户明确批准的“内部合成非分发 PoC 风险接受”**且非作者 Reviewer 逐镜像签署风险登记，可以进入 R4，但始终标记 LICENSE_PARTIAL，不能声称商用交付已合规。`AMBER-A2`：存在真正不能判定的使用权冲突、重要依赖许可原文缺失或额外收费/署名条款，必须另行人工/法务裁决，停止执行该镜像。`RED`：明确禁止/冲突、源不受信、不可控漏洞/无法隔离/费用超预算，停止使用。
- **只有用户批准本合同时明确接受 AMBER-A1 的“仅内部合成、非分发、准入检查不断开”权限，且逐镜像独立 Review 签字、无实质许可冲突时，才允许内部研究运行**。AMBER-A2、RED 必须停止并申请单独裁决。一个未知 SPDX 字段不自动等于非法，也不能默许正式商用部署。G8 生产与软件分发须另外完成 SBOM、NOTICE、授权条款审查/必要法务与交付清单。
- Reviewer 为非作者，出具逐镜像、逐平台审查报告且至少回答 “是否允许本任务内部合成运行？”、“尚未解决哪些商业分发事项？”。Master 不得用自己的接受状态取代审查。

### R4 · 当前产品代码 P2 安全补缺与真实运行门禁

- 先验证源代码中的 `G4Endpoints.cs:37`：64 KiB 限制只检查 `ContentLength`，在 chunked/HTTP2 无 Content-Length 的请求下需要真实请求体字节限制；优先限长读取或已验证的 Kestrel endpoint RequestSizeLimit。增加超界、缺 Content-Length、未过密钥/审计的 HTTP 负例。**只在受授权 Connections/Host 相关路径最小修改**，不放宽现有 G2/G3。
- 在 R3 非作者 GREEN 或满足上述已获批准 AMBER-A1 内部研究例外后，才允许按原批准 M1 合成 Secret/TLS 策略实施 `experiments/g4-m1/compose.m1.yaml`、有限运行入口及合成证书/只读角色/fixture，完成 `scripts/maintenance/g4_m1_preflight.py` 所需真实 runtime consumers。不可用“空文件/假参数”刷 preflight PASS。
- 先由最短真实 PG Adapter TLS/只读测试确定源可用，再启用独立平台 PG/Keycloak/API、再启 UI/浏览器；服务分组启动，满足 6 容器/6GiB 限额，不改 G3 共享持久卷。
- 任何早期 PG/证书/角色/审计故障必须做短复现；严格复用原 P2 组件成果，不改业务设计；只有重新测试受影响层才恢复集成。

### R5 · 49 项真实产品验收及独立 Review

- 使用原任务 `review-evidence/G4-M1-CONNECTION-001/acceptance-matrix.json` 的全部49个 M1-C16/P14/E19 标识逐项核验：真实TLS VerifyFull、源端只读、创建/保存/Probe、重复命令、CAS、审计回滚、Catalog snapshot/取消/fence、Keycloak/OIDC/CSRF/403、Next UI、刷新恢复、五源未支持提示、资源清理。暂不替代 M3 的 Mapping 回滚或 M4 的 Datum。
- 正确引用 G4/G3冻结合同，任何新权限必须审计闭环；真 source synthetic，不采集真实业务行、无外部 LLM/API/客户凭据/收费模型。
- 跨平台：Mac ARM64 native container 可按真实结果 PASS/FAIL；Windows 原生未验证继续 `NOT_RUN`，不得以 AMD64 manifest 或 QEMU 模拟宣称 Windows 验收。
- 已跑且输入未变的定向组件测试允许按 local-validation-policy 复用；如代码/锁/运行配置变更，必须重跑受影响部分。稳定输入完成一次完整本地真实验收，不重复无价值的 SelfTest/全仓重验。
- 非作者 Reviewer 对真实产品、安全、资源证据进行独立复审；本次增量提交必须绑定实际 TestedCommit/Head，交付唯一 Review ZIP V3（包括新任务证据及原M1可恢复事实索引）与完整 SHA256、Manifest、独立重开。`main` 与 G6 不变，不自动开 M2。

## OwnedPaths 与角色

- Master Single Writer：`backend/src/Contracts/OntologyPlatform.Contracts/G4*`、`backend/src/Hosts/OntologyPlatform.Api/G4/**`、`backend/src/Modules/Governance/**`仅所需精确白名单、`backend/src/Modules/Connections/**` 公共服务/迁移，`experiments/g4-m1/**` Compose/运行器及新任务证据、G4-M1 E0最小消费者；每次现有非G4共享文件写入须合同与独立 Review 明确允许。
- PG/Backend Worker（有必要才开，Medium）：仅源码测试/PG fixture/必要 Adapter 安全补丁；UI Worker（有必要才开，Medium）：仅 `apps/web/src/features/connections/**` 与相关 G4 页面/测试。两者不得并写公共 Host、锁、OpenAPI、生成物；Master 负责生成链及整合。
- Reviewer（High，非作者）：R0合同、R3逐镜像许可、R4产品运行前、R5完整验收四次只读独立审核；不允许自审通过。
- 不合并 main、不写 G3 正式发布/四源 RDF、G6 或客户生产系统、不访问 OpenAI/DeepSeek API。仅本任务合成 Secret，文件不进 Git/ZIP/普通日志。

## 资源回收与失败退路

- 运行所有外部命令前记录 TaskId/RunId、准确绝对路径、Docker context/engine、已存在容器/卷/镜像/网络/缓存和可删除理由。新增资源用专属 Compose project `ontology-g4-m1-recovery-001`，避免和旧 `ontology-g4-m1-connection-001` 身份混淆。
- R2 下载的独立镜像 layers 可能与既有资源共享，**不能按镜像名称或时间猜测删除**；先检查 ID、digest、所有引用、准确 ownership。无歧义的本任务独占临时容器/网络/卷结束后回收，生产/旧 G3/G6及不明归属资源 KEEP。不得执行 `docker system prune -a --volumes` 或修改全局 daemon。
- 每个受阻点输出 blocker ID、真实命令/exit/timeout/字节/回执/已用资源、最小解除条件；不可因上游镜像 license 未闭合擅自更改用户协议或跑假的49项 PASS。

## 任务结束与唯一状态

- 成功：`G4_M1_RECOVERY_READY_FOR_CHATGPT_REVIEW`，**仅在实际49项本地产品验收及独立Review均PASS时**。
- 阻断：`G4_M1_RECOVERY_BLOCKED_WITH_WITNESS`，留住已有已完成产品代码与原证据、精确授权缺口。合规阻断不可用更换未审镜像、容器执行或放松安全负例绕过。
- 在任何状态均停止并等待 ChatGPT 独立复审，不合并 main、不启动 G4-M2。
