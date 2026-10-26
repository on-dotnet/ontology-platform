# 执行台账

- OBSERVED：开工HEAD/origin/main均为46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，fetch exit0；G2 CI40283523824工程与治理集成success（真实API读取）。
- OBSERVED：主checkout六个DS_Store未跟踪，原样保护；新native托管树用于唯一任务分支。
- OBSERVED：首次worktree list23项，native创建后变17项（包含新树）。七个G1树记录消失的来源未核实；本轮未发出旧树删除/归档指令，不计入回收量。不读全局codex归档。
- Ruling：附件已由用户明确批准全部执行，采用附件四关口原生执行，不重复设计审批；并行只读调查和独立审查，Master唯一写入。
- OBSERVED：沙箱拒绝公共.git refs和托管树写入，授权动作经require_escalated自动审查继续；未改变沙箱/机器全局配置。
- Ruling：Docker首次沙箱permission-denied不等于Engine离线，经批准只读访问后可达；卷数据唯一性未证明则保留。

- OBSERVED：H2首次SelfTest exit1，新增归档G2 git/commits.txt保留历史提交消息尾空格而触发text-format；未放宽校验，四个归档提交日志均先以明确Base..Head git log逐字节重建核对后移除本轮重复副本，原SHA和恢复命令保留，历史Git未改。
- OBSERVED：独立Reviewer复现attributes隐藏文本Important和status刷新index Minor；补精确RED（均1/1失败），现以原始blob文本集合强制--text及--no-optional-locks修复，完整GREEN与复核后才能宣称关闭。

- H1 commit/push：284f8c6020e4cd7190fd1c13ca16457abac677da；独立工具审查修复后54/54及完整SelfTest exit0，真实日志归档。本轮不需要修改CI/verify公共入口，已有SelfTest自动运行所有构包回归。
