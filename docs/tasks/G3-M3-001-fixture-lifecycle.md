# G3-M3 E0：组件验收容器归属补齐

状态：APPROVED_WITHIN_E0 / IMPLEMENTING。依据当前已批准E0资源创建即登记和自动资源回收要求。独立写入树复用g3-m3-web（前次WEB成果已全部集成，当前clean），不在Master树写入。

owned_paths：scripts/acceptance/semantic-roundtrip.py、release-faults.py、query-plan.py、mcp-agent.py、test-governance.py；允许新增scripts/acceptance/owned_test_containers.py、scripts/tests/OwnedTestContainers.Tests.py及docs/evidence/G3-M3-001/WEB/fixture-lifecycle-*。其它CI/verify/源码/锁/合同只读，Master单写接入测试。

只给本轮组件测试新建容器加准确project/TaskId/RunId标签和创建准确ID登记；沿用现有镜像/版本/流程/秘密只在env。finally只移除已成功创建且当下准确ID/标签仍匹配的本次容器；创建失败/名称碰撞/未知CLI/inspect错误不能按名字盲删。before-command-exit-after/准确不存在诊断记入脱敏已有证据，清理失败不得PASS。不得全局prune、扫描/删除别项目或改默认SDK/Docker。旧证据不重写。

TDD覆盖创建成功/失败、名字碰撞、foreign标签、CLI/inspect故障、exact no-such-container与权限失败区别、成功清理及继续其它独立安全项。真实产品验收由Master后续完整组件运行覆盖；mock不代表产品PASS。独立审查/提交后由Master集成，worker不改main，不回退他人代码。
