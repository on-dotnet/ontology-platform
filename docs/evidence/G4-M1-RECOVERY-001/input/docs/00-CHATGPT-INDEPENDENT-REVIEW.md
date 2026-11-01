# G4-M1-CONNECTION-001 — ChatGPT 独立复审 v1.0

日期：2026-11-01。范围：**已上传的 PARTIAL/BLOCKED_WITH_WITNESS Review ZIP V3 及独立重开回执**。本次为读包/源码静态复审，不具有用户机器的 Docker Engine、.NET 10 原生运行环境，也不执行正式 PG/OIDC/browser 测试。

## 1. 精确身份与审查结论

| 项目 | 实际证据／结论 |
|---|---|
| TaskId | `G4-M1-CONNECTION-001` |
| Base | `8afc5d4dfd32e7adb48262cce6587057c0e68715`（已审 G4-00 合同分支） |
| Head | `59edb405dfb4acf4d4a259cffdc3551bafa90d2c`，远程 `codex/g4-m1-connection-master` 已核实 |
| TestedCommit | `958dc6c4eb121958ae889213d1a523a7e7914ce8`；远程 Test→Head 对比只含任务证据文件 |
| G3 main | `d1a61daffe844475b07705797e3ad325cc3f2945`，未变 |
| ZIP | 2,778,865 bytes；SHA256 `070b2ab9ad1a3ad8c5e8de859f0b4018c7f5258eb9a3aea3f08ba6f0b4af371b` |
| ZIP 校验 | 759 members CRC PASS；758 条 SHA256SUMS PASS；755 source mappings 的字节 SHA/size PASS；不安全路径与同名冲突未发现 |
| Git 绑定 | GitHub HEAD 的 755 条范围内 Git Blob 列表与 ZIP manifest 的 755 条路径/OID canonical fingerprint 一致（FNV32 `65cfaf82`） |
| 状态 | **PASS_FOR_BLOCKED_HANDOFF / PRODUCT_NOT_ACCEPTED / LOCAL_PARTIAL** |

## 2. 能力证据与不能扩大解释的事项

- 已提交的 **15 项严格 DTO、21 项 PG Adapter 本地负例、73 项 UI 组件测试**日志均载有通过计数及零失败；实际 Host 构建、TS Typecheck 和工程 SelfTest 也有原始回执。这些是在提交环境执行、由本复审核对原始日志/提交绑定的事实，**不是我在当前环境重新运行 .NET / Vitest**。本环境只有 Node22/Python，无 .NET10/pwsh，不能替代用户机器验收。
- 源码包含独立 Connections EF schema/未应用迁移、Npgsql 只读 Adapter、证书 VerifyFull 与 fixed target、SecretRef/AES-GCM、持久 Probe/Catalog Job、审计、五类动态表单、Host/OpenAPI 接入。上述仅证明具备可审核的**DRAFT 产品实现**，不能证明真实可用。
- 非作者审查曾找到并修复 Probe 同值编辑失效、同键重复源 IO、恢复审计、ETag 分类、UI sessionStorage 机密缓存等问题；这有真实开发和复审价值，不应要求从零重做。独立审查没有证明真实 PG 事务、TLS、OIDC、浏览器和权限撤销链。
- **49/49 项真实产品验收 NOT_RUN**；Compose/runtime consumers 未交付，runtime preflight `BLOCKED/exit2`；Docker 镜像层拉取 0、新建容器/卷/网络 0；CI NOT_RUN；Windows/AMD64 原生、真实商业许可证据均 NOT_VERIFIED。
- 资源：4 个本任务符号链接准确移除、外部工具目标保留，monitor 已停止；Master/PG/UI 未合并 Worktree 的唯一源码和证据仍 KEEP，不得清理。

## 3. 阻断根因（制度/门禁，非 Docker 运行失败）

附件 `docs/06-M1-COMPOSE-RESOURCES.md` 原门禁把**完整运行镜像中所有组件的许可证据**置于**任何镜像层下载之前**。但精确镜像没有都附可直接远程读取的完整 SBOM；OS/JDK/RPM/DEB 库许可证据通常必须访问具体镜像层、软件包清单/版权文件或通过 image scanner 才能核查。因此这道门禁存在前后顺序上的循环依赖。Codex **正确执行了不得擅自豁免已批准门禁**的约束。需要新用户授权修订门禁顺序，不应再做一轮同样的无层远程查询。

精确证据：`postgres:18.6-trixie`、`quay.io/keycloak/keycloak:26.8.1`、`mcr.microsoft.com/dotnet/aspnet:10.0.13`、`node:24.22.1-trixie-slim` 的 manifest/index 与 ARM64、AMD64 候选 digest 已查；Keycloak、ASP.NET 精确运行 OS 层没有完整远程许可证据；Postgres/Node SPDX 中仍有 NOASSERTION、libxcrypt/tzdata 精确 URL 缺失。缺证据**不等于非法或许可证缺失**。约 600,460,317 compressed bytes（ARM64）、1,207,045,092 bytes（两平台总）仅是观察到的 manifest 层大小，不等于实际磁盘占用或已获授权下载。

### 推荐的替代门禁（**需用户另批**）

- **A / 拉取前**：官方来源、索引+平台 digest 固定、已知项目级许可证和明显禁用条款、请求域名、资源预算与本任务身份安全检查。
- **B / 隔离取证**：在明确人类批准的任务专属临时环境中，仅按已锁 digest 获取最小需要的 ARM64 镜像层，不运行容器、不向第三方上传凭证/文件；以既有 Docker Scout 或批准的只读工具对**实际本地镜像**生成 SBOM / 提取逐组件 SPDX、NOTICE、copyright 和缺失分类。下载上限、文件空间与资源归属应由宿主机制监控，不能只靠注释或估算。
- **C / 独立裁决**：Reviewer 检查具体包的权利义务与商用分发风险。绿色准入才运行合成测试；无法明确法律许可或高风险条款标记 AMBER/RED，需人类或法务裁决，不以“没报错”认定合法。研发内部验证许可与后续商用发布许可证据分别管理；G8 发布仍必须完成法律/许可清单与 SBOM 归档。
- **D / 真实纵向验收**：满足运行准入后，恢复已有 G4-M1 产品 P3–P5，实际运行 49 项矩阵、真实 PG TLS/源端只读、OIDC/HTTP/UI、恢复、审计及资源收尾。投入运行时不重做已验证且源码输入不变的组件测试。

参考官方：[Docker Scout SBOM](https://docs.docker.com/reference/cli/docker/scout/sbom/)、[Docker Scout 远程与本地对象选择](https://docs.docker.com/scout/how-tos/artifact-types/)、[Docker SBOM/attestations](https://docs.docker.com/scout/how-tos/view-create-sboms/)。**注意** `registry://` 即使不在本机 Docker image store 留镜像，也可能读取镜像层，须计入新授权网络/下载预算。

## 4. 新发现、须下一轮先验证的代码边界

**P2（源码静态检查发现；产品运行尚未验证）：** `backend/src/Hosts/OntologyPlatform.Api/G4/G4Endpoints.cs` 第37行仅在 `ContentLength > 65536` 时拒绝请求；对于不存在或伪装的 Content-Length、HTTP/2 流式请求，没有在本层按实际累计读取字节数执行 64KiB 硬限制。即使存在 Kestrel 默认请求体上限，也不能替代合同约定的 64KiB。下一轮应首先由非作者确认宿主真实上限/中间件，再通过明确读取限制或 RequestSizeLimit 与负例证明无 Content-Length 超限也被拒绝，且在业务/Secret/审计状态产生之前拒绝，避免无界反序列化。本项不宣称已经在生产复现 DoS。

另须保持明确：PG Adapter 当前为 `pg-source:5432/fixture/fixture_reader/production` 合成源固定配置。它是 M1 合成试验安全边界，不代表产品已具备任意 PostgreSQL 生产源的可配置连接能力。M1 本轮验收过关后仍需 G4 后续独立扩大真实目标能力及 SSRF/出网/凭据/只读风控。

## 5. 裁决与主线

- **通过本轮 PARTIAL 交付的完整性及受阻处理**，不要求回滚有价值的 P1/P2 DRAFT 源码，不允许将其合并 main 或描述为运行成功。
- 当前 G4-M1 保持 `BLOCKED_WITH_WITNESS`，其真实部署、49 项验收及最终产品 DoD 全部未通过；下一授权只需要修改**镜像取证门禁与预算**并恢复原 P3–P5，不要重复另一个纯文档阶段。
- G3 main 保持冻结；G6 维持独立支线 `PARTIAL / BLOCKED_WITH_WITNESS`；G4-M2/M3/M4、G5/G7/G8 不能因此自动启动。
- 建议下一任务 `G4-M1-RECOVERY-001`，详见同交付包中的正式执行合同草案。**本复审不构成新任务批准，也不自行豁免原镜像下载门禁。**

最终标识：`G4_M1_REVIEW_PASS_FOR_BLOCKED_HANDOFF_PRODUCT_NOT_ACCEPTED`。
