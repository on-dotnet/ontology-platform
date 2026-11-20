# Oracle 单表执行入口修正与 S1 实测记录

任务为 G4-ORACLE-MAPPING-QUERY-001，产品 Run 为 product-resume-01。Base 为 `326c7e1fd97f2327a25fa510071115d9eee7c5bb`。持久替代资源仍归 implementation-01。

## 修复前的实测原件

| 边界 | 运行见证 | 证据 |
| --- | --- | --- |
| R1 | 三个实际模式的 JS ready 传入当前产品 Run，Python 在首次外部读前错误拒绝 | 独立树原始命令 `c0e987b7863741e8aed067bc63a9e3bd` |
| R2 | 旧 Python 传入的 ready.json 路径不符合已编译 C# 要求的 session-ready.json 路径 | 同一命令，修前记录 SHA-256 `513136708f9b3bf09ea02816fbf7aad4320dff7821811b84c082e16f9d4d4723` |
| 读取完成后的取消结算 | 旧实现第 1001 ms 仍调用 CAS，当时原总期限余 3999 ms。测试驱动核验了实际旧程序集，未使用真实 PG 行锁 | 独立旧见证命令 `f0695c47eb2943e8adac224e3b9a8001` |
| R3 | 已审冻结替代卷的两次全读为默认图 0、命名图 1372、发布图 46 和 1326 条。历史关闭钩子 UNKNOWN | 6.2.0 上游提交 `d0676a2c402ead68a133596f4ac5977be64dd251`，新停止/重开入口初次离线回归 `f0dc642b5662496a995121fa85aacb8f`，14/14 |

以上为早期精测使用的代表材料。Oracle S0 的 AC03-B 仍为 BLOCKED，cleanup250ms 为 NOT_QUALIFIED，G4 为 PARTIAL。

## 本批结论

**R1、R2、R3 的入口修复已验证，AC03-C 的受影响结算用例通过。正式 AC03-A 与 S1 因本次四会话认证缺少交互而阻断。** Oracle S0=BLOCKED，AC03-B=BLOCKED，cleanup250ms=NOT_QUALIFIED，G4=PARTIAL。此次未形成 Oracle 产品验收包。

| 项目 | 本次证据与结论 |
| --- | --- |
| R1 | FRESH。三个生产模式分别由 Node 导出函数构造请求并通过原 bridge 送入真实 Python 消费者。两种合法上下文共六个正例，错任务、错执行 Run 和错前态被拒。集成后原件命令 `93d77b26e380463f8bc318b09947c888`。 |
| R2 | FRESH。实测调用方 argv、规范 nonce 与文件名，C# 的固定路径和 CreateNew 保留。错误前缀、nonce、文件名、覆盖以及旧程序集拒绝。新副 API 挂载当前 AgentTests；票据的主体、撤销及 TTL 失败在正式分发中有独立分类。本次正式浏览器在票据产生前停止，四张真实票据及其 TTL 为 NOT_RUN。 |
| R3 | REUSED 为已核冻结检查点的两次读取。FRESH 为同一替代容器本代启动的当前全库和两发布图核验，原件 `start-d8f4bbb99ed642eeaf8a4f5d5af7ee06.json`，PID 64643。默认图 0、命名图 1372、发布图 46 和 1326，三类摘要均与冻结原件相符。业务宿主入口核准确 ID、StartedAt 和 PID。本次停止后保留锁文件，退出 143，无 OOM；进程已退出，关闭钩子 UNKNOWN。额外小型 TDB2 物理实验 NOT_RUN。 |
| AC03-C 与 AC03-A 的组合边界 | FRESH。受控结算 8/8，真实 PostgreSQL 8/8，均无跳过。真实行锁覆盖 RUNNING、FAILED、CANCELLED，新增三行覆盖健康读后及时取消、取消后越过原分支截止、成功在原总期限内先赢及迟到取消 409。测试库 OID 17853 已回收，两次平台检查点散列相同。真实 PG 命令 `92cd82b7d50d4b8ab7bd86026c4c724c`。 |
| 正式四角色前检 | FRESH 尝试 1 次。北京时间 18:39:57 至 18:40:39 的浏览器命令为 `ae2ebad4418249cc99d97f722b4d340c`。首个账号 g2-operator-ab 等待输入到期，未到达 /me，其余三个未尝试。本窗为 0/4。独立重开三个宿主观测、真实命令/双流和覆盖全窗的 Oracle 审计，源审计命令 `4456c5bcc8644660a0b971ac3e91ea8e`。未按 clientId 过滤，FIXTURE_READER 固定业务 SELECT 为 0。 |
| AC03-A、S1、S2、S3 | 正式 A 查询与取消、S1 的正式 Mapping/查询持久化和新 reader 会话按原字节恢复，均为 NOT_RUN。S2–S3 未准入。已接受的历史单账号 1/1 独立保留。本窗没有续授、发布新根或写入源夹具。 |

## 当期资源与恢复条件

准入器实测五个持久替代 ID、两个每个 768 MiB / 0.5 CPU 的 API 配置和原 KEEP，计划峰值为 13.75 GiB / 10.5 CPU。API、QueryTests、AgentTests 三套构建同属后端输入 `7ff360c3d812256db08c065871ece27b11ca8f1e554bc5c713b2994daa08c52f`。两个新 API 的匿名 /me 实际均返回 401。各实例、构建、挂载和保护清单的准确身份见机器回执。

关窗前和业务入口关闭后的七项在途计数均为零。两个无状态 API 经 TERM、退出和移除后验。五个替代持久服务均已停止保留，旧 17 个 STOPPED_KEEP 和三个原持卷运行者按准确 ID 保持。关窗原件操作号 `41d91153a3e94824875cbd27265fc2ed`。

恢复产品运行需要对应操作者在本机正常认证，取得当前四主体、角色/站点及至少 210 秒的有效票据。原 15 项同范围授权在北京时间 18:41:34 只读回查时均满足 210 秒，最晚到期为 20:24:06；下次须重新回读。原授权允许对同四主体、同连接、实体表原 11 个字段限时续授，第二表须另有明确可核授权。保持 250 ms 清理、1 秒分支、5 秒总预算。AC03-B 缺同一次正式在途取消的独立源端因果证据。

## 工程资格与原件

- 正式环境准备零下载，21 个项目、179 个包。完整性检查曾发现 17 个额外 Python 字节码；已逐一核对并原样移入本批 ignored 保全区，再用原 prepare 通过。首次沙箱无法读引擎的记录和额外成员拒绝均保留。
- 代表报告经生产证据发布及无损重开。干净检出在 `94901e4dc02fbfd85566688b8ece7cd7806bce27` 运行 MemberPlan 及 MeasureOnly，报告原字节纳入，候选内存精测 7,122,263 字节，状态 MEASURED_NOT_READY_FOR_ACCEPTANCE。
- 正式测试入口在 `d90fd032676813c48b712be2aadce0f950e4381c` 运行 51/51，命令 `d0315377a78d459abac5e95aebea5153`。其中离线断言不计作正式 Oracle 四会话或产品实测。全工作树实际静态扫描在 `6d2a2976f2d54f54637b6fb364fe2c0444639644` 通过，覆盖 24,566 个文件。四个未跟踪的 Finder 文件保留，已提交范围的计划使用同一候选的干净检出。
- 当期认证与 PG 实测提交均为 `6d2a2976f2d54f54637b6fb364fe2c0444639644`，后续增量登记工程门禁和交付材料。原 503 项 SelfTest 保留原历史身份。本批完整 SelfTest、CI 与其他平台均为 NOT_RUN。通用 Oracle verify 消费 implementation-01，当前单场景走 product-resume-01 的 --case-command 与准确 mode；通用门禁和单场景的状态分列。
- 干净检出完整映射后 plan 为 PLANNED。通用 verify 在第一项 environment 返回 BLOCKED，原因为 `OMQ_ORIGINALS_NOT_RUN_admission`；实现阶段的 admission/qualification.json 尚未登记。该原件在任务树和 Git 均缺席。当前 auth 的成功资格消费者也准确拒绝本次失败窗口，返回 `OMQ_REPORT_INPUT`。机器回执单独保存了失败事实的 28 项原件重开，未将其签为成功场景。

## 19:20 用户到场后的正式认证窗口

本次实测提交为 `ee7e3df27d6847c09307526920959f42b4584f4f`。主机预检记录 Mac 已解锁，按原配置建立的两个无状态 API 均通过匿名 `/me` 返回 401 的检查。正式 Edge 窗口可见时已发出提醒。

| 项目 | 当前窗口的证据 |
| --- | --- |
| 四主体认证 | FRESH。北京时间 19:20:57 至 19:21:40，命令 `3b9131ecad82459e88b9f2660b285def` 退出 1。首个 `g2-operator-ab` 在表单期限内未返回 `/me`，分类为 `ORACLE_LOGIN_WAITING_FOR_INPUT`。本窗 0/4，其余三个账号和四票据 TTL 均为 NOT_RUN。已接受的历史 1/1 仍归原窗口。 |
| 源端业务 | FRESH。覆盖完整命令窗口的独立审计 `a65e93a7464c4156adb99cfa9465ac98` 未按 clientId 筛选，FIXTURE_READER 固定业务 SELECT 为 0。正式 AC03-A 与 S1 均为 NOT_RUN，S2–S3 未准入。 |
| 授权与资源 | FRESH。19:22:13 只读观察到原范围有效授权 15 项，均余至少 210 秒。关窗操作 `ce83cef37f794bd8bc76787a4ee54c59` 的两次七项排空计数均为零，两个无状态 API 已移除，五个持久替代服务已停止保留。Fuseki 退出 143，其关闭钩子仍为 UNKNOWN。 |

前次 18:39 窗口与本次分别留存。AC03-B 仍为 BLOCKED，cleanup250ms 为 NOT_QUALIFIED，Oracle S0 为 BLOCKED，G4 为 PARTIAL。
