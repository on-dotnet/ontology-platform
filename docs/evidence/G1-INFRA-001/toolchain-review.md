# 隔离工具链与共享配置审查

2026-10-23，独立只读infra_rules_review检查doctor、global.json、CPM和锁策略。除一项doctor缺陷外未发现阻断，diff-check通过；正常工具链诊断实际退出0。Reviewer未重复下载哈希或运行restore/build，依赖兼容待真实恢复验证。

发现：项目pnpm.cjs存在但Node缺失时仍调用空命令，错误退出1，应环境BLOCKED退出2。Master新增scripts/tests/Doctor.Tests.ps1，以进程内模拟缺失命令复现实际退出1（RED），增加Node缺失跳过分支后退出2（GREEN）。不安装或启动资源，不改全局配置。

原8项工程检查继续通过。独立Review不代表包兼容性、安全或基础设施整体通过。
