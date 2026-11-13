# G4-M2-ORACLE-01｜Oracle 条件实施

唯一任务状态：**BLOCKED_SECURITY_ADMISSION**（2026-11-13）。A–F条件实施已获批准；当前停在数据库安全门禁，不是缺少实施授权。

- 目标：本机Oracle ARM64连接及只读目录切片；设计、裁决与执行记录见[A–F申请](../evidence/G4-M2-ORACLE-01/admission-request.md)。不进入M3/M4，不更新main，不制作ZIP。
- 授权：用户明确批准A–F及镜像展开13GiB，总磁盘峰值40GiB；按原件/安全→合同Review→工程消费者→真实验证顺序推进。历史P0边界与失败保留于原提交/索引。
- Base：`5113d0b9b233e307664c964ae9bf3c1d6b10adfb`，本轮fetch后origin/main相符；任务分支`codex/g4-m2-oracle-01`。最终Head随回执给出。
- 唯一托管树：`/Users/chasen/.codex/worktrees/g4-m2-oracle-01/ontology-platform`，operationId=`be289194-eb2d-493d-95f7-e7aaee6e5cd7`。TaskId=`G4-M2-ORACLE-01`，RunId=`IMPLEMENTATION-20261113-01`；P0原件继续由[metadata/index.json](../evidence/G4-M2-ORACLE-01/metadata/index.json)恢复。
- Owner：本会话Master唯一写者；非作者Reviewer=`/root/oracle_p0_review`。owned_paths为申请E表、本卡/申请/metadata及授权追加；最小工程接入补充`host_continuity.py`、`workflow_web_cache.py`及HostContinuity/WorkflowEnvironment/WorkflowM2Web三个定向测试。其余只读依赖；公共合同/锁仍Master单写。
- 已完成：11个批准新包共13,499,230bytes，长度/SHA512匹配；NuGet专用离线验签11包成功，在线撤销NOT_VERIFIED。基线隔离prepare/锁定restore成功，零网络下载；Oracle新包尚未加入锁/产品构建。复用既有不可变依赖，不复制私有runtime或凭据。
- 工程检查：宿主13、环境7、Web缓存14、Doris结构6、交付13，共53项定向测试通过。原失败及短诊断保留。AC/sleep0/displaysleep10；30秒7次心跳，确认睡眠0ms，锁屏/熄屏及整会话持续性NOT_VERIFIED。产品/真实Oracle/CI/Windows/x64均NOT_RUN。
- 阻断：官方十月CPU的CVE-2026-75803（TLS未认证，9.8）及CVE-2026-91568（CREATE SESSION/Oracle Net，7.7）范围覆盖23.26.3；当前digest无修复/不适用证明，未断言已实证可利用。READ和TLS不能排除。静态comps.xml仅有基础组件/七月构建时间，无法解除门禁；完整摘要和后续裁决见申请末尾。
- 资源：唯一用户镜像KEEP；11新包、已核验继承包及本树隔离缓存KEEP，供同树后续继续，关闭/引用复核后再回收。静态取证临时容器从未启动、无网络/挂载，已按准确ID删除并确认不存在；没有数据库服务或卷。两项未跟踪`.DS_Store`保留。
- 下一步：获得绑定当前digest的修复/不适用证明，或明确裁决修复版本重新准入/限定风险例外，再继续合同与产品门禁。既有A–F授权持续有效，不逐补丁重新询问。
- TDengine保持**WAIT_FOR_EXTERNAL_INPUT**，未恢复调查/开发、未改其树/分支/原件；M2未全部完成。
