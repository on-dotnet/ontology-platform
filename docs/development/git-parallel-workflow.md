# Git并行开发与恢复

1. Master开工和集成前fetch，检查main/origin/main、工作树和基线。未预期改动/分叉保护现场，不reset或强推。
2. 每个独立写项有owned_paths、只读依赖、合同Owner、Reviewer、BaseSha和独立任务分支，使用托管Worktree，不共享写目录。只读研究可共享读取。
3. 单写者拥有根配置/CI/锁文件/公共合同；其他任务提出请求。路径规范化且目录不嵌套；仅切分支不等于隔离。
4. 可验证里程碑记录命令、退出码、失败/NOT_RUN，再commit并push任务分支。DRAFT/PARTIAL可备份，不等于准入main。
5. Master独立审查分支头/diff，解决合同冲突，执行集成检查，以可追踪merge/PR/cherry-pick分批进main并push。CI必须实际run信息，空status不推断成功。
6. 更新失败保留分支和树，记录已推/未推commit及恢复步骤；重新fetch检查，不盲重试覆盖。凭证由系统helper处理，需人类时遵守流程，不读取/打印token。
7. 阶段末以明确已提交Base/Head生成一个ZIP并重开复验，路径/hash交付。审查、归档、安全集成后才清理托管树，不丢未整合工作。列剩余分支/树及下任务授权。

规则源于2026-10-23人类明确批准的G1-INFRA-001 V2，覆盖旧偏好但不篡改历史任务证据。每阶段完成或受阻交回审查，不自动进入下阶段。
