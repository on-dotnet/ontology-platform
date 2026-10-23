# G1-INFRA-001 · 基础设施与标准审查包 V2

状态：READY_FOR_REVIEW；本机工程验收PASS，最终快照/CI/ZIP以[总交付记录](../evidence/G1-INFRA-001/delivery-report.md)及包内manifest为准。BaseSha：c4679e956d505acd33185e5a289329de67452c84。日期2026-10-23。人类已明确确认按V2全部授权并采用Worktree并行；旧阶段证据不重写。

## 分工与冻结所有权

| 工作项 | Owner / 隔离 | owned_paths | read_only_dependencies / 共享Owner |
|---|---|---|---|
| Master | main，唯一集成者 | AGENTS/PLANS/README、当前授权、ADR-006、git-parallel-workflow、根构建/CI/锁文件、scripts/doctor.ps1与verify.ps1、结构化解析器/requirements及其测试、本任务及总证据 | 其他树仅审查/集成；公共配置Master单写 |
| A Review Pack | 托管Worktree，codex/g1-infra-001-review-pack | scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1、docs/development/review-package-spec.md、docs/evidence/G1-INFRA-001/A/** | 根verify/CI只提请求；包格式A唯一Owner |
| B Aspire/Infra | 托管Worktree，codex/g1-infra-001-aspire | backend/src/AppHost/**、backend/src/ServiceDefaults/**、backend/src/Hosts/**、backend/tests/OntologyPlatform.InfrastructureTests/**（含其项目锁）、infra/development/**、docs/development/local-infrastructure.md、docs/evidence/G1-INFRA-001/B/** | 根solution/CPM/CI由Master；AppHost共享配置B单写 |
| C Toolchain | 并行只读，不需Worktree | 无写入 | 官方发行物/哈希/许可/安全；Docker只读调查；安装由Master隔离准备 |
| Reviewer | 独立只读 | 无写入 | 里程碑/最终集成差异、注释、安全、测试和包复验 |

同名分支/树冲突不覆盖；实际规范化路径由托管工具返回后写总证据。并行最多两个写Agent加只读研究，研究完成为Reviewer释放槽位。消息之外保留任务卡、commit和日志。分支真实验证后及时push，Master审查后分批main集成并push。

## 依赖DAG与范围

规则纠偏→树派发；C工具核实/隔离安装与A构包并行；B可先设计静态工程，真实restore/build/启动待必要工具满足。A/B合同冻结后Master接根验证和CI。最后独立审查→集成验证→已提交HeadSha→一个ZIP→复检→停止。

只允许最小健康API验证ServiceDefaults，不实现登录/BFF、Web Shell、正式业务、本体发布、MCP/Agent/SSE或完整LGTM。Docker不可用时不得安装系统Docker/改虚拟化，以PARTIAL/BLOCKED报告。

## 验收和停止

doctor真实目标版本；静态JSON/XML/YAML/TOML、禁用依赖、注释及有限敏感检查；构包正反例、重开归档、hash/路径/禁止项/diff；真实项目restore/build/适当测试；可用容器下启动、健康、重启持久化。缺失均NOT_RUN/BLOCKED，不伪造PASS。

CI必须run ID/URL/commit/结论或NOT_VERIFIED。包有明确Base/Head祖先关系、已提交快照和排除记录，不依赖origin/main..HEAD。成果先审后main，无强推；未整合树不清理。最终输出G1_INFRA_001_READY_FOR_REVIEW并立即停止。
