# 00 · 当前状态审计

《OntologyPlatform G0 审计与实施计划 V1.0》归档正文。审计日期：2026-10-23，Asia/Shanghai。

当前状态：仓库可作为新工程起点；审计时当前分支只有 README 和启动合同，没有旧系统源码，也没有待清退的 TMDL 实现。

## 状态定义与授权

- **OBSERVED**：实际读取文件、执行只读命令或访问官方正文得到的观察，注明范围和日期。
- **PROPOSED**：目标设计、目录、接口、任务或验收方案，不代表已实现或已获实施授权。
- **NOT_VERIFIED**：缺少环境、资料或执行证据，尚未核实。
- **NOT_RUN**：命令、测试、PoC或演练尚未运行；计划文档和静态审查不能替代执行结果。
- **NOT_FOUND**：在明确检查范围内未发现，不推断外部或历史系统不存在。
- **CONFIRMED**：项目需求或方向已确认，不等于实现通过。BLOCKED与USER_DECISION_REQUIRED分别标识门禁和待决策事项。

本次仅批准 G0 Markdown 文档归档；G1–G8 均未授权。审查记录见 [10-g0-review-record.md](10-g0-review-record.md)。

## 仓库事实

| 检查项 | 状态 | 证据与结论 |
|---|---|---|
| 仓库身份 | OBSERVED | `origin=https://github.com/on-dotnet/ontology-platform.git`，符合补充要求 |
| 审计分支 | OBSERVED | `main`；归档单独使用 `codex/g0-plan-baseline` |
| 审计 HEAD | OBSERVED | `226457bfbbd1e16bd1608115a72de7682b0811ef`，`chore: initialize ontology platform` |
| 审计工作树 | OBSERVED | 审计前后 `git status --porcelain=v1 --untracked-files=all`、`git diff --stat` 均无变更输出；归档前再次确认无变更 |
| 审计文件 | OBSERVED | `git ls-files`、HEAD 文件树及包含隐藏文件的枚举均仅发现两个文档 |
| README | OBSERVED | [README.md](../../README.md) 仅包含项目标题 |
| 项目合同 | OBSERVED | 已完整读取 [启动合同](../bootstrap/ontology-platform-codex-master-plan-bootstrap-v1.0.md)，作为冻结需求基线 |
| 指令与配置 | NOT_FOUND | 仓库及已检查祖先目录无 `AGENTS.md` / `AGENTS.override.md`；审计时仓库无 `.agents`、`.codex`、`.github` |
| 前后端实现 | NOT_FOUND | 无 `apps/web`、`backend`、依赖清单、锁文件、构建脚本或数据库迁移 |
| 语义与 AI | NOT_FOUND | 无本体、Shapes、映射、指标规则、Agent、MCP、文档 Worker 或演示实现 |
| 测试与运维 | NOT_FOUND | 无测试工程、测试报告、CI、部署、观测或灾备配置 |
| TMDL 实现 | NOT_FOUND | 仅合同说明中出现 TMDL；无 parser、serializer、UI、API 或状态机 |
| 远端其他历史 | NOT_VERIFIED | 未 fetch 或审计其他远端分支、外部旧仓库，结论仅针对审计工作树和 HEAD |

## 环境观察

| 工具 | 实际观察 | 影响 |
|---|---|---|
| Codex CLI | `0.163.0-alpha.11.2` | 是本机版本，不能据此宣称最新正式版本；G0会话已实际使用子 Agent |
| .NET | SDK `10.0.401`；运行时 `10.0.12` | G1 需准备批准后的固定工具链 |
| Node / pnpm | `v24.21.0` / `11.25.0` | 仅证明本机存在，未验证项目兼容性 |
| EF 全局工具 | `dotnet-ef 9.0.7` | 后续使用仓库局部 EF10 工具，避免误用全局工具 |
| Aspire CLI | PATH 未发现 | 未排除其他安装位置 |
| Docker | CLI 存在，配置访问受限 | daemon、镜像、网络和容器启动均未验证 |

Git 查询提示无法读取用户全局 ignore 文件；本轮未修改用户配置。已读取的 tracked tree 与审计非 Git 文件枚举相符。

## 复用与迁移

- **保留：**仓库身份、README、启动合同和已确认决策。
- **修改提案：**G1 扩充 README，增加工程配置和实施文档。
- **删除候选：**无。
- **TMDL 清退：**当前不需要迁移。未来若提供旧实现，先审计 UI、权限、生命周期和测试的可转移价值，再单独提出迁移 ADR。
- **完成度：**不能将合同中的技术方向写成已实现能力；全部运行验收为 `NOT_RUN`。

## G0 审查摘要

1. 主要风险：所有业务链路、测试和部署能力尚未实现；本机 .NET 补丁低于当前官方版本；Docker 服务可用性未验证。
2. 架构建议：保留 Modular Monolith，统一 `OntologyPlatform.*`；单一 API 宿主集成 YARP/BFF；Next.js 独立 SSR；区分 BuildingBlocks、ServiceDefaults、研发 Agent 配置和运行时 Agent。
3. 顺序：G1基础闭环→G2最小AI Native切片→G3语义治理；G4/G5/G6按依赖推进→G7调查→G8生产验收。
4. 首条切片：真实登录→可信样例本体→SHACL→人工审核→不可变发布→Jena正式查询→受控MCP/Agent→SSE证据→回滚重查。
5. 已完成三个只读子 Agent 审计并由主会话交叉核验；后续实施需任务所有权、工作树隔离、公共契约Single Writer和独立审查。
6. 权限、审计、观测、语义保真、恢复、真实数据源、许可与供应链从G1贯穿；未执行均为NOT_RUN。
7. G1仍等待专用授权；生产凭证、硬件、SLO、RPO/RTO、保留期限和兼容性按阶段确认。
