# G3-M4 Windows Phase 0 实测记录

日期：2026-10-29。状态：**BLOCKED**，不是 M4 产品交付。当前业务代码、公共合同、迁移及锁文件未修改；Slice A/B 均 NOT_RUN。以下为当前已观察检查，未完成项不会提升为 PASS。

## 权威与 Git

已读根 AGENTS、PLANS、当前授权、冻结 bootstrap、G3 总计划、ADR-005/006/009、效率规则、本地优先政策、Review V3、资源生命周期、M3 fixture 归属规则、M1/M2/M3 交付报告、M3 任务/合同/最终独立 Review。人类本轮 Windows 接续授权覆盖历史文档的阶段停止条款，其他限制不变。

用户附件原始 SHA256=`b415966a71cee16e3024c1fda0f9e038e35ddf5974e9fe0c1ab7f1b19802cd89`。[授权归档](../authorization-v1.md)与实际原件经 LF/末尾换行规范化后逐字一致；首次核对发现少一空行，已补齐并重新比对通过，不宣称原始文件字节/hash未变化。

实际 `git fetch origin` exit 0；origin=`https://github.com/on-dotnet/ontology-platform.git`。原主树 `main` 干净，HEAD=origin/main=`3992582e03df1a103fac36e7e82b8c81f85f622e`，恰为附件 M3 交付 Head；本地 `git branch --no-merged origin/main` 无输出。远端存在历史非祖先任务 refs，不从非祖先直接推断未集成或删除资格。M4 既有合同/任务检索未发现匹配文件，本次只建立接续任务卡，不谎称合同已冻结。

开工三个实际 Worktree：当前主树及旧 `g1-infra-aspire`、`g1-infra-review-pack`。第一次 Master Worktree 创建未完成，后串行 `git worktree add --quiet -b codex/g3-m4-master ../ontology-platform-g3-m4-master origin/main` exit 0；现有旧树、分支与引用没有删除或覆盖。

## Windows 与检查

| 检查 | 状态 | 实际结果 |
| --- | --- | --- |
| doctor -CheckDocker | PASS | exit 0；PowerShell 7.6.9，Windows 10.0.22631；隔离 SDK 10.0.402、Node 24.22.1、pnpm 11.28.8；Docker daemon 29.8.2 可访问 |
| Python | PASS | `python --version` 实际为 3.13.14；PATH 的 python3 为 WindowsApps 别名，Windows 脚本使用真实 python |
| 宿主/容器平台 | PASS | Docker context=desktop-linux，Engine linux/amd64；这不代表 Windows 原生容器或 macOS/Intel 业务验收 |
| 关键换行 | PASS | git ls-files --eol：global.json、package.json、pnpm-lock.yaml、doctor.ps1、verify.ps1、workspace-smoke.mjs 均 i/lf、w/lf、eol=lf |
| Web frozen restore | PASS | exit 0，389 包；锁文件未改，项目 `.tools/pnpm-store`，不升级全局工具 |
| Web lint | PASS | exit 0；锁定 Node/pnpm 运行 eslint . |
| Web typecheck | PASS | exit 0；锁定 Node/pnpm 运行 tsc --noEmit |
| OpenAPI → TS | PASS | `node apps/web/scripts/generate-types.mjs --check` exit 0，未生成/改写源码 |
| verify -SelfTest | FAIL | exit 1；CleanupResources.Tests.py 实际 52 tests，failures=23、errors=24；后续套件未运行 |
| 清理短复现 | FAIL | 单独 test_docker_exact_whitelist_and_dryrun：1 test/1 failure，0.955s；REFUSED: Root must be Git toplevel |
| 后端受锁恢复首次 | FAIL | 计时器实际 exit 130，errorCategory=INTERRUPTED；209388ms；不能当成功，不能推断网络或依赖根因 |
| 后端受锁恢复串行重试 | PASS | exit 0；timeline 21000ms；原首次中断保留，未修改依赖或锁 |
| 后端 build | PASS | solution build --no-restore exit 0；timeline 24040ms；19 个真实项目输出，既有 ASPIRE010 警告 1 个，无编译错误 |
| 证据 Schema 早检 | PASS | new-review-evidence 生成 LOCAL schema2/NOT_RUN，test-review-evidence exit 0；仅 EVIDENCE_SCHEMA_ONLY，产品 NOT_RUN |
| canonical Fuseki 身份 | PASS | --identity exit 0；linux/amd64，contextSha256=dba8036818246baaefc136fa6740729e9be068c79dd0c2ae584f895192406091；只计算身份，不代表镜像存在或服务测试通过 |
| 真实 PG/Jena/RustFS/浏览器 | NOT_RUN | Preflight 未放行，未启动业务整栈 |
| 本轮云 CI | NOT_RUN | 本地优先，不触发无必要云验收 |
| M4 独立产品 Review/正式 V3 | NOT_RUN | 尚无产品候选和完成门禁，不生成冒充正式交付的包 |

实际工具入口来自原主树 `.tools`；未修改机器 PATH、默认 SDK、全局 EF、Docker/WSL 或系统配置。Web 受锁恢复不等于完整 Web build/test 或浏览器通过。

## 阻塞与廉价定位

**B0-01：Windows SelfTest 失败。** `scripts/maintenance/cleanup_resources.py` 的 preflight 将 `git rev-parse --show-toplevel` 字符串直接与 `str(Path)` 比较；Git 在 Windows 返回正斜线路径，Path 使用反斜线，导致安全根校验错误拒绝。单测试已在不到 2 秒内重现，无需重复完整 SelfTest。完整失败另包含 cache 元数据依赖 POSIX O_NOFOLLOW/dir_fd 的正确拒绝，以及 fixture 的平台执行/符号链接假设。不能删除安全守卫或把 REFUSED 当 PASS；本次尚未修改清理执行器或测试。

**B0-02：首次后端恢复中断，已解除当前恢复/编译阻塞。** 首次长命令被中断而非成功，进程输出曾与其他终端命令交错，以 timeline 实际退出为准。改为串行恢复后 exit 0，随后真实 solution build exit 0；没有推断未经观察的网络/依赖根因。后续长命令继续串行执行，不覆盖首次 INTERRUPTED。

## M3 继承事实与独立只读复核

实际只读 Agent 初次调用 ERR_HTTP2_PROTOCOL_ERROR，没有结果；缩小为 M3 delivery-report.md 与 final-independent-review.json 后重试成功。复核确认历史 M3：400 业务检查 PASS、故障 8/8、性能 27 样本，绑定前五关与后两关，原外层 FAIL 保留；必要 P1/P2=0。该记录当时最终 V3/独立重开仍 NOT_RUN，不在本轮伪造后置成功。此只读复核不是本轮产品或 Preflight 变更的独立 Review。

本轮文档独立审查初次 ERR_CONNECTION_CLOSED，未取得结果；缩小后重试实际读完任务卡、本文、validation.json 和 timeline，结论无必要发现，仅同意 DRAFT 文档提交，不能放行 M4，详见[回执](preflight-review.md)。Reviewer 没有复跑测试或核验 Git diff，不提升为产品审查或真实测试通过。

历史 M1/M2/M3 均将 Windows 原生列为 NOT_RUN。Monaco BLOCKED/PAUSED_BY_USER、真实收费 LLM 未运行、完整 OWL 推理/G4/G5未实现、生产 HA/SLO/供应链专项未完成、artifact 预算未知与归档活跃引用守卫继续保留，不因本轮 doctor PASS 消除。

## 资源与计时

只读 inspector `-IncludeDocker` exit 0：本机全局可见 containers=1、volumes=1、images=1、history=0、networks=5；可见容器/镜像属于其他项目，不是可复用的 M3 栈。未读取 env/凭证/卷内容，未创建 M4 Docker 对象，未执行删除或全局 prune。此前 M3 在 Mac 保留的 G2 卷数量不移植为本机事实。

本轮资源增加为一个 Master Worktree、隔离 Web/后端依赖、编译产物与工具缓存；均 ACTIVE/KEEP，用于诊断和恢复，不能在任务未关闭时回收。旧两树/历史分支和未知 Docker 对象保护；M4 Docker 删除候选为零。物理容量回收 NOT_VERIFIED。本机唯一可见镜像不是 canonical Fuseki；provisioning 未运行，不复用旧 G2 或其他项目卷。

原主树 ignored `artifacts/validation/G3-M4-001/preflight-timeline.jsonl` 记录已采集命令，[冻结记录](preflight-timeline.jsonl)保存相同字段观测值。输入标识为 `SHA256(BaseSha + '|windows-x64|sdk10.0.402|node24.22.1|pnpm11.28.8')`=`7ea4ec154e1f0f4d8fc867da029e5ba39e027b1ed2ea91dedcd6b5a9cd195b31`。这是本次命令输入标签，**不是**全部工具二进制、依赖和环境的内容寻址证明。

Windows 原始 JSONL 含 CRLF，原始 SHA256=`fcd4a4da08606e24fa2350bc255a354e94961896e5128c4176014e69ae6ceaf7`；Git 归档规范为 LF，SHA256=`6dacb197aed9e2d1c64e38b5bf5a59d9f9557f2610a2f0b22783193bb9c802af`。原始字节散列比较确实不一致，随后仅规范换行的逐字文本比较通过，全部观测字段和值不变；不能把它描述为原文件逐字节复制。

实际 summary：8 个区间，墙钟跨度 1006592ms、区间并集 498848ms、累计执行 498847ms、可观察关键路径 209388ms、并行重叠 0ms、同标签同输入重验 1 次；COMMAND_FAILED=2、INTERRUPTED=1。毫秒取整使并集与累计相差 1ms，不将其解释为并行收益。短复现属于不同命令标签，未算入同标签 recheck。Agent 活跃/思考、Token/费用、未采集区间均 UNKNOWN，不能用聊天跨度代替。

证据格式失败另记：首次新 Markdown 静态检查发现换行不合规，规范本轮文件 UTF-8/LF 后静态 exit 0；首次正式 validation.json 早检因 EVIDENCE_EOF 拒绝，规范换行后同入口 exit 0、14 checks/EVIDENCE_SCHEMA_ONLY。没有改校验器、检查状态或产品输入以取得通过。这些命令未进入上述八区间计时，耗时 UNKNOWN，不能漏报后再推估为零。

## 本地提交与远程备份

七份文档/证据首次 DRAFT 提交 `05cb966`，最终 staged diff-check exit 0；原主树 main 干净，未改产品/锁。已提交 Head 的 LOCAL 早检实际 exit 0、14 checks/EVIDENCE_SCHEMA_ONLY，证明只含允许的文档增量，不代表产品验收。独立 Review 仅核对四份材料的一致性，范围限制保持。

`git push -u origin codex/g3-m4-master` 实际 exit 1：Recv failure: Connection was reset。随后仅一次 `git ls-remote --heads origin refs/heads/codex/g3-m4-master` 实际 exit 1：Failed to connect to github.com port 443 after 21056ms。开工 fetch 成功不代表此后网络仍可用；当前远程备份 **BLOCKED**，本轮未成功 push，不将远端分支存在性判定为已验证。未改代理/凭证/全局配置，不强推或重复长等。网络检查不在八条 timeline 内，其余未采集耗时 UNKNOWN。后续本地提交只补充这些已发生事实，不预填自己的未来 SHA。

## 后续顺序与停止

先解决/验收 Windows SelfTest 平台阻塞；必要项全部通过后才 CONTRACT-A 正反例及独立 Review，再按任务卡执行 A → A 集成门禁 → B。后端恢复/build 已通过，不重复相同产品输入下的无关完整检查。当前只允许相互独立的环境诊断和证据记录，M4 业务实现停止，不输出附件完成标记，不自动启动 M5。
