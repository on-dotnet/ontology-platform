状态：PROPOSED_G4_CONTRACT / NOT_IMPLEMENTED。TaskId：G4-00-CONTRACT-001；Master 单写。基线 d1a61daffe844475b07705797e3ad325cc3f2945。

本文件为 V1.1 输入的仓库合同入口。下列引用章节按原字节归档，属于本合同的详细定义；当前裁决优先于输入中的建议，G2/G3 冻结合同优先于 G4。输入包历史“未授权”描述保留，2026-11-01 用户明确批准本任务仅合同归档、验证、独立 Review；不是产品实施许可。

## 依赖与授权

G3冻结→G4-00合同复审→另行批准M1 PG连接闭环→M2四类Adapter→M3 Mapping治理→M4查询六态与受控能力→M5整合。G5/G7依赖G4；G6 Docling支线锁未完成且不并main，不阻断本合同，不默许其集成。完整 C-01..20/S-01..70 见[验收矩阵](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/08-STAGES-ACCEPTANCE.md)。所有S项仍NOT_RUN。

## 下一G4-M1授权申请（尚未获批）

申请仅PG合成隔离环境：五类型动态配置UI、PG真实创建/测试/编辑/停用/审计与受控metadata，连接管理权限/Secret策略先冻结。Master独占Contracts/Host/迁移/锁/生成链，Adapter与UI在独立树非交叠写入，非作者安全/UX Review。需先批准精确依赖/镜像/许可、Secret存储方式、网络与资源白名单；G4 E0消费者支持需单独列公共脚本变更。不得以该申请进入M2–M5、真实生产、收费模型或G6集成。

最短正反：真实PG TLS与只读账号、跨schema/scope拒绝、Secret不回显、旧probe失效、同key异payload409、CAS冲突、真实OIDC/HTTP/浏览器恢复。稳定输入完成适用本地完整验收、独立Review、提交绑定、V3和资源收尾；CI按需NOT_RUN。缺环境不以mock代真源。

## ADR与风险裁决

| ADR | 提议 | 状态/解锁证据 |
|---|---|---|
| G4-ADR-01 | 独立元数据schema与SecretRef | PROPOSED；实施前确定secret store/生命周期/审计原子性 |
| G4-ADR-02 | typed SPI与独立方言 | PROPOSED；逐驱动精确版本/许可/只读类型负例 |
| G4-ADR-03 | Web GET与网络白名单 | PROPOSED；实际socket/重定向/DNS/OAuth/代理拒绝 |
| G4-ADR-04 | Ontop PG/Oracle对照 | PROPOSED；另批环境后比较正确性/权限/性能/运维 |
| G4-ADR-05 | 独立MappingRelease | PROPOSED；canonical字节、异人/CAS/审计/回滚故障 |
| G4-ADR-06 | G4QueryResultV1/ReadReceipt | PROPOSED；六态、时间/证据精度及G2兼容真实回归 |
| G4-ADR-07 | 新权限与审计action | PROPOSED；明确角色映射/白名单/拒绝审计，默认不授予 |
| G4-ADR-08 | 双架构与资源 | PROPOSED；批准镜像/许可/平台实际测试及精确回收 |

八ADR均 BLOCKED_FOR_IMPLEMENTATION，设计归档不等于依赖或实现批准。新增错误码/权限/API/DTO仍PROPOSED。现有G3合同胜出：旧DTO/Manifest/SourceBundle/Identity/Run不改；G4无图证据不投射成G2伪图；query预算不扩大。需改变以上边界即REQUIRES_USER_DECISION并停对应项。

## 非作者 Review 提前发现的实施阻断

- G4-ADR-06 / M4：G4SemanticDatum仅来源链子集，完整值/单位/时序/关系端点判别Schema和字节回归待ChatGPT裁决；必须在M4实现授权前冻结。
- G4-ADR-05 / M3：MappingProposalView仅PUBLISH子集，ROLLBACK固定targetReleaseId/manifestHash的判别读写合同待裁决；不能借M3实现自行补字段。
- RQ-01实体选择断链已在本任务补充PROPOSED设计Schema及合成正反例修正；原V1.1输入原字节保持。状态词层次RM-01、授权拒绝RQ-03已澄清。以上不是产品测试，也不自动批准M1。
