# 精确资源收尾

Docker已真实删除6容器、2任务内部网络、4任务tmpfs具名卷、4新增固定ARM64镜像。精确plan/receipt包含实际命令/exit/before/after，非作者逐ID复验缺席。保留13唯一既有镜像、8旧卷及3当前默认网络。原Before默认bridge已在13:39:15换ID，原因UNKNOWN；不修改原Before、不将其说成当前清理造成或原ID全保留。

Master准确11文件系统对象删除955220704逻辑字节：4冗余OCI tar、api-final重复发布、2旧Web构建及4本树借用链接。canonical镜像目录保留，供本关口取证审查。不是物理APFS/containerd去重回收量。共享donor device/inode复验未变，Worker链接未清理。

两个临时PID35950/36010经准确命令/cwd核验后SIGTERM并最终exec0，15100/15180无监听。最初5秒等待monitor断言失败保留；它在下一心跳结束，无全局电源设置或重启。最终静态检查因pythonlibs链接已清理失败；只临时恢复同一已批准链接完成4188文件检查，随后再次精确unlink并验证donor身份。该额外一创建/一删除见verification-tool-cycle，不覆盖第一次清理事实。

## KEEP与解除条件

- 本任务Master/Worker工作树及任务分支：当前未合main、仍待独立复审，保留源码与检查证据；仅本关口获准关闭并核实所有提交安全后评估回收。
- `.tools/security/g4-m1-recovery-001-20261101-01`：仅本任务合成私有输入、TLS/PFX/KEK及realm资料，0700/0600；绝不入Git/ZIP。用于最终ZIP已知秘密扫描及受控复现，待本关口复审关闭后按准确清单销毁。没有活跃服务继续使用。
- `artifacts/g4-m1-recovery-001/forensics/{0,1,2,3}`及SBOM/许可原件：canonical取证和精确镜像输入审查，待本关口确认已归档后回收；4冗余tar已经删除。
- 当前 `artifacts/g4-m1-recovery-001/api`、`apps/web/.next`、测试产物及原始日志：本Head待审的可重建产物和原始执行证据，当前无容器/宿主服务运行；Review关闭后保留唯一提交可恢复入口再白名单回收。
- `/private/tmp/g4-m1-recovery-001-bguhng3e`：唯一授权附件安全展开与原始校验输入；原字节已提交归档，复审后回收。Downloads原ZIP为用户材料，不在清单。
- 所有其他任务树/G3/G6/持久卷/全局工具和donor均不在本任务删除边界。

恢复入口是已提交任务卡、runtime/compose消费者及原固定digest；先重新Preflight和审查资源预算，不自动重拉、启动服务或进入M2。
