# Oracle 同键零下载 prepare 续行交付

**完整 prepare 为 BLOCKED，S2 为 PARTIAL，S3 为 NOT_RUN，G4 为 PARTIAL。** 本轮解决了上轮已知的缓存物化和磁盘余量问题。正式入口在核验 pnpm 11.28.8 的批准原包时退出 2。产品登录及十槽均未启动。[机器回执](final-machine-receipt.json) · [非作者复核](non-author-review.json)

沿用 `codex/g4-oracle-mapping-query-001`、原托管工作树、`product-resume-01 / s2-s3-01` 和资源批次 `implementation-01`。起点为 ChatGPT 已接受的 `cd130d337480997a105fe1497dde9e0cdb464fca`，本轮工程输入为 `95434cdda4c2728bec42924e18710858bb52218c`。main 固定在 `5168f2c93ca226caa521a6dc4ac85439335274c4`。上轮三项入口修复、原件和六个复审问题均可从已接受提交重开。[已接受的三份文件](https://github.com/on-dotnet/ontology-platform/tree/cd130d337480997a105fe1497dde9e0cdb464fca/docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01)

## 正式入口与磁盘实测

| 项目 | 当期证据 |
|---|---|
| 内容键与完整校验 | 内容键仍为 `d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43`。原树的 locked restore 回执、21 份项目资产与 7 份既有回收台账按固定 SHA-256 重开。已回收的 250 个整包路径包括 80 个 feed 副本、168 个私有 NuGet 副本和 2 个 SDK 副本。每个源归档、锁、sidecar、元数据、实际展开成员和额外文件检查仍有效。缺少原 restore 回执时，该树在物化前停止。 |
| 准备空间 | 同一私有 NuGet 缓存的 109 份公开包 XML 透明压缩后，从 170,401,792 B 减至 23,379,968 B，实际释放 147,021,824 B。逐件复核原路径、SHA-256、逻辑长度、权限、修改时间、独立 inode 和压缩标志。迁移起始两个同包同字节副本短时共用 inode，第一次原入口实测余量 38,358,594 B 后串行压缩；结束时每项均为单链接。 |
| 七角色准入 | 压缩后原入口测得余量 138,686,018 B。后续检查及 SDK 解析完成后，收尾准入 `b39879c982cf44219eb6273e6877889f` 计入 42,812,027,326 B，40 GiB 内余额为 **137,645,634 B**。七角色含 helper 的预估为 13.75 GiB、10.5 CPU，当前任务运行角色为空，临时探针已移除。保护清单摘要与上轮一致。 |
| 阶段峰值 | 新构建键 `df12e77a94af917c4d11ecaea1c0786b17904661139a2bae80223d6a66835e74` 尚无同键快照。以现存 API、Query、Agent 输出模拟原冻结器的所有前序同路径同摘要共享，分别有 99/222/222 个成员，可共享 0/77/216 项。三个阶段的冻结预算为 32,124,683、15,010,385、2,861,649 B，逐阶段预留相加为 49,996,717 B。该估算可容纳于收尾余额；正式新构建、发布投影、服务增长及实机阶段峰值仍待核验。 |

准入原件、两次中间测量、逐文件前后账、完整复核脚本和各命令双流均由机器回执定位。已回收路径仍缺席，本轮磁盘依据使用原入口的现测值；17 个停止保留实例、3 个持卷服务及旧卷、密钥和封存档继续保护。

## 资格与阻断

| 状态 | 当前范围 |
|---|---|
| FRESH | 当前提交的定向回归 10/10，仓库静态检查、runtime 结构检查及提交区间 diff-check 退出 0。21 项目与 179 个批准包通过实际校验，两个 SDK 在原禁网沙箱通过 MSBuild preprocess，均解析到本树私有 SDK。 |
| FRESH | 当前本机索引实测 391 包、26,176 个文件，原历史清单按固定摘要重开。两代的 391 个索引编码摘要各异；逐行的锁键、文件顺序、每个文件 SHA-512 与 bin 声明一致。109 个 shim、1,283 条链接与元数据重算得到原 Web 绑定 `1c5fb6199beb880c263f8a466068c507034627e5bd0bdd1526e832fc5678f842`。原四个特定索引身份及完整来源字段均有独立基线。 |
| BLOCKED | 首次正式 prepare `581a62f0d2034c9e9e193aab2dea235a` 因登记的 pnpm 路径缺失退出 2。增加同摘要任务缓存入口后，工程 Head 上的正式命令 `c29c7ae992bd4957b7aad46a33b318b0` 仍以 `WARM_PNPM_APPROVED_TARBALL_MISSING` 退出 2。两份已展开工具树的 454 文件、22,861,430 B 逐字相符；本地重打包未命中冻结 SRI。全程零下载。 |
| REUSED | access 78 项、前五槽、AC03-A/C、S1、EC01 和已合格旧源按原输入复用。旧父命令 `1afa8fd9ad624134a814126527f7a916` 退出 1，ABA 子命令 `36606f5b1aa74ac09863d99930578f85` 退出 2。双表 runtime 的 2＋2＋2＋2 和 seed 的两次预备读取继续使用上轮冻结预期。 |
| NOT_RUN | 完整准备后的二次幂等运行、新绑定构建、十槽、实机峰值、完整工程 verify 与 CI。原树四份既存 Finder 文件保留，当前工程 plan 以 `PLAN_DIRTY` 退出 2。新宿主的 Fuseki 发布图、服务停启链及六条组合授权的当前 TTL 须在正式产品入口重新核验。 |
| 持续缺项 | 两份 Doris assessment 的独立存储原件和取消清理 250 ms 保持 NOT_QUALIFIED；AC03-B 与 Oracle S0 继续 BLOCKED。 |

## 唯一需要补齐的输入

需要提供已有的 **pnpm-11.28.8.tgz 原包**，可放置到原工作树的 `artifacts/workflow/G4-ORACLE-MAPPING-QUERY-001/artifact-cache/pnpm-11.28.8.tgz`。接受的 SHA-512 SRI 为 `sha512-9piKMgRrmj9419fuB0eSa76QX/nf9zvxmruHvX0ZBqKskNk/c74ytfnhTCiZVpvLDJxeyKGeCD9dcburbdnguA==`。现有零下载入口会重新验证该 SRI 和包内的准确成员。随后仍须正式 prepare、当前构建和峰值获证，方可执行已冻结十槽。

本次交付停在 ChatGPT 复审。三份文件的 Git 字节、远端任务分支与 main 的普通推送后回读位于原批次 `same-key-prepare-remote-readback.json`。本轮未生成中间 PARTIAL ZIP。
