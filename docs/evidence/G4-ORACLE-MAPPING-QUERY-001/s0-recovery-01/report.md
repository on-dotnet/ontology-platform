# Oracle S0 阻断恢复交接

`G4-ORACLE-MAPPING-QUERY-001 / s0-recovery-01`，2026-11-20。**recovery/closeout = BLOCKED，Oracle S0 = BLOCKED，G4 = PARTIAL。** 准确取消行已完成一次维护恢复，新栈已停止保留。RC05 缺少完整跨存储证明。正式取消仍缺少源执行因提交后的取消而终止的正例，S1–S3 继续关闭。

分支为 `codex/g4-oracle-mapping-query-001`，Base 为 `9de3b93a0dfddb948b4d68c61ad1b54ce84e0812`。业务、维护、恢复验证使用不同的执行身份。最终交付提交、普通 push 与远端回读绑定在包外机器回执；同目录的非作者回执绑定相同 Git 对象。公开原件按原始长度和 SHA-256 重开。[无损原件索引](index.json)

| 门禁 | 结论 | 可重开的事实 |
|---|---|---|
| RC01 源入口封闭 | PASS | 容量锁持有至真实打开源连接，TLS 前及 ODP 打开前均核验。隔离 PG 的计数替身验证未知占位期间新建、重放、状态/结果/证据、同连接历史读取的打开数为零，错误主体、锁后竞态、四槽及旧 fence 晚提交均有反例。释放后恢复原权限读取。跨实例用两个 Store，未声称 OS 进程重启。[真实 PG 回执](originals/real-pg-5a42dafebb99.json) |
| RC02 较早 Run 截止 | PASS | 在 ReserveRun 前收紧共享单调截止。源调用与清理、失败确认、绑定和 MCP 编码前后共享该截止。已过期与充足窗口均有对照。定向 Agent 8 项、相邻 wire 2 项。[Agent 双流](command-originals/58166a6623b342ba813bf55b46ed14da/receipt.json) · [wire 双流](command-originals/d8dd447d6f3445ddb42504f34828d183/receipt.json) |
| RC03 单行维护 | PASS | 窄观察者、业务投递封闭、独立源终止证据、准确旧行与审计、新连接后验均成立。真实业务行仅执行一次 CAS。隔离 PG 已验证错误 tuple、过期产品确认拒绝、旧 fence、审计失败整笔回滚和重复恢复。[新鲜终止证明](originals/termination-4239ea404d924bbcae5e4ec41ad4cc27.json) · [单次事务及后验](originals/maintenance-4239ea404d924bbcae5e4ec41ad4cc27.json) |
| RC04 阶段计量 | PASS | 生产预算器分别计算已占用和未发生量。五个定向用例验证预留转落盘、增长、超额、测量缺失和归属错误。原、替代、关闭三个阶段核对精确 ID、卷、网络、运行全集、端口和配额。[预算门禁](originals/recovery-budget-tests-7da190898a5349049c924b1046824199.json) · [替代清单](originals/replacement-resources.json) |
| RC05 当前一致保全 | **BLOCKED** | 已取当前冷备并在隔离替代卷逐文件比较，服务还原后完成下述五个分项观测。OIDC 当前角色与真实签名票据、RustFS 完整版本链仍缺证。原 Fuseki 关闭钩子也未确认。[服务验证器](originals/checkpoint-ca3d35a7e5f94e539cd24ec39b8f7c0b.json) |
| RC06 停止与交接 | 停止后态已核 | 原五服务、替代五服务、四个业务 API 均已退出。旧 17 个停止实例和三个运行实例保持原 ID。备份可重新读取。准确交付 Head 的非作者结论和远端结果以包外回执为准。[最终资源逐 ID 回读](originals/closeout-state.json) |

## 准确历史行

维护目标为 `query-18b5ee00b53e4e4eafc43cc4717bd293`，连接 `a7913bb552eb4cd1a3f6eaf5b93cd619`，原 owner 为 `oracle-execution-004f5b3e04084f1998201939aaeec5e6`。原物理执行为 instance 1、PDB 3、SID 60、serial 51748、AUDSID 50045、SQL_ID `dum3m3c96vc07`、SQL_EXEC_ID 16777219。两代业务 API 均退出，七类平台工作为零，窄观察者新鲜读回没有匹配会话。前态及审计的完整字节留在私有目录。[前态公开摘要](originals/prestate-4239ea404d924bbcae5e4ec41ad4cc27.json)

尝试 `4239ea404d924bbcae5e4ec41ad4cc27`，操作 `3e494a56c9ef43298d44706850ccad31`。维护身份为 `os-uid-501`。原执行 fence 1 已进入取消终态 fence 2。事务清空两个租约字段，保留 CANCELLED、CancelRequested 和 fence 2，新增一条 `data.query.cleanup.recover`。新连接重算其余原行的 SHA-256 为 `3f49e5938439ddc765b6e5ad9d2a3ea0b37d1132d2d769870d9b8c179ed1066f`。原取消审计仍为一条，成功结果、回执和执行审计均为零。

## 冷备、替代与停止

| 对象 | 独立恢复观察 |
|---|---|
| PG | 替代 PG 的同一只读快照覆盖 48 张表、当前权限、目录、Mapping、激活、发布引用及维护审计。稳定投影与原 PG 为同一 SHA-256 `bc3a0c7014cb66a731f183aff6fae3a792f2cccb89badb23c33a5608b63e844a`。[恢复前](originals/pg-baseline-0e8c1a69fbe5401292061ac13dda2874.json) · [恢复后](originals/pg-restored-ca3d35a7e5f94e539cd24ec39b8f7c0b.json) |
| Oracle 与私有材料 | 准确替代卷经独立审查后复用，原卷、早期归档和诊断均保留。锁定 ODP 客户端完成 TCPS、身份、只读及目录核验，两表各一行、11 列与原基线一致。恢复的 keyring 使用正式消费者解开一条既有受保护结果并比较原散列。[早期替代卷独立审查](originals/early-alternative-independent-review.json) · [当前 Oracle 冷恢复](originals/restored-oracle.json) |
| Fuseki | 第一次替代打开及再次原生打开均可读全库。默认图零行、命名图 1,372 行，发布本体 46 条、数据 1,326 条，与 PG 已审 Turtle 在 Jena 中只读计算的预期逐条一致。SHACL 原字节与清单相符。原镜像关闭日志禁用，TERM 后退出 143、无 OOM、日志无关闭确认，两个锁文件保留；原实例关闭钩子为 UNKNOWN。[完整图对账](originals/graphs-restored.json) · [第二次打开](originals/graphs-second-open.json) |
| RustFS | 整卷含版本元数据私有保全，替代服务使用正式发布客户端按清单验证五个对象的长度和原字节，包括 SHACL；该消费者只覆盖发布引用。精确 VersionId 读取、完整版本与 delete-marker 清单仍为 NOT_VERIFIED。 |
| OIDC | 恢复了 H2 和签名配置，替代服务的 discovery、issuer 和两个公钥的 kid、材料散列与原件一致。四个原主体的当前 client/role 关系与实际 token 验签仍为 NOT_VERIFIED。[公开公钥回读](originals/oidc-public-restored.json) |

当前平台只建立一个四卷检查点，归档共 294,062,080 B。当前 Oracle 两份归档共 4,676,075,520 B，宿主私有材料归档 105,472 B。最终重读包含上述七份及早期 Oracle 两份，共九份。历史早期平台恢复仍为 NOT_RUN。私有归档、凭证和原始用户行保留在原保护位置，公开账本只列引用及摘要。[冷备账本](originals/archive-ledger.json) · [私有材料摘要](originals/host-materials.json)

停止后核得旧三个运行容器，原库存 SHA-256 仍为 `2fda67495da82c7270e16f034efcb246a2fbd226f3dfb647076acea7f987e4c9`。资源后态回执计量为 42,629,384,638 / 42,949,672,960 B，该次余量为 320,288,322 B。实际 VM 为 20,964,958,208 B、12 CPU；替代五服务及一个验证器的配额峰值为 12.25 GiB、9.5 CPU。全部原件、失败观测及旧数据保留。[尝试清单](originals/attempt-inventory.json)

## 实测、资格和未运行项

- **FRESH**：三组后端实测提交为 `9b71721d84acf4bc4a445adca0454b0ddbbf991f`，真实测试为 8 + 2 + 4 项，构建 inputKey 为 `5f9e0c29ed37afcfdaac9d5e6e9c35f3bd9834fddecc46f29f8b069ca141ae28`。真实维护、替代读回和资源动作各有独立运行回执。[三组实测](originals/validation.json)
- **重新核资格**：工程候选 `b6372032ab6ce721bcee4b2097d2eb6e820decbf` 相对实测后端仅四个 C# 文件存在空白差异。锁定 Roslyn 对四棵完整语法树和 8,620 个标记的种类、原文和值逐一比较相同，涵盖 SQL 和结构化注释。14 项测试仍归属原运行。原生 formatter 修正了改动行的 406 个诊断，再验 exit 2 的 344 个诊断均定位在 Base 同字节行。[输入资格](originals/backend-qualified.json) · [格式逐行归属](originals/native-format-attribution.json)
- **REUSED**：原 window-pair 非零退出传播及 DI logger 按 Base 的既有离线原件核接线。原正式脚本为 `dfe38a6c4ca5ab217361136dc2a07e949e70a38a`，原 API 构建为 `3235fc2c3bd1a7a3df1139cede9841c0cd1ff4eb`，snapshot 为 `ac3370165c2817682f81e7809ca33c39c7fa9a4d63e543c1d0a5964850c9da3e`。原 CommitAsync 区间缺失，原清理仍为 NOT_QUALIFIED。[退出传播原件](originals/offline-wrapper-exit-check.json) · [原阻断报告](../implementation-01/s0-blocked/report.md)
- **NOT_RUN**：本批没有重试正式取消、S1–S3、历史全链或 CI。PG、Doris 与 Oracle M2 历史原件保留各自身份。唯一 A–F 和任务卡继续使用原入口。[任务卡](../../../tasks/G4-ORACLE-MAPPING-QUERY-001.md) · [唯一 A–F](../contract-admission-request.md)

## 集中裁决

1. RC05 若要放行，需在既有凭证保护内提供可验签的原主体票据与当前角色/client 关系的正式读取途径，并提供可按 VersionId 读取且覆盖 delete-marker 的受控 RustFS 只读消费者。自动审批已拒绝直接抽取 OIDC 登录口令来补证。Fuseki 若允许用替代卷两次原生全读替代原关闭钩子证明，应单独裁决，原关闭事实仍保留 UNKNOWN。
2. AC03 仍需有产品理由的新方案，量化证明固定 SQL 的源在途窗口能够覆盖正式取消提交区间及原预算。原 SQL 自然 EOF 早于提交前观测点至少 174.005 ms。现有证据支持停止在 ChatGPT 复审。

## 工程分发

首份干净检出计划指出四个恢复输入缺登记。把它们接入现有 Oracle 准入后，计划已识别全部输入。单独执行真实工程消费者得到 Oracle 准入 12/12、通用工作流 25/25。正式 verify 在合同资格入口以 `OMQ_ORIGINALS_NOT_RUN_s0` 拒绝，exit 2。全仓静态检查 exit 1；在现有解析器就位后，短复现定位到 `infra/oracle/compose.mapping-query.yaml` 两处已有 Compose `!override`，安全 YAML 解析器报 ConstructorError。该文件、解析器及 verify 脚本与 Base 字节相同。证据 schema2 检查通过。[工程分项](originals/engineering-directed.json) · [正式分发](originals/verified-code-receipt.json) · [静态短定位](originals/static-baseline-diagnosis.json) · [执行与构建绑定](originals/recovery-cli-binding.json)
