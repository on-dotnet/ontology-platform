# Mac Master 交接记录 · 2026-10-25

当前关口 M0-MAC-PORTABILITY-001，尚在执行，最终状态以 [总报告](../evidence/M0-MAC-PORTABILITY-001/delivery-report.md) 和标准包manifest为准。前序 main 基线25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1；fetch后与人类指定基线一致，无未知提交或本地改动。用户明确批准迁移合同第二节至文末，范围不含SEC/FE/OBS/G2。

## 可恢复协作状态

| 职责 | 工作目录 | 分支 |
|---|---|---|
| main唯一集成目录 | /Users/chasen/Developer/repos/ontology-platform | main |
| Master隔离实施 | /Users/chasen/.codex/worktrees/m0-master/ontology-platform | codex/M0-master |
| A脚本 | /Users/chasen/.codex/worktrees/m0-scripts/ontology-platform | codex/M0-scripts |
| B容器 | /Users/chasen/.codex/worktrees/m0-containers/ontology-platform | codex/M0-containers |

三树均由Codex托管创建，不复制Windows树；独立目录/分支和各自Git管理目录，公共对象库共享是正常Git机制。每条命令显式workdir，客户端最后创建树会改变后续默认cwd，因此不得依赖隐式cwd。root/main只有Master集成；根配置、锁、CI、AppHost共享配置单写。路径冻结见 [任务卡](../tasks/M0-MAC-PORTABILITY-001.md)。

explorer自定义角色实际发现并成功委派只读任务；platform_worker实际按A/B路径并行执行；quality_reviewer独立只读审查。开发者角色说明与仓库TOML一致，仅证明加载/派发与实际行为，不能推导独立OS只读沙箱。它们不是Microsoft Agent Framework产品模块；本轮没有MAF业务实现或付费模型API调用。

Master任务卡提交e3f0b9694412f7a91b6075be9d7e8d4fac4b890b，已推送。原生Mac锁及工程验证里程碑4d6f0a7ca3beacba68f171d57a711b18902e9f22。A提交a24edf72ab4ea2732af9f4bb507fda7160a3de2a，独立审查后才能集成。B最终提交、总审查和main状态将随收尾补记，不靠聊天私有历史恢复。

## 环境和重启

按 [Mac手册](../development/macos-setup.md) 使用固定工具与项目隔离pnpm/Python。Master .tools保存本轮已校验pnpm11.28.8及PyYAML，其他树只读复用；这些忽略工具不进入Git/ZIP，换机器重新按官方哈希恢复。macOS27.0.1/arm64，SDK10.0.402；真实恢复生成osx-arm64锁后，locked restore/build/4项MTP/format exit0。ASPIRE010保留，NuGet平台工具回退不是CLI bundle功能验收。

首次沙箱拒绝.git/FETCH_HEAD、Docker socket或外网DNS不代表工具故障；使用客户端正常审批流程重跑同一命令。不chmod socket、不读取auth材料、不复制OS helper机密、不改用户PATH。允许的Git和依赖恢复使用宿主审批，不等于系统管理员安装授权。中断后核对Agent状态及运行进程，不重复起栈；只在本任务明确创建的开发容器和卷运行探针。

Windows历史报告和卷保留事实，本机没有继承Windows私有会话或数据库。Windows M0运行NOT_RUN；Linux门禁须读取实际Actions head/run/conclusion，不能由Mac通过外推。跨平台矩阵及日志见总证据。最终只交付一个标准ZIP；独立重开核验后停M0关口，等待人类复审与下一阶段授权。
