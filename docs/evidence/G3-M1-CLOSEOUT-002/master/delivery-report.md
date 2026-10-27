# G3-M1-CLOSEOUT-002 交付矩阵

状态：READY_FOR_REVIEW / PARTIAL（物理回收未验证、未运行平台保留；最终稳定Head CI/唯一V3 ZIP须核对提交后实际回执，不预填未来事实）。整合SelfTest exit0、ReviewPackage90/0及完整diff-check0已实测，整分支独立审查Spec/Quality PASS、C0/I0/M0，最后自然证据限定复核PASS，见whole-branch-independent-review.md。只本轮工程收口，不重做M1业务、不启动M2、不改历史Git或其它项目/生产。

## 实际结果

- PASS：正式构包器默认V3，V1/V2继续VerifyOnly；完整文本diff/二进制双侧blob、单份payload、Git恢复证据索引、实查同Head run+双job、ignored有限聚合、截图12/3MiB与10/15MiB门禁、原子partial及严格重开。90回归+真实PNG大夹具1项通过。最终53PNG/55256ignored夹具V3=2482853 bytes，V2=32803202 bytes，约92.4%缩小；原始历史证据和ZIP字节未改写。
- PASS：唯一canonical Fuseki入口，AppHost两处和g2-integration共同复用内容寻址context镜像；跨Worktree共享锁，首建后连续真实2次调用的image/history集合不变。最新AppHost实际9容器标签、非秘密任务/运行清单EXITED0，观察9准确容器ID和8卷；旧私有runtime未回写/复制。
- PASS：Mac真实Apply35项=16旧卷+8重复镜像+11history；70逐项before/after，全部严格absent后验。初次旧代际Apply被拒绝且0删除，无日志创建；保留失败记录，重新实际盘点、独立复审generation2计划后Apply成功。未绕过守卫、未restart/reset/prune/改DB。
- PASS：开工0容器/24卷/16image IDs/9history/3network；本轮canonical首建及旧可信健康探针新增2image/2history，实际preApply0/24/18/11/3；清理及最新健康探针退出后0/8/10/0/3。只保留ef979八卷、8固定依赖镜像、legacy恢复Jena与canonical镜像；所有默认网络保留。准确ID/引用/理由/解除条件在closed-resource-ownership.md。
- PASS：清理前后PG pg_isready0、Jena/RustFS/Keycloak三HTTP200，8/8健康探针；后次用最新canonical+标签实现，9容器自然正常退出，不把探针容器计历史回收。真实语义集成（PG/Jena/RustFS/发布故障/查询/MCP/MAF/native SSE）exit0，最新Release build0错/既有ASPIRE010警告。
- PASS：永久AGENTS/PLANS/授权/效率/构包/生命周期规则和自动化回归；独立审查发现2个P2均修复、限定复审通过；已修SEM EOF格式，保留历史失败文本，diff-check0。
- NOT_VERIFIED：Docker Engine卷逻辑用量preApply1.868GB→624MB，约1.244GB净减（显示值有舍入）；后次日常环境正常活动后619.3MB。镜像共享层总计仍5.747GB，不把8个503MB逐行相加；cache13项500.1MB未prune。APFS/VM sparse disk物理释放没有实测，不宣称物理回收。
- PASS：11history在Apply后逐Ref支持的强no-record诊断，再观察到实际自然bridge代际从e5a1d4…变为c71c286…；当前受审版本/单节点未变、核验期间代际稳定，11/11准确Ref再次强no-record且无回现。完整命令/退出/代际见history-natural-postverify.json及可复现入口；未主动restart/reset/upgrade/prune/改DB，不以时长或列表缺席判定。
- NOT_RUN：Windows/Intel/生产/新M1业务重做/新浏览器全量视觉验收；本轮未改Web业务，最终完整Web/backend由同Head CI执行。付费模型/新依赖/全局工具修改均未发生。

## 工程与交付冻结

清理前Head b241569a169f8312384200579b0e74ed6f821ee5、实际CI40483372730 engineering/governance-integration双job成功，原事实见preapply-same-head-ci.json；资源worker早期CI40483034113被后续同分支push取消，不记成功。最新最终Head的真实run/job及ZIP path/size/SHA以最终manifest和独立重开回执为准。

Master拥有公共规则/CI/脚本集成；PACKAGE独立树g3-m1-closeout-package，原commits0a873be+77b8ff0；RESOURCE独立树g3-m1-closeout-resources，原commits35c2da0+f2d8e7f；各自非作者Review见independent-tool-reviews.md，原树/任务分支当前为本轮复审恢复入口。旧6树/未集成refs/私有runtime/PFX和其它阶段原ZIP均不在本轮Docker删除范围；每个当前任务树在本轮复审后、集成与ignored归属核验后原生archive_worktree，不强删私有资料。Master当前树保留生成最终唯一包及审查恢复。

开始/结束和墙钟见efficiency-metrics.json及最终回执；实现/等待/环境/测试/CI/返工/封包活跃耗时UNKNOWN，不能从聊天推断工时。正式交付后输出G3_M1_CLOSEOUT_READY_FOR_REVIEW并停止等待ChatGPT复审。
