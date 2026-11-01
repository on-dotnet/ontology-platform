# G4-M1-CONNECTION-001

状态 IN_PROGRESS / P0-P1。授权见 ../evidence/G4-M1-CONNECTION-001/authorization.md。
BaseSha=8afc5d4dfd32e7adb48262cce6587057c0e68715，origin/main=d1a61daffe844475b07705797e3ad325cc3f2945。
Master 分支 codex/g4-m1-connection-master；托管树 /Users/chasen/.codex/worktrees/g4-m1-connection-master/ontology-platform。

## DAG / Gate

P0 基线/供应链/宿主/资源→P1公共合同及正反例→非作者Review→P2独立PG/UI与Master组合→P3最短真实PG/OIDC/HTTP→P4Catalog/完整交互→P5稳定完整本地/独立Review/提交绑定/自身资源清理/唯一V3独立重开。首次任务集成不得等全部页面完成；不合main。

## 所有权

Master：Contracts/G4ConnectionModels.cs，Connections模块下除Adapters/**以外的文件，所有项目/锁/迁移、Host/G4/**与必要组合入口、Governance审计白名单、实验Compose/脚本、Web生成类型/生成器/共享Shell、任务/证据/合同、E0精确扩展。
PG Worker：Connections/OntologyPlatform.Modules.Connections/Adapters/**；ConnectionsTests/PgAdapterTests.cs及适用适配器测试。只读 Contracts/Abstractions/Persistence/Host/项目锁。
UI Worker：apps/web/src/features/connections/**、apps/web/src/app/data/connections/**及专属测试；只读生成类型/共享Shell/Design Tokens/锁。
Reviewer：只读，无owned_paths。P1通过后写者从同一冻结提交独立托管树开工，不跨树写入。

## 验收/恢复

先严格DTO/权限/状态负例，PG TLS/只读短验，再HTTP/OIDC/CAS/审计事务，最后真实浏览器/故障恢复/资源。沿用输入49项编号，不以静态或Mock代产品PASS。所有手写C#中文XML及局部用途注释专项Review。verify.ps1 -SelfTest输出ignored artifacts。CI默认NOT_RUN。TestedCommit至Head产品输入必须一致，diff-check exit0，唯一V3≤15MiB，截图≤12/3MiB。
历史失败：缺jsonschema→复用现有/private/tmp/g4-00-validation-venv（无安装）；Docker socket沙箱拒绝→批准只读复查服务正常；G3 E0不识别G4→Master新增准确G4消费者/资源身份，不使用G3任务冒充。
恢复保持本任务未合main分支/树及独有证据；仅准确已审TaskId资源可回收；旧G3/G6保持。
