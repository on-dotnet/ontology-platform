# 精确格式补丁后阻断交接（2026-11-03）

状态：BLOCKED_WITH_WITNESS。现有任务分支继续保存，不可提交 main。

TaskId：G4-M1-MAIN-INTEGRATION-001。Authorization：APPROVED_EXACT_FORMAT_PATCH_ONLY，审批原文见 raw-text-evidence.json 中的 approval-original.md 精确UTF-8文本，SHA256 65802aee169747e3d2255e32a423c471aa1cba79fdf548ca20e0d25f3d3a9b60。

ApprovedMain：d1a61daffe844475b07705797e3ad325cc3f2945。SourceHead：e7e6e28e2b6e07c5e5ccddeb91e04610bce0d14b。CandidateSourceHead：99753df6f03b184e40b431a5b5aba89d8fa67087。

精确15文件补丁 SHA256：a99ccaa90787d110674d1b7d5a0a28a7d11ee4dfccd95347bb0ba686feeac668，33,442字节。隔离与真实应用均15/15 Before/After吻合，迁移仅删除BOM；非作者Reviewer在应用前后独立核实。独立源码提交及新部分 TestedCommit：80af5bb3a5c6cbe3906bb6aee8a78c2bc7536f7e。最终证据Head和远端读回见本轮包外final-receipt.json，不将该回执自引用进提交。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| whitespace verify | exit 0；原274 WHITESPACE和1 CHARSET解除 |
| 完整format verify | exit 2；两处IDE0161仍阻断，即使诊断为warning |
| 精确补丁针对构建 | exit 0；输入源码与新T相同，非完整I01 |
| 受影响四项目 | 240项，150通过、90环境/fixture跳过、0失败；各项原始输出保留 |
| 新T SelfTest | exit 1，初始secret-patterns失败；27套未启动 |
| I01 | BLOCKED；完整Web/原生/宿主验收未完成 |
| I02、I03、I04、I05、I06、I07 | NOT_RUN |
| I08 | PARTIAL_BLOCKED；未达到main审批条件 |
| CI、Windows、Intel | NOT_RUN |

SelfTest和V3有限扫描都把格式展开后的测试成员赋值识别为秘密模式。Reviewer确认该值来自类型成员引用，不是凭证字面量。现有扫描器保持原样，实际源码不编码、不省略、不绕过；新V3构包尝试及退出码单列包外。旧e7e6阻断ZIP保持原字节（SHA256 4e4255f9f98e5e8847b1f1b18152ecadeaf4c5395c76b89dc626d842819bc636），不把它称作新T交付包。

初始沙箱restore被主动中断却实际返回0，记INTERRUPTED_NOT_ACCEPTED；随后沙箱format准确停止exit -9。切换获准原生上下文后的离线restore、format、构建及针对测试原始记录分别保留。无下载、无新容器/卷/网络，无真实源PG访问。首次合成Npgsql检查因PowerShell缺本地logging程序集exit1，补充加载已存在的锁定程序集后exit0，首次失败不抹去。

## 最小下一步申请：精确三文件提案

NOT_AUTHORIZED_NOT_APPLIED。只申请应用 proposed-three-file-repair.payload.json 中的唯一补丁：31,032字节，SHA256 3443614b8dd4b7da720d5c08d781e18074d3cb06daac9cf612cc96fa60f62b20。原始可读patch保留在本任务 ignored artifacts/resume-20261103-01/proposed-three-file-repair.patch。必须逐项Before校验、隔离验证、非作者Review后才能真实应用；不申请修改共享扫描器/规则。

| 精确路径 | Before SHA256 | Proposed After SHA256 |
| --- | --- | --- |
| `backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/Migrations/20261030155129_G3M4ImpactReports.cs` | `acfc10eadbd100c5ca8b875a8a713bb30dada8dd3564d22b3d76b8f62f81bf5d` | `722b63e254412f9369ccce1c03fc11ca89929ec32c442b4d35a7445238379e7d` |
| `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Migrations/20261101115947_InitialConnections.cs` | `df2f6304359d23bcd442e6fb30f6283e17e86990ea0f83316948658f33f3935c` | `a5177f7dadafb946c1d45b289b0cf3279603901423d75e29b46e44b1202d574c` |
| `backend/tests/OntologyPlatform.ConnectionsTests/PgFixtureSecurityTests.cs` | `79421cd2173d6ed6a0bbddce42a7bba0467cbb369146103d5a76bb77f4cee78b` | `ebb76c8f430dff47bf9ef1167101e3a4fa5dd8fa6a73d2f98b68691868356b82` |

两处迁移仅从块命名空间转换为文件范围命名空间并对应缩进。Roslyn独立检查命名空间名称、using/extern/attribute作用域、成员语法子树、其余token和注释内容一致；Up/Down、SQL、迁移ID、快照不变。该转换明确超出此次BOM-only授权，尚未实施。

测试文件只将同一成员赋值从builder初始化器移至初始化器之后、创建未打开连接之前。值与次数、证书/TLS/超时/池/日志配置均不变。锁定Npgsql 10.0.3离线合成比较5组（普通、分号引号、Unicode、空、null）有效设置相同，全部连接Closed；4组连接字符串键排序变化、1组字节相同。此检查不表示真实PG/TLS运行成功，获批后仍需针对构建/测试及原计划稳定T完整验收。

当前审批第3.6节明确“不得顺手把迁移命名空间改为文件范围形式”，第4节要求越界修复另行申请，因此暂停这三文件实际写入。批准本提案不包括main更新/M2/G6，也不豁免原B适配器、消费者正反测试及I01–I08真实门禁。

## 资源与恢复

本轮46个自建可再生目录（3工具副本、42 bin/obj、1隔离补丁目录）已按新清单、新DryRun SHA和只读Review实际回收，9713普通文件、2,187,235,684逻辑字节，逐项ENOENT，4413跟踪文件散列不变；此数不代表APFS物理释放量。原共享NuGet/PyYAML源、旧工作树及持久材料未改。

准确宿主进程56427释放exit0；106心跳中76次观察锁屏，displayOff/sessionContinuity仍NOT_VERIFIED。无全局电源策略变更。保留当前分支/工作树、旧ZIP、全部证据和三文件提案；解除条件为后续明确集成及生命周期批准。

恢复从80af源码及最终证据Head读取：先复核远端/main/工具/镜像，再按此前原样流程从已验证本地缓存建立独立副本；不得安装/下载。当前适配器仍DRAFT，旧阻断交接所列缺失入口及历史身份问题仍未闭合。获批三文件修复后，先隔离应用和廉价复验，再按原授权完成适配/Review，冻结最终新T，运行完整本地验收。历史SelfTest/旧产品49项不可继承为当前PASS。
