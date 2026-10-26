# G2-PUB-001 实施证据

当前状态：**DRAFT / READY_FOR_REVIEW候选，整体G2仍PARTIAL**。BaseSha=457911442aaa12f3ba170ee43c70343b64581f39。PUB独立应用实现及真实三依赖矩阵已完成：冻结源码930c2239b2df9065be75b79cf576e803d965c86d在干净工作树上完整46/46通过，0 skip、exit0。独立Review、Master集成及真实HTTP/FE/QRY闭环仍由Master执行，本分支不代表完整G2通过。

## 初始模型里程碑（历史证据）

初始阶段仅模块模型/Factory，审批/制品/图/事务/Outbox与真实故障矩阵当时尚待实施。

- `git fetch origin`：首次沙箱 FETCH_HEAD 写入拒绝，使用明确任务授权的 escalation 后 exit 0。
- `dotnet build backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing -c Release --no-restore`：初次 exit 1，缺 project.assets.json。
- `dotnet restore backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing --locked-mode`：exit 0，已有锁/批准依赖，无依赖改动。
- 同一 Release build：exit 0，0 warnings / 0 errors。
- 产品测试、真实迁移、外部制品、HTTP、CI、独立Review：NOT_RUN / NOT_VERIFIED。

模型明确准备记录/正式标识、独立提案及单次消费、资产唯一 Active 与单调 revision、完整命令预留/回执、激活历史、Outbox 租约/fence 与 eventId 唯一调和回执。Master 唯一生成迁移。

## 服务与真实对象阶段（DRAFT）

已实施：纯审批资格规则；真实SigV4固定回环S3条件写及有界GET；独立只读Catalog与全制品/图核验；提案/异人审批；固定manifest预留；PUBLISH draft→proposal→active与ROLLBACK proposal→旧release→active分支；同物理事务CAS、Governance writer、持久回执/Trace/Outbox；真实后台lease/fence及eventId唯一调和回执。HTTP只绑定明确分配的PublishingEndpoints.cs；未修改Host启动组合。

真实测试：
- approval-red.txt：4 tests，3 failed，exit 2；同主体、短角色、到期瞬间负例。
- approval-green.txt：4/4、0 skip，exit 0。
- s3-first.json：错误filter选择零测试，exit 8；不记作通过。
- s3-actual.json：真实RustFS 1.0.3，3/3、0 skip，exit 0；UTF8回读/相同内容幂等、不同内容覆盖拒绝且旧字节保留、并发同键不同字节唯一写成功、缺失和错SHA256均失败关闭。
- implementation-build.txt：实际服务和新测试工程编译exit 0。初次测试触发器DDL拼接有3项EF1003提示，均仅由固定测试表白名单和服务端生成hex标识组成；将进一步整理固定DDL参数边界。

S3官方依据：[条件写及412](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)、[PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html)。采用 If-None-Match:* 纳入SigV4签名，GET核对完整长度和SHA256；ETag不当内容hash。此为逻辑不可变，不声称生产WORM或跨服务ACID。没有新增AWS SDK或依赖。

当前完整PG故障矩阵、回滚、并发、Outbox恢复仍NOT_RUN，等待Master生成并交付真实迁移及SEM剩余源提交；测试源码已准备。当前capabilityVersions为空(absent)，完整G2必须QRY真实登记后重新发布R1/R2。无真实HTTP/浏览器/CI/独立S2审查通过声明。

工程验证增量：SelfTest首轮因当前树未恢复批准的PyYAML、日志尾随空格、生成lock无末换行和随机密码变量名的有限模式误报失败；保留selftest-first.txt。仅项目隔离恢复requirements原锁PyYAML6.0.3，修改自身文件格式和变量名，没有弱化scanner。再次SelfTest真实exit0，selftest-green.txt。格式从backend cwd solution-relative owned清单运行exit0；测试项目尚未注册solution，单独format也exit0。日志只规范尾随空格和末换行，测试内容/次数/失败保留。

## S2候选实现完成增量（2026-10-26，待独立Review/集成）

前述“等待迁移/源码”的历史状态已经解除。Master授权消费迁移a0601b6，本树对应eedab2d；SEM剩余8308340、13cba4f、8b9bd188对应6e99f5e、bd5b7ac、2cde4a1。共享8971ea6已在初始祖先。PUB未生成或改写任何迁移、共享合同、既有锁、Host组合、solution或其他Owner代码。

真实结果（每份JSON含原命令、exit、完整安全输出及运行时源码SHA/工作树状态）：

| 证据 | 结果 | 证明范围 |
|---|---|---|
| full-first.json | 34/34，0 skip，exit0 | 真PG/S3/Jena及三个模块真实Up；两版/回滚/原子故障/重放/worker |
| expanded-matrix.json | 41/41，0 skip，exit0 | 增加真实迁移空Down/非空Down拒绝/并发55P03；不同提案CAS竞争、回滚自批/过期/目标绑定 |
| bounded-final-matrix.json | 43/43，0 skip，exit0 | 增加S3完整五秒预算/调用者取消；固定DDL+参数scope，build 0 warnings |
| rollback-faults.json | 3/3，0 skip，exit0 | 回滚旧对象不可用、治理audit失败、Outbox失败均保持R2；同命令恢复到完整R1，revision递增3 |
| proposal-contract-red/green.txt | 3/3失败exit2 → 3/3通过exit0 | 反向恢复旧缺失分支guard证明新回归有效，再恢复修复；缺PUBLISH字段、混合ROLLBACK、非法manifest hash在依赖前422 |
| selftest-final.txt | exit0 | 原仓库SelfTest检查器及35审查包测试；不冒称产品验证 |
| final-build-format.json | 见实际退出码 | Release API/PublishingTests真实编译和整solution只读格式验证 |

API编译证明新PublishingEndpoints适配原G2EndpointGuard签名，不代表Host已注册或真实HTTP验收。临时测试工程只新增MSTest.Sdk4.5.1及已批Contracts/Ontology/Governance/Publishing ProjectReferences，无新PackageReference。新工程与私有锁写权完成后移交Master；不修改其他锁。

安全一致性说明：

- PUBLISH服务端精确绑定当前draft/revision/hashes/真实成功报告；只有独立完整platform.auditor主体和完整scope可作一次批准。状态、24h到期、内容hash和命令修订均于最终事务重核。
- ROLLBACK草稿/校验字段必须全null，固定旧releaseId+完整manifest hash，另作异人审批；当前草稿推进不阻止旧完整版本回滚。既有图与源对象保留，回滚不调用正式图部署。
- S3只允许可信配置的数字回环地址、无代理/重定向、SigV4固定最小PUT/GET。条件PUT禁止覆盖不同字节；并发真实测试只有一个不同内容能占据同键。流式回读限制一MiB和完整五秒预算，完整长度/SHA256/源字节与PG清单一致才成功。
- 外部源对象、manifest本身及隔离Jena图/SHACL/受控查询全部回验后，才进入同物理PG最终短事务；PUBLISH draft→proposal→release→active，ROLLBACK proposal→旧release→active。ActiveId+单调activationRevision共同CAS防ABA。Governance自己加入相同DbConnection/DbTransaction；四个PG实际触发失败点都没有留下成功active/activation/audit/outbox。
- 一次持久预留固定releaseId与manifest字节；完整scope/operation/key+payloadHash+subject约束重试。提交回执先于依赖调用恢复，同命令并发只有一个审计和Outbox；不同提案只有一个CAS胜者。
- ReleaseOutboxDispatcher确为BackgroundService。短租约领取、实际源/图调和、第二短事务fence/owner/期限校验、eventId唯一消费回执、失败有界退避。实际Start/Stop、新worker接管、重复消费和旧fence拒绝已测试。延迟事件只查固定release，不修改active。
- 已激活后真实破坏Jena图导致Catalog明确503，Outbox不写成功回执、不切别版；恢复完全相同历史图后原事件可以重试。没有声称PG/RustFS/Jena跨服务ACID、生产WORM或生产GC。
- ReleaseActivation/ReleaseSummary持久真实actor.TraceId；模块ActivitySource/Meter为OntologyPlatform.Publishing，指标仅固定operation/status/phase。宿主OTLP注册由Master负责。

真实边界：该候选可进入独立PUB审查；整体仍DRAFT/PARTIAL。CI=NOT_VERIFIED。真实HTTP/Keycloak/FE/MCP/Run固定snapshot/OTLP全链由Master集成验收；本分支只证明独立应用用例和真实三依赖。QRY尚未注册时capabilityVersions明确空，未冒填v1；最终G2必须真实registry后新发能力绑定R1/R2并重验查询回滚。Windows/Intel/生产及真实付费模型未运行。没有创建Review ZIP或自行合并main。

所有测试仅使用本脚本新建随机回环容器、tmpfs/临时TDB及随机隔离数据库；认证随机值只由当前进程环境注入并对输出遮蔽，不读取历史runtime、realm、卷或凭证。每次finally删除且只删除本次名字的容器/临时数据库，真实清理命令与结果在JSON中。

最终整solution只读format检查：exit2，唯一共享问题为backend/tests/OntologyPlatform.G2ContractTests/WireContractTests.cs行159的5项WHITESPACE。PUB owned路径与独立测试工程format exit0；未跨写。Master回执表示已在其树修正，待公共Host提交，此分支不把别树尚未消费的修复当作自己的通过证据。Release API及PublishingTests build均exit0、0warning/0error。


## 固定源码最终回执

- SourceSha：`930c2239b2df9065be75b79cf576e803d965c86d`（已push）。最终证据仅追加文档，不改变此源码。
- 命令：`python3 scripts/acceptance/release-faults.py --label committed-source-46`；`committed-source-46.json`实际记录workingTreeChanges=false、sourceSha上述值、exitCode=0，46 tests / 46 passed / 0 failed / 0 skipped，测试执行约21秒；三容器及迁移Up/Down/故障/真实清理均在原输出中。
- 同源码`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`再次exit0，见committed-selftest.txt。
- API与PublishingTests Release构建0warnings/0errors；owned格式exit0。整solution共享WireContractTests格式问题仍以本树实际exit2记账，Master已接手修复。
- Owner停止在独立审查/集成关口。PublishingTests新csproj和私有lock已完成并移交Master。CI、HTTP/浏览器与能力绑定的新R1/R2总体G2验收不由这些本地用例代替；保留上述NOT_VERIFIED/NOT_RUN边界。
