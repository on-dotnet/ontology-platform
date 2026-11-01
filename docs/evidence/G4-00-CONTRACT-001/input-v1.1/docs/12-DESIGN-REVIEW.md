# 12 · G4-00 V1.1 修订自审与 V1.0 历史结论纠正

**历史结论纠正**：V1.0 的 `DESIGN_REVIEW_PASS_WITH_IMPLEMENTATION_GATES` 未覆盖完整 JSON Schema 及跨文件矛盾，用户独立审查已正式给出 `REQUEST_CHANGES`。**本 V1.1 不是在历史结论上补一句PASS，而是据 4 条缺陷重建并验证相互一致的合同**。这是作者侧的**设计自审**，不是 Codex 独立Reviewer，不是 G4 真实运行测试，也不代表正式产品已上线。审查输入：G3 main准确Head、仓库冻结G2/G3规划与合同、用户已确认前端/后端/五源/主线、G6-P0阶段和官方连接器/安全/Codex文档；输出本ZIP的 PRD/UI/技术/安全/数据/AI/阶段合同。日期 2026-11-01。

## 审查维度与结果
| 项目 | 发现与处理 | 结论 |
|---|---|---|
| G3冻结格式与历史兼容 | G4不改G3 RDF/Turtle/SourceBundle/Manifest/审批; MappingRelease独立 | DESIGN PASS |
| 五源配置闭环 | 五源独立参数、类型输入、测试、权限、保存/编辑/禁用；不再只有来源系统名称 | DESIGN PASS |
| Source-Adapter与模型差异 | Doris虽MySQL wire但有类型差异；TD优先WS；Oracle service/owner；API GET白名单 | DESIGN PASS / RUNTIME NOT_RUN |
| 产品操作闭环 | 13界面单元、所有关键动作、状态机、错/冲突/恢复与 API映射 | DESIGN PASS |
| AI Native | 无模型仍可工作；AI负责建议和异常收敛，人处理关键判断；正式发布异人审核 | DESIGN PASS / MODEL NOT_RUN |
| 身份与时间 | G3-M4 org/site/source namespace/时间区间；未知单位/时区/水位保留；同号无隐性合并 | DESIGN PASS |
| 确定性数据安全 | 来源只读三层+Gateway typed plan+SSR F/DNS/重定向/HTTP payload控制 | DESIGN PASS / SECURITY RUNTIME NOT_RUN |
| Mapping治理 | Revision、SchemaSnapshot、OntologyRelease绑定+Diff/Assessment/Proposal/Approve/Active/CAS/回滚 | DESIGN PASS |
| 统一语义查询 | 现有G2六态+有界限额，证据按来源且实时权限复核，不发明第二套gateway | DESIGN PASS |
| G4主线连续性 | G4-M1~M5、G5/G7/G8依赖正确；G6-P0不阻塞G4也不自动并入main | DESIGN PASS |
| 跨平台与成本 | Compose是单节点标准入口；Mac ARM/Win WSL2 AMD/目标Linux，镜像/驱动许可另批 | DESIGN PASS / RUNTIME NOT_RUN |
| 防返工与工程效率 | 先合同、最小PG纵向、适用测试分层、非作者review、任务资源KEEP/DELETE、唯一V3 | DESIGN PASS |
| 输入包/执行授权 | 只有一份Codex权威执行合同+启动词，**当前没有Codex执行授权** | DESIGN PASS |

## 本次主动纠正的潜在设计陷阱
1. **原型不闭环**：把五源配置差异、动态表单、错误归因、Secret轮换、启停、Schema和查询串成真实用户旅程。
2. **“只读”的错误安全感**：只看SQL前缀不够；采用源账号权限+typed计划+执行限额并设计安全负例。
3. **前端按业务数据源统一使用通用URL**：纠正为五类精确连接契约，WebAPI特殊SSRF审批；TDengine REST是带SQL的厂商接口不是通用WebAPI。
4. **G2 Gateway预算漂移**：G4交互查询必须继续遵守目前 `maxRows≤100/timeoutMs≤5000/depth≤5/Run≤30s/3 tools`，不能未授权提高；Schema扫描是不同异步任务。
5. **用当前Schema重解释历史Mapping**：固定SourceCatalogSnapshot和OntologyRelease，Schema漂移导致revalidation，保留旧审计引用。
6. **把G4事实写进G3 source/dataTurtle**：G4虚拟/按需查询，MappingRelease独立；G6文档事实和G4源事实在G7合流而非写同一个权威图。
7. **过度模型调用**：G4默认离线规则可用，有合法模型策略才允许AI增强；高置信度不等于已审批，输入字段注释仍属于不可信文本。
8. **过早宣布五源均可用**：G4-M1只完成一个真实PG纵向切片，其余UI/适配统一设计但运行仍NOT_RUN；M2~M5再完成真实源/查询。
9. **错误的生产HA承诺**：Compose直接启动不等于多机HA、多实例密钥共享/200并发达标，G8另测。
10. **“Codex任务包”被视为立即执行授权**：在README/09/10重复标注一次清晰边界；本次不实际启动Codex与工具。

## 仍需下一阶段裁决的 ADR/外部条件
- 8项 `G4-ADR-01..08` 全为 `PROPOSED`。完成精确合同审查和首次隔离源测试后分关口决定。
- Oracle ODP.NET 商用分发/驱动与源版兼容、Doris真实 FE/Connector兼容、TDengine C# WS企业版与时间精度/WebAPI私网许可、Npgsql TLS、Docker ARM64/AMD64 的实际证据均为 `NOT_RUN`。
- 五源真实隔离测试环境需要未来用户明确提供或批准专属合成容器/镜像；没有真实源就保持`BLOCKED`，不能用Fake/Mock装成真实连接。
- 模型服务中心六Provider目前只是 G6 PREP 设计，不代表G4 AI模型已能实际调用；本次没有模型Token或收费权限。
- `G4-00-CONTRACT-001` 可以**另行批准 Codex 文档合同落地**；`G4-M1-CONNECTION-001` 只有该工程合同复审及独立用户授权后才能启动。

## 自检证据
V1.0 曾执行 8 个正向设计例校验，但未覆盖四项审查反例；V1.1 新增 21 个正向、16 个Schema必失败负例以及3个Schema合法但语义必须拒绝的负例，并执行完整 JSON Schema Draft 2020-12 校验；检查 5 connector、6 Query statuses、13个 UX 单元、20条设计验收与70条未来产品测试ID，以及档内禁用提前执行的文案。生成后另执行 ZIP CRC、Manifest 的成员数量/大小/SHA256与重开。**这些检查是输入包及设计内部一致性，不是实际 G4 产品/API/容器运行验收**。

**总状态：`G4_00_DESIGN_PACKAGE_READY_FOR_USER_REVIEW_EXECUTION_NOT_AUTHORIZED`**。

## 2026-11-01 V1.1 修改记录与自审限制

- CR-01 查询输出：已补全部11个G2同名概念字段、新G4SourceEvidenceRef、2个AMBIGUOUS候选、版本化结果与无损转换边界；旧G2 DTO/REST并未被修改。
- CR-02 创建请求：Schema、样例、API、UX统一 `config/secretRef/command` 且首次expectedRevision=0；旧 `type/connectionProfile/secretInput` 输入拒绝。
- CR-03 认证引用：TD profile 移除 credentialRef；唯一顶层 secretRef；匿名 Web API 为 null，认证模式必填；安全上传独立通道。
- CR-04 Mapping读：新增 List/Revision/Diff/Assessment/Proposal/Release/Active GET，UI 保存/审批/刷新/历史步骤全部对应。
- 下一轮 Codex 合同审核仍须独立非作者Reviewer和后续用户授权；真实 G4 产品/运行仍为 `NOT_RUN`。厂商依赖/许可未在此次合同修订中重验证。

补充：V1.1 含六态全部合成样例、PENDING/APPROVED/REJECTED 提案示例及 X01..X03 三条 Schema 合法但交叉证据/非作者规则不合法的设计反例。它们仅验证设计校验逻辑，真实运行状态仍 NOT_RUN。
