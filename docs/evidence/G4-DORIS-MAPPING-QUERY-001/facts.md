# 固定事实、原件与检查索引

TaskId=G4-DORIS-MAPPING-QUERY-001，RunId=merge-spec-01。源码均固定于606ca2d2c61964e6498dd72d5e9ad960d3593bf7；恢复用git show <SHA>:<path>。本文件是A–F的事实/审查索引，不是第二规格或状态源。

## 原件身份

主树包外 `artifacts/reviews/G4-DORIS-MAPPING-QUERY-001/main-update-receipt.json` 包含归档/受保护文件前后hash、祖先、精确二进制patch比较、普通push实际握手及后置回读。阶段A merge与push实际exit0，远端main/source均606ca；受限ls-remote DNS和首次merge ORIG_HEAD.lock拒绝为exit128，授权环境重试成功，失败不抹除。

M5原树 `/Users/chasen/.codex/worktrees/g4-m5-integration-001/ontology-platform/artifacts/reviews/`：工程ZIP606ca为1,446,527 bytes/SHA256 d529083b441c3e098b5525963710d5668d4391eb5a5c655d0f03f7423c480915；非作者entry-fix-02-non-author-reopen.json SHA256 c6eb83f73b7802ac25b6b3695978f839652d8dea5c133346d209cc1cd5384bb2；machine-receipt完整身份见包外回执。历史产品ZIP8cb48c1f420cb5f3461e2dcff1fc747b5d6e301cdc73248e796179d72b128eea、f620工程ZIP5c3228ebe28d182266edb2d7f78ae5b8cf9534c6592bc6c567226d16356abfc1原字节未变。复用原非作者同包检查，不重开/重构包。

M2固定参考：docs/evidence/G4-M2-DORIS-01/delivery-status.md:7–17、validation.json、product-proof-index.json；docs/evidence/G4-M2-DORIS-01/final-policy/resourceCloseout.json为准确KEEP/历史回收原件。只有元数据/TLS/生命周期范围，不代表新行读取通过。M3/M4唯一合同仍为各目录contract-admission-request.md及任务卡，按Base恢复，不改其历史批准字节。

## 只读源调查

只读Explorer `/root/doris_source_facts`、`/root/pg_coupling_facts`核对真实源码后返回，Master转录到A–F准确路径/行号。关键见证：IMappingSourceValidator:9/21、MappingValidationService:190/199/313/743/872/1157，QueryBindingReader:71/135/184/267/326，G4MappingRules:101，G4QueryExecution:674，G4SourceEvidenceService:28/39，G4Composition:52/72/83。PG平台准入锁和平台提交事务不因外源Doris改动。

## 本轮资源观测（2026-11-17）

只读命令：docker ps --format ID/Names/Status；docker info --format MemTotal/NCPU；docker inspect仅Id/Name/HostConfig.Memory/NanoCpus；docker image inspect仅Id/Architecture/RepoDigests；df -k。没有Env、日志或秘密输出，服务操作0。默认沙箱Docker socket拒绝，未把其格式化输出0/0当容量；获准只读重试后真实VM=16787419136bytes/12CPU。

14个运行容器，M4/M5各7；每栈配额6GiB/4.5CPU（不是实际RSS），总12GiB/9CPU。下面短ID在本次docker ps中唯一，精确完整ID只用于引用，不是处置许可：

| 栈 | 服务/完整容器ID |
|---|---|
| M5 | api-secondary cd563c910aa96e9c6eaabf32475d5bfe2ec56e6a9f754ca48b4287de1b8e653b；api 22837b2b2702a851ca4553b6d0ff0ce09ac3d5f65f67b911f39598cbf1f804d8；rustfs 5e0f45ecaf9e2f227c4290891eeb26e577bfeaaaa8d5a5b0be7a15458656a49a |
| M5 | keycloak 4a5dacfa92d7d9a119267365a65ab5037b98b4bb2292b9e47199b0bb14ab50b4；fuseki 0edb069b759a2521cb56250f1db0227bd3cc8c81ad06210a1d8a7c7b52866534；pg-source 19f76154598ac31e4a075175aadafc0a2f22591281ecf5db0704fd65e26a502b；platform-pg b71ef14e5e484253c0b435332c4480fc071268f634c0b049d5d4aff57c383912 |
| M4 | api ed281bc42b432a4e20817b00dfbc7b480271f36368a24370414a6e6fb5b62dca；api-secondary fc53d2b9b9fc7d67344a79e1abcf107b32b832d762713979a3584da8d9d1c7f5；rustfs 47686c56bb164ed6577349fe47b20968f83630032d6c3ebd8ed55586a8846bbd |
| M4 | keycloak 61791a2303a2945b9947824de91e763d22be03b538d1c0b76ee3ce44027a835f；fuseki f1a5f1cb913037f7716a3599bc19c1ed9eed11aa6db79b7f1a57c8dbe1c3943d；pg-source c1bbd53e0b335a12c5e50bc860a58e6d3cb01de7d81a354ee87696dd0a941c81；platform-pg d267220f4227b7c92f5d2e37e7e85a4587644488157c10e5f95586613bd08952 |

两Doris镜像Id、RepoDigest与A–F锁定manifest一致，Architecture=arm64；只证明本地引用存在和架构，不是再次逐层校验或启动测试。当前宿主RSS、其他磁盘占用闭包、端口可用、启动前BE参数 NOT_VERIFIED。M2历史宿主峰值约1.34GiB，不冒充当前峰值。未来必须创建前按同消费者即时输入核预算。

## 公开资料边界

读取官方4.x事务页（https://doris.apache.org/docs/4.x/data-operate/transaction/）仅支持不能移植PG可重复读的设计警示，未作为4.0.8实测证据。官方4.0.8 SessionVariable页面目标模式未找到，SelectCommand页面读取失败；不据此造结论。table-design/data-model/overview链接跳转概览，不用概览证明表模型。未保存公开网页全集，无制品下载。4.0.8 UNIQUE/MOW/精确类型/取消均待最短获批真实验证。

## 审查及检查

非作者 `/root/spec_review` 初审发现并推动修正：组织列缺失、Mapping强制时间与HALF_OPEN_OVERLAP遗漏、NULL关系夹具顺序、Doris native类型分类、宿主localhost拓扑、UI精确路径。作者另修正六态名称、旧目录算法与DUPLICATE假主键风险；候选改UNIQUE/MOW并待实测。第二轮复核还发现无单位decimal无法通过现评估，已补unit_code=K和现注册单位/G3证据，不扩单位合同；最终非作者原话：“最终增量复核通过，可交集中裁决，未发现剩余规格阻断。”已按其非阻断建议修正ConvertValue方法名。

轻量检查：Python标准库五路径白名单、UTF-8无BOM/LF/末尾换行、25条相对链接存在、A–F/AC01–11覆盖及git diff --check实际exit0；既有Assert-ReviewPath/Assert-ReviewContent有限扫描五份文档exit0。终稿再核相同检查并保存逐命令输出/真实exit到本任务ignored artifacts/reviews/document-validation.json及commands.json；正式test-review-evidence.ps1仅验文档证据schema，不构包或认证产品。有限扫描不保证发现所有秘密。产品、CI、prepare/restore/服务及ZIP全部NOT_RUN。
