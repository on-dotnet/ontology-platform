# Oracle S0 冻结检查点恢复交接

任务 `G4-ORACLE-MAPPING-QUERY-001`，批次 `s0-recovery-02`，Base `454d1a2f17581673cbbf44900a5fe241d603f5ef`。RC05 恢复资格 **BLOCKED**，资源收尾 **VERIFIED**。Oracle S0/AC03 **BLOCKED**，cleanup250ms **NOT_QUALIFIED**，G4 **PARTIAL**。本批停止在 ChatGPT 复审，S1–S3 未准入。

| 项目 | 资格 | 实测原件与结果 |
|---|---|---|
| OIDC | WAITING_FOR_USER_AUTH | [认证宿主和回调](originals/auth-ended-fb78d7ca0af84dbcacd946c819997ba1.json) 已实测专用 BFF 就绪、冻结 RS256 公钥绑定、只读 keyring/PFX 及禁自动生成键。code/S256 已核配置，签名算法与失败策略有离线正反例；实际新令牌验签 NOT_RUN。正式挑战 0 次，同票回调后成功读取 /me 共 0 次。 |
| RustFS | RUSTFS_FROZEN_VERSIONS_VERIFIED | [实际替代实例](originals/objects-actual-7062c51be2c745368c49afbeda6c6192.json)与[冷备参考实例](originals/objects-reference-6174f35d67d644e6a4f503d55afd4ef8.json)分别读取 3 页。桶版本设置为 UNSET，5 个内容版本的 VersionId 均为字面值 null；逐版本散列及五项 PG 发布引用相符，删除标记 0。 |
| Fuseki | REUSED | 同一封存归档和替代实例先后两次全读，默认图 0、命名图 1,372，两个发布图分别为 46、1,326。原关闭钩子 UNKNOWN。[上批二次读取](../s0-recovery-01/originals/graphs-second-open.json) |
| 结构解析 | FRESH | [旧解析失败](originals/parser-before.json)绑定 Base 的准确 Compose。局部 SafeLoader 识别该文档的 !override，定向验证含错误 YAML、未知标签、对象构造、非 Compose 中的标签及普通 YAML/TOML。 |
| 平台 PG、Oracle、keyring | REUSED | [冻结检查点](../s0-recovery-01/originals/checkpoint-ca3d35a7e5f94e539cd24ec39b8f7c0b.json)绑定 48 张 PG 表、Oracle TCPS 11 列及两表各 1 行、受保护结果；[真实聚合](originals/aggregate-result.json)重新核对。 |
| 资源 | VERIFIED | [停止后态](originals/closeout-state.json)与[九份归档](originals/preserved-archives.json)记录准确 ID、SHA、文件身份及权限。运行全集为原三个持卷服务，旧 17 个保持退出。 |

## 认证窗口和允许变化

原四账号为 g2-operator-ab、g2-auditor-ab、g2-operator-a、g2-viewer-a。宿主审核实际 endpoints、后台服务、业务路由拒绝、匿名 /me 返回 401、G2/G4/QueryEnabled/Mapping 和迁移/seed 开关。窗口与当次宿主绑定，关停后该入口已关闭。[人工交接](originals/manual-handoff.json) [窗口后态](originals/auth-window-outcome.json)

登录新增会话 0 行，审计新增 0 行。替代 PG 前后对账为 `AUTHENTICATION_WRITES_ACCOUNTED`，epoch 16 → 16。本批登记的票据及审计增量以认证原件 pgWrites 为准。原查询 CANCELLED、fence 2、成功副作用 0、原取消和维护审计各 1。采集范围为四个合成账号的当前平台投影及新令牌；IdP 全体用户、全部 client 和非平台角色未审。历史直接提取口令审批的原文未提供，登记 DENIAL_ORIGINAL_NOT_AVAILABLE。

四个账号的正常认证链尚未集齐。后续恢复此项需要重新核对资源、专用宿主和当前替代 PG 基线，并安排四个原账号在隔离浏览器中完成登录。

## 重开与工程验证

[原件索引](index.json)登记每个公开原始流的路径、长度、SHA-256 及还原方式。两个维护驱动的源码、编译器、参考程序集、实际命令及双流绑定在同批。组件实测时工作树处于集成过程，真实读取绑定各自构建的源码、DLL 及命令输入；准确代码提交复核这些原件，未将早期现场执行改记为交付 Head 的新运行。完整编译资格还需原实测树中的两个已保留 DLL。独立参考由锁定镜像、只读封存归档和新登记卷建立，56 个成员共 87,689 B，以 GNU tar 提取并全量比较。[参考创建原件](originals/reference-created.json)

工程实测输入 `aba08e047f3a4673a6fc255d90db8d5736e1036c`。Oracle 工程入口完成 17 项测试，解析入口完成 10 项正反例。完整影响验证为 **BLOCKED**（context-selection=PASS、engineering=PASS、engineering-full=FAIL）。完整 SelfTest 会复制约 717 MB 的 Git 文件；在本批 64 MiB 增量上限下，已向该准确进程组发送 TERM（工程子项 exit −15）。全仓静态检查由原验证脚本执行，最终回执记录其退出码。首次外层等待 230 秒超时，第二次因互斥标记拒绝；两个属于本批退出进程的空标记已按 inode 保全，失败账本散列相同。[互斥记录](originals/directed-lock-recovery.json) [实际工程结果](originals/engineering-selected.json) [本批验证](originals/validation.json)列实际运行的作用域；包外机器回执列最终 Head 的复核和实际退出码。14 项已接受后端用例及 344 条历史格式诊断按相同产品源码/策略核资格，本批无原生后端、浏览器产品链、Oracle 正式取消、重复维护 CAS 或 CI 执行。产品合同门禁单独回读，缺少 S0 正式取消证据。已有正式取消预算 250 ms／1 s／5 s 继续有效。

阶段准入实测最大合计内存 6,979,321,856 B、CPU 6.5。样本中最高增量 52,277,248 B，64 MiB 上限；最高阶段计费 42,629,488,721 B，40 GiB 上限。替代 PG、Keycloak 和 RustFS 已退出，临时宿主、参考容器及参考卷的准确消失状态均已回读。原件保留参考卷首次挂载与冷比较失败、一次认证宿主启动失败，以及替代 IdP 已退出后的端口检查失败。本批保留原件、原卷与历史 ZIP。

AC03 后续裁决仍需产品合理的正式在途窗口、取消提交先于同次源端结束、可独立归因的源终态及零成功副作用。此恢复交付没有 Oracle 产品 V3 或同包 VerifyOnly。
