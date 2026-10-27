# AppHost 前缀修复限定复审

Reviewer m1_contract_review（非作者，Astra/high），范围 5df0765..6a1c76cd41e2b926f82ccd4ddd9b750dce5b7c44。Spec PASS / Quality PASS，C0/I0/M0。

Wave2Infrastructure.cs 只增加 g3-m1 前缀，严格全文锚点拒绝末尾 LF；M2、大小写、路径与超长前缀仍拒绝。实际 Release DLL 的三个允许前缀在后续缺 NodePath 处退出，五个非法前缀在前缀 guard 退出，均不能到达 Program 的 Build/Run。Reviewer 核对 RED2→GREEN2 及原始/归档日志 SHA，与 prefix-log-provenance.json 相符。统一入口在 Release build 后调用该边界测试，失败立即停止。

本次未修改 Contracts、reader 项目或其构建输入；v4 reader 继续保留 5df0765 的126个冻结成员。此限定审查不认证第三轮完整入口最终结果、整分支、最终 CI 或 ZIP；Reviewer 未修改文件、启动容器或重跑测试。
