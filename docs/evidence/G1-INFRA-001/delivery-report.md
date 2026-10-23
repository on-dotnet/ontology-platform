# G1-INFRA-001 V2 交付与审查入口

日期：2026-10-23。状态：READY_FOR_REVIEW；本机工程验收PASS，最终快照/远程CI/构包结果以审查ZIP的manifest.json和CLI复检结果为准。仅当前任务，不代表整个G1或G1-ENG历史PARTIAL变更。

## 授权、基线与协作

用户明确确认“按V2全部授权执行，采用Worktree并行”。[授权原文](authorization-v2.md)、[任务卡](../../tasks/G1-INFRA-001.md)、[独立审查](independent-review.md)。阶段BaseSha固定c4679e956d505acd33185e5a289329de67452c84；不用origin/main..HEAD代替阶段diff。

| 工作项 | 分支 / 最终已审头 | 工作树及所有权 |
|---|---|---|
| Master集成 | main；交付HeadSha及main集成SHA等于最终manifest.headSha | C:/Users/Administrator/source/repos/ontology-platform；根规范/工具/构建/solution/CI/总证据单写 |
| A构包 | codex/g1-infra-001-review-pack；d96f1f5b226c750d7beda270b36b8de7a091da78 | C:/Users/Administrator/.codex/worktrees/g1-infra-review-pack/ontology-platform；构包脚本/测试/规范/A证据 |
| B基础设施 | codex/g1-infra-001-aspire；c120b5ff5128346b7709191589f6e5889d671ccd | C:/Users/Administrator/.codex/worktrees/g1-infra-aspire/ontology-platform；四工程/五锁/开发资源/B证据 |
| C研究 | infra_toolchain_research，只读，无新树 | 官方工具链/容器来源核实；安装由Master隔离执行 |
| Reviewer | infra_rules_review、infra_implementation_review，只读 | 规则/构包/根接线与基础设施/全部5手写C#专项分别审查 |

规则968ab2a、工具准备7ba3839、语法门禁2547e6d、A集成7d1da77及两任务分支均已普通push成功。B通过no-ff合并和根接线完成最终阶段提交；Git完整提交关系见ZIP git/commits.txt。没有强推、覆盖用户修改或删除未整合成果。最终两Worktree/分支保留，A/B均干净；主树提交后干净，ZIP/工具/产物忽略不入Git。

## 实现清单

- 项目隔离SDK10.0.402、Node24.22.1、pnpm11.28.8、局部EF10.0.13；官方发行物哈希实测匹配，未改机器PATH或默认工具。详见[工具证据](toolchain.md)。
- AppHost负责开发编排，ServiceDefaults只承载健康/OTel/发现/HTTP弹性，最小InfrastructureApi无业务端点，InfrastructureTests有4项真实回环测试。没有建立无需求BuildingBlocks、packages目录或前端共享包。
- PostgreSQL18、Jena6.2.0/TDB2、RustFS1.0.3、Keycloak26.8.1：固定三预构建镜像摘要，Jena官方包SHA512与Java基镜像摘要；独立开发卷、安全秘密引用、就绪探针/启动依赖。见[操作手册](../../development/local-infrastructure.md)。
- 五份真实NuGet锁含平台独立AppHost工具图，CI使用locked-mode；110个唯一锁图包+2个SDK许可核实；已恢复依赖漏洞查询未报告已知易受攻击包，边界见[B依赖](B/dependencies.md)。
- Git并行规范、YAML/TOML真实解析、禁止依赖/机密有限扫描、审查包正反例接统一verify与官方SHA固定的CI；[构包规范](../../development/review-package-spec.md)。

## 实际验收

| 检查 | 观察结果 / 证据 |
|---|---|
| doctor -CheckDocker | exit0；精确工具版本与Docker29.8.2，见[输出](doctor-final.txt) |
| 根solution restore --locked-mode | 四真实工程exit0，见[输出](restore-final.txt) |
| verify -SelfTest -RunNative -RunTests | exit0；静态/历史8项/doctor回归/结构化4项/ReviewPackage35项通过；真实solution构建0错误，MTP4通过/0失败/0跳过，见[输出](verify-final.txt) |
| 格式工作区警告核查 | 诊断级别exit0，四工程分析器均运行，21文件/0格式改动；警告原因为ASPIRE010，未隐藏，见[诊断](format-diagnostic.txt) |
| 整栈/重启 | 五HTTP探针200；PG随机标记、TDB2测试URN、S3对象内容、Keycloak非秘密身份ID重启保持；端口仅回环，见[运行摘要](B/runtime-summary.json) |
| 基本日志关联 | 真实404请求TraceId与日志scope一致PASS，见[结果](B/trace-correlation.json) |
| 独立Review | A、B、Master共享接线最终Critical0/Important0/未解决Minor0；审查不是重复运行全部容器 |
| 最终CI | 提交后查询GitHub实际run ID/URL/headSha/conclusion；最终ZIP通过显式四个Ci参数嵌入同一HeadSha事实。本文件不伪造自引用提交hash，也不以空status判PASS |

## 保留事项与状态语义

OBSERVED仅指实际命令/运行事实；PROPOSED指未来方案；NOT_VERIFIED指尚无充分验证；NOT_RUN指未执行。计划、静态审查、版本存在和零测试不等于实现或运行PASS。

ASPIRE010提示未用CLI bundle；当前官方NuGet Dashboard/DCP回退已实测能启动资源，CLI特有能力未验证。DCP本机日志连接警告回退控制台；Dashboard ingest、完整OTLP传输/检索NOT_VERIFIED。镜像CVE扫描、OS层完整SBOM/复合许可、生产部署/备份恢复未验证。它们不冒称本轮已实现，不影响已记录的开发探针/四资源持久化事实。

所有本次测试宿主和四最终测试容器已停止，隔离测试卷保留；临时秘密清除，不将带随机初始化密码的测试卷当作可复用日常开发卷。原生Web lint/typecheck/build/test/E2E NOT_RUN：apps/web只有清单，未获准实现真实前端。

SEC仍需正式身份/业务认证合同，FE仍需已批准Design System及真实Web工程，OBS仍需完整遥测后端；均未授权。本轮不执行这些任务或G2。交付一个已提交快照ZIP并重开核验后，输出G1_INFRA_001_READY_FOR_REVIEW立即停止，等待用户下一轮专用授权。

## 审查包

以阶段BaseSha与已提交HeadSha执行create-review-package，EvidencePath使用[逐项验收JSON](validation.json)。真实最终CI通过四个Ci参数绑定HeadSha，避免证据提交的自引用问题。ZIP只在忽略的artifacts/reviews，不提交、不上传第三方。文件路径、大小、整个ZIP SHA256和独立VerifyOnly结果由最终答复提供；包内完整源码/diff/提交/证据/成员SHA256均可复核。有限路径/秘密模式加人工Review不等于全面防泄露保证。
