# G4-M2-TDENGINE-01｜P0 当前状态

日期：2026-11-13（Asia/Shanghai）。唯一状态：**P0_BLOCKED_WITH_WITNESS**。P0核对文档交付，不表示产品可实施。

| 项目 | 当前事实 |
|---|---|
| Base | `5113d0b9b233e307664c964ae9bf3c1d6b10adfb`；本轮 fetch 后本地 main、origin/main 均相同 |
| 分支 / Head | `codex/g4-m2-tdengine-01`；完整交付 Head 以本卡所在 Git 提交及最终回执为准 |
| 托管树 | `/Users/chasen/.codex/worktrees/g4-m2-tdengine-01/ontology-platform`；原生创建操作 `2f4fc12b-1a35-4efc-ad6e-8b444b7975b8` |
| 角色 / Run | Master 单写；独立非作者只读 Reviewer；RunId=`tdengine-p0-20261113` |
| 授权 | 用户明确批准附件 P0；仅限定文档、小型官方元数据（单响应≤8MiB、累计≤64MiB）、提交及普通push |
| owned_paths | 本卡、`docs/tasks/current-authorization.md` 追加段、`docs/evidence/G4-M2-TDENGINE-01/admission-request.md`、同目录 `metadata/` |
| read_only_dependencies | 根规则/PLANS/冻结架构、现行工程政策、Contracts/G4、Connections、API/G4、Web connections、工程消费者与gate；共享合同仍由Master负责，P0不修改 |
| 能力门 | 官方明确原生WSS为Enterprise能力；社区3.4.0.0起拒绝授权语法，较早社区授权语法不生效。没有已证实合法可用的Enterprise ARM64制品 |
| 唯一待决候选 | Connector 3.2.1 + TDengine TSDB Enterprise 3.4.2.13发行套件（taosd及其配套taosAdapter）/Linux ARM64；配套Adapter实际版本、制品与许可尚未核实，不准入下载 |
| 其他硬缺口 | 自定义CA接口、三层取消见证、元数据DTO保真、任务工程适配器；详见一次性申请 |
| 验证边界 | 产品、prepare/restore、服务、全量SelfTest、CI均NOT_RUN；只做源码/元数据/宿主资源只读核对与文档轻量检查 |
| 下一动作 | 审批[A–F申请](../evidence/G4-M2-TDENGINE-01/admission-request.md)；先提供合法精确Enterprise验证源，补齐硬证据后再裁决获取/实施。网关不是社区权限缺口的替代方案 |

资源 KEEP：本树及本任务分支保留到同会话后续获批、最终交付与明确回收；元数据随Git保留。没有创建容器/卷/证书/数据库。Doris保留卷、私有原件、缓存与旧树未改变；原main工作区6个未跟踪`.DS_Store`原样保留。没有ZIP、main更新、产品修改或后续阶段启动。

文档轻量检查、非作者审查结论和失败见证统一写入[一次性申请](../evidence/G4-M2-TDENGINE-01/admission-request.md)，避免第二状态源。后续沿用本会话、本树、本任务，不另建恢复任务。
