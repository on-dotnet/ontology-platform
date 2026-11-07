# 非作者 P0 Review

Reviewer：只读子代理 `/root/p0_review`；基线b3b68500d76ab5965fcc540afb883ca605cb15dd。未写文件、未运行产品测试。以下为Master保存的审查结论，审查对象为基线合同，非产品代码批准。

结论：**P0 BLOCKED**。公共分发与Web闭环均未验证。

- P1：G4ConnectionRules.cs:32只允许POSTGRESQL_READONLY，Application/ConnectionApplicationService.Commands.cs:16再次限制。API_KEY_REF没有合法Web用途；借用PG用途会改变隔离语义。新增用途需批准公开验证行为。
- NONE：G4ConnectionRules.cs:19–20允许创建null SecretRef，Models.cs:250/Rules.cs:38仍强制草稿Probe引用。G4Endpoints.cs:21保存后test不需要引用，因此不用改变draft wire也可走Create→Test；不能据此声称必须改DTO。
- Persistence/ConnectionRecord.cs:28–31与初始迁移:122–123使用非空SecretId、默认SecretVersion=1，无SecretId外键。技术上未必需要迁移，但无凭据表示/版本/轮换拒绝/认证转换必须明确裁决；禁止伪PG secret或未经批准sentinel。ConnectionApplicationService.cs:244固定SecretConfigured=true，应用多个阶段读取真实secret行。
- host_continuity.py:222,224没有本TaskId；execution_preflight.py:248,260–266的普通M2属于G3，不能冒用。可在允许的workflow*适配内复用只读函数及准确消费者核验；修改旧两个CLI超附件白名单。
- 可继续的无关工作包括资源工具核验、环境来源修复设计、内部dispatcher设计及PG回归规划；当前仅PG执行是正常实现缺失，不是自身授权阻断。

独立Review没有认可P0通过，没有认可Web实现。后续源码与HTTP安全仍需新独立审查。
