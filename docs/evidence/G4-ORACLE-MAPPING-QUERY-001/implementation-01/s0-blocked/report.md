# Oracle Mapping/Query 实施阻断交接

**S0 BLOCKED，G4 PARTIAL。** 正常 100 行下，固定 SQL 自然到达 EOF 后，正式取消才提交。非作者复核同一执行，维持 NO-GO。S1–S3 未准入。

## 同次请求

| 事项 | 当期观测 |
|---|---|
| 身份 | 正式试验提交 dfe38a6c4ca5ab217361136dc2a07e949e70a38a，API 构建源 3235fc2c3bd1a7a3df1139cede9841c0cd1ff4eb，snapshot ac3370165c2817682f81e7809ca33c39c7fa9a4d63e543c1d0a5964850c9da3e |
| 查询 | query-18b5ee00b53e4e4eafc43cc4717bd293，ClientId 0e224578b55b4b479d98d3fa4ff1ac46，SQL_ID dum3m3c96vc07，SQL_EXEC_ID 16777219，串行计划 1347626742 |
| Oracle | 2026-11-19 UTC 16:07:38.6097473 执行，16:07:38.6111068 EOF，相距 **1.3595 ms**。同一源游标增加一次执行、一次 EOF、100 行，PX 为 0。21,288 次独立采样。窄统一审计按 ClientId、会话及对象关联，返回码 0 |
| 平台 | 取消请求返回 200/CANCELLED，执行请求返回 503。PG 的 LeaseUntilUtc 减 250 ms 为 16:07:38.785482，该同事务 SQL 时刻早于 CommitAsync。计入两端时钟和精度误差，**此较早前界仍晚于 EOF 至少 174.005 ms**。16:07:38.786465 已读见 CANCELLED，主 API 在 16:07:38.7940100 观测并传播取消，16:07:38.7986804 记录物理释放 |
| 持久后态 | 一条正式取消审计，零成功结果、零成功回执、零成功审计。owner oracle-execution-004f5b3e04084f1998201939aaeec5e6 保留，终态 fence 2，源读者会话为零。当次没有定向取消命中业务 SELECT，也没有同次原生 1013 |
| 证据限制 | 正式 Store 的手工 DI 工厂漏传日志记录器，原运行缺少 CommitAsync 两侧精确区间。原自动字段 formalCancelCommitted=false 反映分类器缺少提交事件；持久状态和审计证明了提交。原 naturalCompletion=false 指取消场景的完整分类；游标和 EOF 证明该 SELECT 自然读完。原件保留。物理释放和无残余不能替代当期占位确认 |
| 独立对照 | 自然对照 query-8453cb0c18c947e5b9d8114a31d6ab1e 返回 200/FOUND，56 项检查，释放槽位，零源残余，成功结果、回执、审计各一。此前同命令工厂 ODP 直取消至物理清理为 9.0965 ms，证明范围限于源能力 |

[正式取消源端原件](originals/formal-witness-071127c7-2a34-40d7-9675-7cf967edfdb0.json) · [正式浏览器](originals/browser-s0-oracle-cancel-1795104451303.json) · [真实 exit 1](command-originals/b1879ba239ea4344a9db482d1dfd9140/receipt.json) · [自然完成原件](originals/formal-witness-cdbd7aa6-5d68-438d-aa3a-530f4189396c.json) · [两表还原](originals/formal-window-fixture-38c990414dfa4795a0c50a3ac9c2a0fd.json)

## 验证范围

- **FRESH。** 锁定 TCPS、11 列、显式驱动事务和独立写者提交、替代式源冷恢复、窄源观察，Web/SSR/双 API relay，真实四主体 OIDC、G3 发布、目录发现、异人 Mapping 审核、激活、三项权限各限实体 11 列。provision、mapping、ready 在各自原提交完成 76、57、46 项检查。另有七个源码定向用例及独立真实 PG 的占位、Sweep 和 fence CAS 用例。这些结果仅覆盖所列 S0 子项。
- **FRESH 离线修正。** 在 45a986abc4cbe97cb8b4570d8c54ad284541e1e1 编译并从正式注册解析 Store，logger 接线回归 1 项通过；工程资格离线回归 7 项通过。两个已封闭的 API 始终使用原实测构建。原配对外壳返回 0 并在正文记录 FAIL，正式取消浏览器命令 exit 1。任务分支已修正外壳的退出传播，未重跑产品链。
- **REUSED。** provision、mapping 和自然完成原件的重开限各自实测提交。ready 相关核验输入已有后续修改。早期生产 MemberPlan/MeasureOnly 恢复自 7d113e3ca9e6dc1b91722fe320c429ae1ace0cce，1,019 个成员，估算 6,793,410 bytes。PG/Doris/Oracle M2 历史字节按原身份保留，整集超时及 134 个唯一用例覆盖、格式 exit 2 和 271 条继承诊断仍按历史原件解释。
- **NOT_RUN。** 新 Head 的正式取消正例、整套 S1–S3、E1 四个正式拒绝场景、新平台首次整栈冷备与替代恢复、最终整栈冷备与恢复、最终 V3/同包重开和 CI。

[源能力和失败原件索引](../s0/originals-index.json) · [早期精测](../early-measurement/implementation-01/early-plan.json) · [DI 离线修正](originals/formal-di-offline-01.json) · [本批原件索引](index.json)

## 资源与集中待决条件

两表由 100/1 恢复至 1/1，前后逐表散列一致。停止前连续两轮、每个 API 退出后的检查均显示活动查询、Agent Run、未完成 Mapping job、未投递的两种 outbox 及源读取会话为零。两个任务 API 已优雅退出，持久占位、原容器、原卷、私有材料保留。新源 Oracle、平台 PG、OIDC、Fuseki、RustFS 继续按原 ID 运行；替代 Oracle 保持退出。旧 17 个 STOPPED_KEEP 与三个原持卷运行者逐 ID 核对。首次源库冷副本已替代恢复；新平台整栈恢复待验。

1. 保持本次 S0 NO-GO。若继续验收，须先裁决一个可复现的时序，在实际固定 SQL 仍在途时完成正式取消提交，并写明相应数据、权限、资源及恢复边界。当前 100 行和 250 ms/1 s/5 s 保持有效。
2. 重启此正式连接前，明确这条终态未确认 owner 的任务级恢复步骤、身份和判据。保留原失败及完整证据。此前继续封闭两个业务入口。
3. 如需释放新栈，先核完整平台状态与私有材料的一致备份及替代恢复，包括 PG 行和权限、OIDC realm 签名、TDB2 图/SHACL、带版本的 S3 原字节以及下一阶段资源余量。旧资源仍按原条件保留。

[封闭投递和逐项后验](originals/s0-blocked-seal-01.json) · [资源状态回读](originals/blocked-resource-status-8d9fbea11fc74732b91a700449e7c9ec.json) · [非作者结论](non-author-review.md)
