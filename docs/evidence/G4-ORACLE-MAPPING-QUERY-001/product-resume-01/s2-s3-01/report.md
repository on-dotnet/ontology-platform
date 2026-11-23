# Oracle 普通关系读取的元数据成本

**NORMAL_PATH_BLOCKED · S2 PARTIAL · S3 NOT_RUN · G4 PARTIAL。** 准确旧 Q 已恢复。B1 工作耗时 2275.801168 ms，含连接释放 2279.844543 ms。普通分支工作阈值 750 ms、总阈值 1000 ms。前后两次证明视图共 1031.397501 ms，即使耗时降为零，仍需 1244.403667 ms。没有支持产品准入的候选，P1、P2、同 Q GET 均为 0。AC03-B、Oracle S0、cleanup250ms 沿用既有资格。

## 实测成本

同一 GUID `c2c5059355af4c1fbe1852ea560729ee`，单调频率 1 GHz，pre/post 客户端原生身份均为 1/62/250537/915922451844688663/3（实例、SID、AUDSID、统一审计会话、PDB）。表内时间单位为 ms，首行和 EOF 相对各 span 起点。— 表示没有该驱动动作。identity 成功只读一次；privileges 是 scalar。12 条的操作、游标释放及命令释放异常号均为空，丢弃为 0。

| 阶段 | SQL | 总计 | Execute/scalar | Read | 次数/行 | 首行 | EOF | 游标释放 | 命令释放 | 间隙 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pre | identity | 54.315 | 50.861 | 0.885 | 1/1 | 52.804 | — | 0.490 | 0.105 | 1.973 |
| pre | privileges | 86.625 | 86.440 | 0.000 | 0/0 | — | — | — | 0.002 | 0.184 |
| pre | attestation | 864.352 | 863.737 | 0.081 | 2/1 | 864.233 | 864.326 | 0.001 | 0.002 | 0.530 |
| pre | directRead | 49.584 | 48.003 | 0.117 | 4/3 | 48.454 | 48.829 | 0.002 | 0.001 | 1.462 |
| pre | catalog | 159.519 | 155.907 | 0.016 | 23/22 | 157.191 | 157.916 | 0.002 | 0.002 | 3.593 |
| pre | physical | 410.002 | 402.821 | 0.009 | 3/2 | 403.396 | 403.745 | 0.002 | 0.001 | 7.168 |
| post | identity | 0.331 | 0.305 | 0.001 | 1/1 | 0.315 | — | 0.001 | 0.000 | 0.024 |
| post | privileges | 2.478 | 2.475 | 0.000 | 0/0 | — | — | — | 0.000 | 0.002 |
| post | attestation | 167.046 | 167.010 | 0.004 | 2/1 | 167.029 | 167.041 | 0.001 | 0.001 | 0.029 |
| post | directRead | 0.515 | 0.483 | 0.002 | 4/3 | 0.494 | 0.499 | 0.001 | 0.000 | 0.029 |
| post | catalog | 134.443 | 134.273 | 0.010 | 23/22 | 134.302 | 134.384 | 0.001 | 0.001 | 0.156 |
| post | physical | 93.087 | 92.949 | 0.004 | 3/2 | 92.969 | 92.976 | 0.002 | 0.001 | 0.130 |

pre 1624.396209 ms、post 397.900335 ms。驱动各层合计 2007.015374 ms，span 内其余 15.281170 ms。Open 路径已计时操作 222.434917 ms，其中 Open 138.598 ms、TLS 83.356 ms；另有 31.069707 ms 工作间隙未归因。证明视图、目录和打开路径均有成本，单样本无法将驱动等待拆成 CPU、I/O 与调度。旧 Q1 的 545.729209 ms 只定位到 readOnly 内取消，不能用 B1 回填。

## 输入、方法及失败

Base `4a3e3411fb0df6777bf7eb2176dfea4463087225`，B1 控制器 `9a5e5bb65062bf870961d22a5b8cf1c00b4110ec`，离线修订 `5e2f599db71b321834d52dd6f931a125ae340d7d`。构建输入 `34cbe9d480f934fc608515135be496c49202294fdb916f7047c8760cf78bf311`；ConnectionsTests 快照 `9ca96998ce3de5092444d674b1867da381e902e61805474be5be3560e78236ac`、API 快照 `3a554a9525c399a6378e5cfa98d2bd158361959caf1203f36d9c2bc8f2f04900`。两者实际 Connections、Contracts、ODP.NET SHA 完全相同。固定 linux/arm64、.NET 10.0.13、0.5 CPU、768 MiB；测试进程不含 API 的租约、业务事务和并发分支，JIT、调度及线程池状态可能不同。组件只调用正常 Open、四条 ACL、两条目录及同组 post，未创建平台 Query。目录输入 SHA 为 `12de027ed8b81fc5f04af37d165d91089abe28c2d26cb3a3315706474192505b`。测试宿主通过受限只读挂载使用隔离 reader。诊断 8 秒工作、绝对 10 秒、外层 30 秒，外层实际 10.419924 秒。

生产方法按真实 Execute、累计 Read、首行、实际 EOF 和释放写紧凑 span。身份字段并入原 SELECT，原 ACL 判定保留，各条命令在进入下一条前结束其释放计时。新 profile oracle-metadata-v2 单分支 12、双分支 24 span。普通成功路径 98+24 项，失败保守上界 160+24 项，估算上界 89,215 B、导出上限 128 KiB。旧 profile 仅按冻结旧命令和 key 重开。正常目标拒绝测试 1/1、ConnectionsTests 22/22，四个真实 Q1 反例分别移除释放、移除 origin/budget、置外来 execution、无证明改 confirmed；全部被拒。离线修订另核失败阶段终点、span 重叠与 helper 计量，SourceAssociation 5/5。初次构建同名局部变量与反例测试的失败保留。

B1 原件 9660 B，SHA `97bed4844799c0f518c959eefcc4a689bf58cefdfe8f8a0a2d12deb1b8d76b1d`。独立 observer 运行 10.242204 s，双流均为 0 B，连汇总行也缺失。后查 COUNT(*) 返回一行，计数为 0，helper 物理释放返回并移除。活跃时的准确 SERIAL# 没有源端原件，故样本期限内源终止 UNKNOWN；采样次数、最大间隔、SQL_ID/child/计划、等待和本次增量统计也未知。保护监控第二次返回 WINDOW_SAMPLER_EXIT_1，窗控制器退出 1，完整磁盘峰值未知。离线修订分开设置 SERVEROUTPUT、保存两条控制命令回执、把实际已验 helper ID 的可写层纳入额度，并在观察器启动前检查外层收口余量。采集修订未经新的源样本验证。

## 定义、准确维护和额度

实际 READONLY_ATTESTATION 为 VALID DEFINER 视图，列 POLICY_VERSION CHAR(18)、BLOCKED_COUNT NUMBER；FIXTURE_READER 仅 READ、不可转授。依赖本地 PUBLIC_PRIVILEGE_BASELINE、PUBLIC.DUAL 和 SYS 的 DBA_COL_PRIVS/OBJECTS/ROLE_PRIVS/SYS_PRIVS/TAB_PRIVS/USERS。所查 dependents/triggers 均 0。实际定义原流 SHA `2d189afbe0084c0a63f3aacf27663a8aa6e8e87300cc46823dbeaa632bff48f8`。现有证据不能支持仅替换证明视图。DDL、差分矩阵、trace、恢复 DDL 和授权续期均为 0。

关闭原件 `64bdc66845958810935eb00e9b633108b6c5dc7ebf56ea19d030c396a5db5040`。PG 启动前核 normal 生产者、原源代次终止和两 API 缺席；PG-only 窗内用新连接核前态。非作者绑定 proof `a2403b77b406d9c6efdcf3b3839b825e3493954c14d0aa9115bc186aa1faf578`、GO `e1a220b36e73ebdef4c0e5a7bef6c9a9c68c27f0cbe025566f6e063f78d662b4` 后，对 `query-5d891e89221e4a3f8f6893873b1d7a9d` 一次 CAS，仅清 owner、until。新连接读回 FAILED/fence 2、query_source_unavailable，原失败审计保留，新增唯一维护审计 `b1de68dc8ce548898fd27727a0c3453a`，结果与收据为 0。PG 关闭后继 `45e81bff11ee67580201193d50d083f9a85e4a9fb7a953e822f17677603570b4`。d368、f159 新维护为 0。构建期间三个旧默认绑定被覆盖，已据保留的原始输出与快照重建摘要命名副本，逐字节匹配原登记 SHA 后独立重开。

PG-only 108.440749875 s，源窗 78.352728958 s，累计 186.793478833 / 2340 s，余 2153.206521167 s。冻结收口时间 180 s，48 GiB 政策、44 GiB 止损、4 GiB 收尾预留。前置冷态 43,250,315,710 B（7f3b7b0e143840a586d180d9014144ee），PG 开窗 43,255,472,574 B，源开窗 43,261,350,334 B，源窗有效观测 43,316,269,502 B。采样器另保留 1 GiB 检出量，48 GiB 档要求实际计费低于 43 GiB。代次 `65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1|2026-11-23T00:16:12.549726178Z|running`。Oracle 自然停库完成 2026-11-23T00:16:49.192287833Z，PG 完成 2026-11-23T00:16:53.562103002Z，任务运行项空，旧保护资源保留。预算余量不能解除样本停止条件。B2/C1/C2、P1/P2、GET、ABA、十槽、S3、main 合并均 0。未进入产品前置核验，四角色/授权时效和普通双分支余量没有本轮资格。

维护 operation `653cbcda45ee44859dc4065233539d05`，attempt `5b79eaae05a44e94be6b0d6e9410e4f0`。全账本该 proof 恰一 CAS，新连接四项及任务级恢复后继已独立重开。462 个成员，索引 SHA a0fea98789637afbfda9225f868d5d3f6fc6e3e3958de6f2bfd7f73445d9c493。

工程计划退出 0。受影响 verify 退出 2，contract、backend 通过，web 在 OMQ_FORMAL_S2_S3_NOT_RUN 退出 1、测试数 0。未取得正式父的产品成功原件。

## 命令与独立重开

| 用途 | 实际命令 ID |
|---|---|
| create | `3aa3b8d906d248d6aa472347ace65c52` |
| identity | `3c1a9ab6052c4414897d67b6ce29860a` |
| actual | `344a18aed44b425287bed063baac067f` |
| exit | `c9a6a96c1af4409397a3c9d7ff0a891b` |
| remove | `8481ccc0a8ff4cdb91ca594d1072db54` |
| absent | `41c75cbec2f2427ea6aab5e03cba196a` |
| sessions | `b23ac9a3e2534bc3ad5b478add2fec15` |
| postSession | `e3699dafe1674af4a0851d3ae099b48a` |
| catalog | `940ca38ed8674ede996a9b3c8c1f8099` |
| view | `83d09713284d48448da0eb1ebc03c6f8` |
| definitionMetadata | `64852c3f9dfe4ba69af75ab1d4d575df` |
| sourceGeneration | `8d7a25adfff6495fbe364e6367199d8b` |
| cas | `a9e08bfa28934f3480f052d6c4d64f3b` |
| readback_row | `4533f994d89942c58d4e449a121b823b` |
| readback_audit | `d643773b50814ce691d219cedb77b637` |
| readback_receipts | `5d82d418ec15426a9f233eaf5d292009` |
| readback_errorCode | `c0dc275249d449a1b79b90e3bddd6282` |
| connectionsTests | `cafb98e8c8c34fc3ac6b5c20de21ae51` |
| normalTarget | `e7c508baeea044ecba197ffcdea278e7` |
| offlineConsumer | `c835a395be6c42529b142580075aa13d` |
| plan | `055141a048754ed094db3c2e1058b68b` |
| verify | `29bf6f7a6b0a45bba021f5bb74925902` |

/root/cost 独立差分 Begin/End、Execute/Read/Dispose ticks，逐字节重开双流及三模块 SHA，对照源代次收口和两窗时钟。 12 个跨度完整。组件工作 2275.801168 ms，去除两次证明仍需 1244.403667 ms。observer 双流 0 B，采样次数及最大间隔未知。

/root/consumer 运行 WorkflowOracleSourceAssociation.Tests.py，并将真实 B1 span 绑定 Q1 失败事件后以 qualify_normal_projection 逐项重开。 四项指定反例拒绝。失败阶段边界相等接受，晚 1 tick 拒绝，重叠 1 tick 拒绝。旧 Q1 保留 FAILURE_TRACED。

/root/maintenance 独立重开绑定的 386 项输入、父进程及实际源代次终止、两 API 缺席与新 PG 前态，核验 accurate proof 后签发 GO。 GO

下批若另行授权，先用固定输出夹具验独立采集器 summary、准确 SID/SERIAL#/实例/PDB 与缺席读回，以及 helper 在册计费。只在以上通过后申请一个同规格元数据诊断窗，核目录与证明 SQL 的实际 child/计划和打开成本。保持原期限，逐项量化后再裁决候选与产品准入。

## 历史批次原报告（截至 4a3e3411）

# 普通 HTTP 关系查询诊断

**NORMAL_PATH_BLOCKED · S2 PARTIAL · S3 NOT_RUN · G4 PARTIAL。** Q1 首个取消来源为 workCutoff，首个失败阶段为 readOnly.cancelled。只读校验包含会话身份、权限汇总、只读证明、直接对象授权和游标释放。现有事件无法区分内部耗时，离线注入取消仅复现外部症状。单一可修原因未锁定，停止 Q2。 本批清除了 f159 的 owner 与租约截止。Q1 没有结果字节可供 GET，原字节恢复尚未取得资格。

## 两个失败的证据边界

历史正式父 `4032c1d770b240989966ba3275d86999` 退出 1，业务 POST 返回 503，客户端耗时 1671.913 ms。根据时间窗、连接及审计唯一关联 `query-f1599097a7274c20b82cbf0dfcea4e2b`。旧 API 已移除，原收据未保全逐阶段 trace。有效配置为默认 Warning，SemanticQuery 及 Connections.OracleSourceAdapter 为 Information。PRIMARY_CAUSE_NOT_RECOVERABLE_FROM_OLD_ARTIFACTS。776.090 ms 是 API 创建字段到 PG 完成字段的 UTC 差。零次业务 SELECT 只说明该审计窗没有业务读。

三次普通关系请求的归一化请求散列均为 `4530c34dbe04e8e6b5f3608d49d5189364bd94eeff5e3c4e45c82bf078036f44`。历史健康 Q a3b2eaa370fe4f8193d3d2ac817f6f7b 在 A1/epoch121 用时 2762.698 ms，返回 5056 B，SHA-256 为 `1546bdc00a5565fd9a1ad80f37c9dbec9fba11a8c6b0932082c2cad129cf8897`。f159 与本批 Q1 使用 A3/epoch136。健康样本、f159、Q1 的最短授权余量约为 14400、13713、5594 秒。Q1 的 PG 台账共 105 行，本次选用的 15 项授权最短余量为 5593.633 秒，满足 1710 秒要求，续授 0。历史宿主及授权代次有差异，三个请求的对比不足以诊断冷启动。

| 样本 | 源码 | API 快照 | Oracle 容器 | 授权 epoch | 最短余量 s |
|---|---|---|---|---:|---:|
| 健康普通关系 | `851906f140c0` | `56622dd78172` | `65bdf442f567` | 121 | 14399.945 |
| f159 | `9e84841423ba` | `d642579639d1` | `65bdf442f567` | 136 | 13713.168 |
| Q1 | `5318f9b1807f` | `5ed4767eb175` | `65bdf442f567` | 136 | 5593.633 |

完整代码、API 代次、配置和激活身份已写入机器回执。各样本为对应阶段首次关系 POST，源连接池在此前的状态未知。Q1 使用真实 reader，未发送业务预热查询。

## Q1 的 HTTP、时钟和收口

正式父 `e1c70fc2faf344f39c98ac6731a061aa` 退出 1。四角色认证阶段耗时 4874.068 ms。Q1 POST 返回 503 `query_source_cleanup_unconfirmed`，客户端 1718.061 ms。响应没有 Q 头。PG 唯一命中 `query-5d891e89221e4a3f8f6893873b1d7a9d`，与投影和审计的 trace `b7493f3191111571d3a690378ee48ecd`、correlation `89d5324d20fe42ae9cccfe59ea9f4752` 相符。PG 行 FAILED、fence 2，owner 散列 `f155210a2019304736db8f52cc879be44f88045bd28ddcbae06878159f09e08b`，原失败审计 `3e1ca8e4e1af42efa3ac8d0007c8debf`，持久错误 query_source_unavailable。源业务读、结果字节、结果读收据均为 0。未知 owner 留在现场。

下表按实际 API 的 1 GHz 单调时钟，以源分支建立期限为零点。剩余总期限来自事件处的 TimeSpan。5 秒 HTTP、1 秒源分支和 250 ms 清理均沿用原期限。Dispose 和观察器退出计入源调用。租约观察 100 ms 超时、观察器异常、正式取消和请求取消本次均未触发。没有进入目录、事务及业务命令阶段。

| API 阶段 | 事件 | 相对源分支 ms | 剩余 HTTP ms |
|---|---|---:|---:|
| http | enter | -918.184 | 4999.163 |
| branch | enter | 0.155 | 4080.835 |
| initialLease | enter | 0.451 | 4080.538 |
| initialLease | returned | 3.410 | 4077.579 |
| observer | enter | 4.027 | 4076.962 |
| source | enter | 4.459 | 4076.530 |
| permit | enter | 4.865 | 4076.124 |
| permit | returned | 5.557 | 4075.433 |
| acquisition | returned | 14.976 | 4066.014 |
| permitCheck | enter | 64.307 | 4016.682 |
| permitCheck | returned | 64.810 | 4016.179 |
| tls | enter | 64.822 | 4016.168 |
| tls | returned | 67.805 | 4013.184 |
| openCheck | enter | 88.857 | 3992.132 |
| openCheck | returned | 89.209 | 3991.780 |
| open | enter | 89.211 | 3991.779 |
| open | returned | 237.112 | 3843.876 |
| permitReturn | enter | 237.140 | 3843.849 |
| permitReturn | returned | 237.684 | 3843.305 |
| sessionTag | enter | 237.686 | 3843.304 |
| sessionTag | returned | 237.851 | 3843.138 |
| readOnly | enter | 238.110 | 3842.879 |
| workCutoff | signal | 752.838 | 3328.151 |
| cleanupStart | enter | 753.579 | 3327.410 |
| readerCutoff | signal | 765.797 | 3315.191 |
| readOnly | cancelled | 783.839 | 3297.149 |
| cleanupStart | enter | 783.890 | 3297.099 |
| disposeConnection | enter | 783.977 | 3297.012 |
| disposeConnection | returned | 787.785 | 3293.204 |
| PHYSICAL_RELEASE | returned | 787.916 | 3293.074 |
| source | cancelled | 788.049 | 3292.940 |
| observer | returned | 788.067 | 3292.922 |
| cleanup | unconfirmed | 788.115 | 3292.874 |
| http | returned | 795.308 | 3285.682 |

准确宿主 `2c0549a8e4b8d4f9dd8157204c8c24685f702f7c127c2041bd360612004d4041`，进程命名空间 PID 9，模块 `c6d6a558-bfe6-4f65-bb4a-489586a79bbd`。先导出再移除 API，命令 `56bca1e4a9d84523b85a993124b8a48e` 成功。消费者重开 8385 B、SHA-256 `6af20f5eb2369c71d3f95133e2f9d51ccb7bf633e137d7990cffb92cad358bc2`，34 条事件，丢失 0。认证、响应后审计／PG 取证、导出和资源关闭计在外层。API／源 UTC 对宿主的前后误差区间及逐阶段外层时间见机器回执。

本批实际 POST 1/2、产品窗 1/2、活跃 198.185/2340 秒。Q1 用 1 次，Q2 用 0 次。剩余名额随本批停止。两台 API 已移除，前后七项排空均为零，五个持久角色已退出，Fuseki cleanShutdown 为 UNKNOWN。末代原件 SHA-256 `64bdc66845958810935eb00e9b633108b6c5dc7ebf56ea19d030c396a5db5040`。原卷和密钥、九归档、旧 17 加原 3、原 V3、四个 Finder 文件保持。峰值计费 43,236,250,046 B，止损线 44 GiB，总额 48 GiB，收尾预留 4 GiB。

## f159 准确维护

先重开 c35242b898c04ae3ad5529ba346d320f 关闭原件（7735 B、SHA-256 `a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348`）、源代次与生产者封闭证明，再以新连接校验冻结行与审计。仅启动任务 PG。隔离事务 1/1 通过后，`908a039cfe604cadbbf839706c9ec369` 退出 0。一次提交将 owner 与租约截止清空，保留原失败审计 `38ebcc6e08504994b36a322edc4ffd86` 并追加维护审计 `fca8425bb6fc49c28361038ec1d6e90b`。新连接逐项回读稳定行、审计、收据、错误码。该任务级恢复保留原清理失败。Q1 晚维护、d368 重做、A3 回滚均为 0。

## 工程验收与下一关口

Doris 工程入口 11/11，覆盖历史 Git 正例、14 个篡改变体及真实输入改变触发 RF_PRODUCT_REVISION。旧 assessment 仍未资格。Python 定向 4/4，含准确 dotnet 与 AgentTests 构建绑定的两项源关联测试，以及仅替换 HTTP transport 的真实 request 记录到 Python 的 410/seed 后半段。扩展集 5/5，含本次实际 API 投影负例。C# 9/9，完整 Oracle 入口 156/156。发现数与实际执行相符，skip 0。选择收据及实际命令列于下表。

Web 与 interaction 缺少成功的正式父，消费者返回 OMQ_FORMAL_S2_S3_NOT_RUN。当前普通路径及同 Q GET 均未取得资格。先定位只读校验内部的单一原因并验证普通关系与原字节 GET，再另行审查真实 ABA 和剩余 S2。250 ms、AC03-B、Oracle S0 保留原资格。历史诊断／正式父各 1，本批新增 ABA、十槽、S3、main 合并均为 0。CI 与完整 SelfTest 均未运行。

| 检查或取证 | 实际命令 ID | 退出码 |
|---|---|---:|
| 历史正式父 | `4032c1d770b240989966ba3275d86999` | 1 |
| 环境准备 | `4b5bdcb7347345bab911476ed5ca1d8f` | 0 |
| PG隔离维护断言 | `69d3e200d84d4244b8e390f871924ce9` | 0 |
| f159维护 | `908a039cfe604cadbbf839706c9ec369` | 0 |
| Q1普通正式父 | `e1c70fc2faf344f39c98ac6731a061aa` | 1 |
| API导出 | `56bca1e4a9d84523b85a993124b8a48e` | 0 |
| CSharp定向 | `160154146cfd439f9e29d8db39ab2ba3` | 0 |
| Python定向 | `ac1cb3013e14491d81291503a8216a1e` | 0 |
| Python交叉与投影 | `6cfbff661378460f93b0990127c569bb` | 0 |
| 初次完整Oracle | `1fa2c8b17a96474aa04d530532543e9c` | 1 |
| 清环境历史夹具失败 | `cb715030cf9b497fb19bb10d9f92f5d1` | 1 |
| 完整Oracle | `979d8bcf71d249f19b819077438d5cc9` | 0 |
| 已绑定门禁 | `bf696c8eafd644bf833b6b9fc82848d6` | 2 |
| 交互消费者 | `30adb7539cb84c37b86c7764a4e496fa` | 1 |
| 构建-api | `7807f8af509a484ea11b0007ba590437` | 0 |
| 构建-agent | `0d608cea9bf84e73b58359cd127df45e` | 0 |
| 构建-query | `853dd873701749f4a8156a824f2adbdd` | 0 |
| f159前置-row | `36e084afe8ab4763a492f20410544f6d` | 0 |
| f159前置-audit | `70e58d248ea0461091d2c4d51b563884` | 0 |
| f159前置-receipts | `9d39bc60a07b4a49897f6fa80fc0dab9` | 0 |
| f159前置-errorCode | `a65341f6f9154382aec20da3355358c1` | 0 |
| f159提交前-row | `15dd6f279f5f4d2d8d1b555e93597342` | 0 |
| f159提交前-audit | `34f6b0235cfa472ca151d9cac264785d` | 0 |
| f159提交前-receipts | `92fe71a1aa1e4d36bbebd0b5cbef49d2` | 0 |
| f159提交前-errorCode | `365cd37c494f4408875053d731c72bde` | 0 |
| f159新连接回读-row | `303a65a4743947519fa34480a4a2a1fd` | 0 |
| f159新连接回读-audit | `6e00a818c2ea4befb56620c2e80522c4` | 0 |
| f159新连接回读-receipts | `e97f65d4fbf04416bae3b51219d82e1b` | 0 |
| f159新连接回读-errorCode | `794e08f6d9cc4c5989d01b4502db6255` | 0 |
| Q1关联-ident | `94718d9f17394ca0adfdcaab5834bef5` | 0 |
| Q1关联-row | `6795cc23c706473ba61daf2830a1670c` | 0 |
| Q1关联-audit | `3da1a808c24741cdab667343a55e3eb6` | 0 |
| Q1关联-data | `f3b7944ad1a343308ce3d436df749b38` | 0 |
| Q1排空-before | `819c297cc68b4ed6bcfc8525edd88a52` | 0 |
| Q1排空-after | `cd7ec043dea74061beeb752f7f9b23df` | 0 |
| 独立干净候选政策 | `79e8227a350c4e1991188932ca7ed222` | 0 |
| normal-engineering-plan-a0d4d94 | `a0d4d94fa6754375af3ce22d6912dc93` | 0 |
| normal-engineering-verify-ebcb9da | `ebcb9da775134b168e105941587dbf8c` | 2 |
| normal-stable-oracle-task-admission-bb99da5 | `bb99da5ed17a4a328e9fbd14a95aac21` | 0 |

## 独立复核

工程复核逐字重开 37 组三联命令收据，产品复核逐格核对 34 条事件和 17 份索引原件，维护复核重开 357 条登记路径。Q1 的 API 宿主与模块、PG 失败行、两个时钟区间、f159 两列新连接回读均相符。当前完整稳定候选门禁 `ebcb9da775134b168e105941587dbf8c` 真实退出 2。环境、合同、后端分别复用 21、27、10 项执行并重新核准。查询准入 16 项、Doris 11 项、工程 29 项均重新执行。独立 Oracle 入口实际发现 156 个不同用例并全数执行，干净候选政策检查退出 0。

本批实际执行的跨边界用例如下。

- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_ordinary_rejection_requires_fresh_same_connection_after_release`
- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_reopen_two_branches_emitted_by_agent_test_process`
- `OracleRuntimeSourceEventsTests.ExportTwoCompleteSourceBranchesForOfflineReopen`
- `WorkflowOracleS2.S2ReadinessTests.test_expired_catalog_and_current_reader_seed_are_independently_bound`
- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_reopen_normal_http_failure_and_overflow`

## c44c6294 历史交付原文

下列原文记录维护前截面。原文中的“行内执行 776.090 毫秒”应读作两个 UTC 字段之差。历史 f159 的 owner 已由本批准确维护清空。

# Oracle S2/S3 限定交接

**S2 PARTIAL，S3 NOT_RUN。** d368 的准确晚 CAS 已完成。一次诊断与一次修正后的正式十槽均已执行。正式父通过四角色认证，随后在 ABA 槽的首个关系查询收到 `503 query_source_cleanup_unconfirmed`。该查询的两列租约仍在。两个父命令均未派发在途 ABA 的 25 秒 DI 子进程。交付停在 ChatGPT 复审。

| 本轮实际操作 | 命令 | 结果 |
|---|---|---|
| d368 准确维护 | `8c6dac18ce3940398c85dba1660cdcdc` | exit 0。新连接已核两列清空、原失败审计保留、恰有一条维护审计 |
| 诊断父 | `a576965c8f4d47999676d82ecfde9106` | exit 1，24.169 秒。认证 6.217 秒，ABA 槽 13.453 秒，历史结果 GET 返回 410 |
| 修正后的正式父 | `4032c1d770b240989966ba3275d86999` | exit 1，31.101／2340 秒。认证 6.729／600 秒，ABA 槽 22.005／180 秒。十槽 1 PASS、1 FAIL、8 NOT_RUN |

## 准确晚恢复

非作者重开 d368 的请求与绑定、宿主和网络、专用 Oracle 实例、原父与实际 docker-exec 子进程、两台 API 及生产者关闭原件，再核 9b81 → 9386 → 05ea 的原生关闭与后态。维护只启任务 PG，冻结行位于 `mapping`、系统标识 `7709907053089669168`。事务校验身份、owner 散列、FAILED/fence 2、稳定行与唯一失败审计后，清空两列租约并写入维护审计。独立复核覆盖 493 件原件。

查询 `query-d368ac610c7745889890e1589653af8f` 的 request、binding 和其余行字节稳定。原失败审计 `83330a307d7a4583aa44e7c2a6db4fa4` 保留，新维护审计为 `514479db82f74b4a921a4b2ca2674bb6`。新连接的行、审计及读收据三个命令分别为 `393e621987fd4b5cbdc4baea4030f82c`、`43a3dcf0771b488a9c2d835ff4dfcdeb`、`2abc9b489e224d49b06e7fba2e5ce477`。成功审计、结果和读收据均为零。历史两条 clientId 与 Q 的逐源归属仍为 NOT_PROVEN，cleanup250ms、AC03-B、Oracle S0 保留原资格。

## 两次产品执行

诊断中，当前连接五阶段探测通过。随后 reader 读取历史 `query-d293780099754592b3e2a00957e13c8b`，10.684 毫秒后返回 `410 result_expired`。实际驱动要求 200，因而停止。修正保留历史 queryId、5056 字节的原散列和真实 410。在准确过期分支中，驱动使用该槽原有的新关系查询，要求同一父、reader、会话和 Q 从正式 GET 取回相同字节并核零源读。该新分支的后半段取得离线正反例覆盖。

正式执行复现历史 410 并进入原有 seed POST。HTTP 用时 1671.913 毫秒，距五秒上限 3328.087 毫秒，响应 503、错误码 `query_source_cleanup_unconfirmed`。此次 HTTP 没有返回 queryId。关闭 PG 前，按准确连接和请求起止查询，唯一命中 `query-f1599097a7274c20b82cbf0dfcea4e2b`。

| 正式失败 Q 的现场事实 | 实测 |
|---|---|
| 未过滤 Oracle 审计 | seed 窗预期 2 次业务 SELECT，实际 0 次；正式父全窗也是 0 次 |
| PG 时间（UTC） | 创建 12:50:37.198569，完成 12:50:37.974659，截止 12:50:41.308879。行内执行 776.090 毫秒，完成时余 3334.220 毫秒 |
| 状态与占位 | FAILED，fence 2，owner 散列 `08d6b6d8633b72b6ad4a980128d3e6a1b68c83b5c388cecd3a3296d84accf4cb`，租约截止等于原 Q 截止。LEASE_HELD_NOT_QUALIFIED |
| 副作用 | 唯一失败审计 `38ebcc6e08504994b36a322edc4ffd86`；成功审计 0，resultHash 为 null，结果大小、密文长度和读收据均为 0 |

正式失败行保留现场。源分支一秒和清理 250 毫秒各自的实测时长与差额均未知。seed GET、实体选择、B4/A5、同 Q 在原期限内拒绝、普通最终 403/409 的占位释放与下一同连接新查询准入均未取得本轮实机资格。当前完整 A 仍为 `activation-d2dcec9ef54c4f3bb96d60cab449580b`、revision 3。历史父 `c02e89f8d8f2481f90058606ccf71b29` 和子 `5b90bb8f66fb4ddd9bfeddbe5015133a` 的失败原件保留；旧超时最后有证调用为 ReadJobAsync，剩 296.4737 毫秒。

## 工程、授权与收口

四处原入口修正覆盖完整激活回执与下一槽消费、真实子进程的有界允许字段收集和 logger、当前 run 的工程适配器、准确三笔或登记五笔激活链。普通最终 403/409 的已审实现保留。后端变更后按同一输入键重建 API、Agent、Query，实际宿主重开各 99／222／222 件快照。首次产品开窗因查错构建原件目录在诊断派发前关闭，诊断与正式计数均为零。实测候选通过 55 项 Python 和 9 项 JS 定向检查，历史五槽 684 件与 access 78 项按输入重开。

诊断时 PG 确认原 15 项 grant 自然到期，按原范围签发 6＋9 项。检查点由 90 行／epoch 121 推进到 105 行／epoch 136。正式窗复用同一组，剩余 13713.168 秒，新增 0 项。工程 verify 退出 2。environment 21、contract 27、backend 10、query-task-admission 16 全部通过。旧 Doris 门执行 11 项，1 项因 RF_PRODUCT_REVISION 失败；后续门、CI 未运行。两份旧 Doris assessment 仍未资格。

PG-only 维护后继为 `134da209…`，派发前关闭后继为 `344cb4dd…`，诊断关闭后继为 `d5598f01…`。最终正式操作 `c35242b898c04ae3ad5529ba346d320f` 的收口记录单独绑定实测末次关闭。两台 API 均已移除，五个任务持久角色均已退出，前后排空各七项均为零。Fuseki 的 cleanShutdown 为 UNKNOWN。原卷、九归档、旧 17 个停止实例与原 3 个运行实例受保护，四个 Finder 文件散列已核。正式窗 6 个样本的最高计费量为 43,155,800,510 字节（40.19 GiB）。非作者重开末窗 1,343 件原件，末次关闭摘要为 `a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348`。各窗合计 1,453 组不重复的路径、字节散列及长度见机器回执。

Base 为 `11f438423179d1cc64d043eb2483793b7e03f962`，正式及最终工程实测代码为 `9e84841423bac82911fc989b7b0a4ec999ac1ac7`。main 固定为 `5168f2c93ca226caa521a6dc4ac85439335274c4`。普通推送后的完整分支 Head 与三文件逐字节回读登记在同批本机包外回执 `delivery-readback-11f438.json`。本批无中间 PARTIAL ZIP。[机器回执](final-machine-receipt.json) · [非作者复核](non-author-review.json)
