# G2-PUB-001 实施证据

状态：DRAFT / PARTIAL。BaseSha=457911442aaa12f3ba170ee43c70343b64581f39。当前仅模块模型/Factory，审批/制品/图/事务/Outbox与真实故障矩阵尚待实施，不能声称 S2 通过。

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
