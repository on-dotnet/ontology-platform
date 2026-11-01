# G4-00-CONTRACT-001 · 本体平台五源连接与 AI Native 语义数据合同

状态：合同独立Review通过 / PARTIAL；最终V3重开以包外回执为准。产品 NOT_RUN。2026-11-01用户明确“批准执行 G4-00-CONTRACT-001”；随后明确批准仅本任务隔离安装Schema验证依赖。不是G4-M1/main/G6集成许可。

BaseSha=d1a61daffe844475b07705797e3ad325cc3f2945；fetch后origin/main与HEAD相同。branch=codex/g4-00-contract-001；托管Worktree=/Users/chasen/.codex/worktrees/g4-00-contract-001/ontology-platform。

Owner/公共合同唯一写者=Master。非作者Reviewer只读，无owned_paths；推荐GPT-6.1 Sol/high，以派发回执为实值。无产品Worker。

## ExecPlan 与文件所有权

1. 完成ZIP/Manifest/SHA、安全解包及README/09/14阅读；保存唯一输入原字节。
2. fetch绑定真实origin/main，读AGENTS/PLANS/current authorization/G2/G3/E0/V3/生命周期；独立托管树。
3. Master只写docs/contracts/g4-00-{connections,mapping,query,ui}.md、docs/planning/g4-implementation-plan.md、本任务卡、docs/evidence/G4-00-CONTRACT-001/**。Schema和样例归Evidence，不写docs/contracts/g4/，不修改current-authorization（用户路径限制优先）。其余仓库/历史合同/AGENTS/脚本/产品/主干全部只读。
4. 先G2逐字段及状态/权限/API对照，再21正/16Schema负/3语义负、两个内联JSON；测试只覆盖设计，不宣称HTTP/五源通过。verify -SelfTest输出ignored artifacts；证据Schema早检、git diff --check。
5. 独立Reviewer至少15攻击反例并覆盖UX/五源/权限/SQL/SSRF/版本/资源，Master定向修正复验；提交任务分支并push，不合main。
6. LOCAL schema2绑定testedCommit及不变输入，唯一V3 PARTIAL，Reviewer独立VerifyOnly重开。必要门禁不满足则BLOCKED_WITH_WITNESS。

## 风险、最短验证与回退

缺jsonschema：原解释器exit3，不安装全局；用户后续批准任务隔离安装，需官方来源/精确版本/许可核查。E0 check --milestone G4-00 exit2，仅支持M1..M5；本轮无新Host/audit/DI/运行消费者，记录NOT_APPLICABLE而不伪造G4 PASS，不修公共脚本。宿主preflight POLICY_READY，lockDisplayTrial/sessionContinuity未验证，不用于产品连续性PASS。

G3兼容冲突→EXISTING_CONTRACT_WINS；字段/状态歧义→CLARIFY_IN_G4_CONTRACT；需权限/依赖/产品变更→REQUIRES_USER_DECISION。所有S-01..70/五源/Docker/模型/浏览器/.NET/CI本轮NOT_RUN。失败先最短定位，未变不盲跑整仓。

回退为保留任务分支/未整合树供复审；未触main无需回滚主干。资源仅任务树、输入、静态输出、唯一ZIP与已批准隔离验证依赖，旧树/卷/私有runtime保持；不启动Docker/模型/收费API。完成后停ChatGPT复审，不自动M1。


## 当前交付冻结记录

原21正/16Schema负/3语义负/2内联、G2源绑定37项、Review补充28项均实际通过；独立Reviewer另验10反例，当前无P1/P2。工程SelfTest exit0，后续只跑最终静态及输入绑定，不重复无关完整验收。Review回执/验收/失败/精确cleanup均在本任务Evidence。唯一V3为PARTIAL，CI与全部产品runtime NOT_RUN。M3回滚DTO和M4完整Datum仍需ChatGPT裁决后冻结，不把设计样例称完整产品wire。Head/TestedCommit/ZIP/hash/独立重开取已提交validation和最终包外回执，避免自引用。
