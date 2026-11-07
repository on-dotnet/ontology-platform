# P0 最小边界裁决（提案，尚未批准）

现有代码与附件目标存在认证合同缺口；不将其当普通补丁自行放行。

1. API_KEY_REF：`G4ConnectionRules.Validate`仅接受Secret Intake Purpose=`POSTGRESQL_READONLY`，应用UnboundSecretAsync也核对该用途。给Web复用此用途会把PG专用凭据用于另一协议。建议批准新增精确Purpose=`WEB_API_KEY`，限定与Web API_KEY_REF配置匹配；PG规则不变。必要修改范围：Contracts/G4ConnectionRules.cs（公开校验行为）；应用秘密用途匹配；相应合同/权限负例与UI intake。现有Purpose字符串列可容纳，不需要迁移，但用途语义是新批准项。
2. NONE：Create DTO已允许null SecretRef；草稿Probe DTO与Rules却强制非空，持久生命周期Create/Enable/Worker要求真实Secret记录。建议另行批准无凭据语义，明确持久SecretId/SecretVersion表示及草稿Probe nullable规则；禁止伪造秘密/凭据版本或用PG凭据占位。可选择本切片仅API_KEY_REF、明确拒绝NONE，避免扩大此次数据库/nullable合同范围；该缩减需用户确认。
3. 任务入口：host_continuity.py的CLI task-id名单无本任务，execution_preflight.py无M2消费者。附件允许workflow*新TaskId适配；可在该适配器中复用已有只读函数并校验真实M2消费者，不必放宽旧脚本。接口存在不等于门禁可运行。
4. 环境：prepare第一次后端离线restore成功，但Web来源锁定到已经不存在的历史Worktree。停止同输入重跑。可用候选缓存只定位到g4-eng-workflow-001和g4-eng-workflow-env，尚未重新验证；需要任务专属来源绑定/逐成员校验与回归，不能只改路径就宣称READY。依然零下载；原历史准入证据不改。

建议最小决定：批准第1项的精确公共行为扩展，并将当前切片限定API_KEY_REF；NONE/OAuth/分页策略在本切片明确拒绝。若要求同时支持NONE，需明确批准第2项无凭据语义与nullable契约。审批后继续普通范围内实现、P0环境修复与真实验收；不重复申请普通补丁。
