# 保留的失败与未验证事实

- P0 Git fetch/Docker socket初次受沙箱限制；按准确范围升级只读检查后成功，不写daemon offline。
- 独立托管Worktree创建第一次参数不匹配，改用真实工具参数；未回退共用main。
- 输入验证缺jsonschema；复用已有项目隔离venv，未安装新依赖。
- 初次误用仓库根solution路径，实际入口backend/OntologyPlatform.slnx；已纠正。
- MTP错误filter-class造成两次零测试exit5，不能当PASS；正确filter首次发现数字字符串可接受，修严格NumberHandling后真实15项通过。
- API路由被推断成RequestDelegate导致16项编译错误，改为显式Func<HttpContext,Task<IResult>>；最终真实构建通过。
- UI Worker尝试同步共享生成文件触发自动审批拒绝。安全替代：Worker撤销共享同步，Master在自身公共路径集成生成类型并执行真实typecheck；拒绝未被绕过。
- UI审查真实发现错误码映射、恢复参数、跨org同site选择及三轮缓存泄露反例；最终99b6158修复，原审查事实见independent-component-review.md。
- 状态机独立源码Review发现4项竞态/审计/ETag问题和旧Probe投影遗漏，Master修复；真实并发/数据库验收仍NOT_RUN。
- E0误传完整TaskId而不是已登记阶段G4-M1，CLI拒绝；正确runtime阶段仍因未实现消费者REFUSED exit2。未放宽前置规则。
- EF10.0.13 migration remove不支持--offline，命令exit1，原日志migration-revise.txt保留。准确3个本任务新生成、未提交/未应用迁移文件被删除后重新生成，最终日志migration-generation-final.txt；未调用force或修改数据库。
- dotnet format exit0但报告加载工作区警告，日志保留；不把它当全部注释语义审查。
- 初次资源after命令漏--digests导致镜像文本比较false；同参数重查与逐个原ID inspect通过，原失败观察和补充回执并存。
- 沙箱内ps查询被拒绝；准确PID检查以已授权的受限升级命令完成，确认本任务monitor已退出。
- 镜像SPDX便利查询两次45秒TimeoutExpired不是CLI exit124。准确attestation短查询可用，但完整镜像许可仍未闭合，保持pull BLOCKED。

所有组件测试成功不能抵消镜像门禁、49项产品NOT_RUN、未运行CI或跨平台缺口。当前提交仅供PARTIAL审查及恢复。
