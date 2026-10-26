# PRE-G3-CLEANUP-FIX-002 Master交接（2026-10-27完成收口）

停在本轮整改复审，不启动G3、G3 Plan或业务功能。新Master先fetch真实origin/main，不把文档中旧SHA当未来固定基线。Base de2c020；工具独立分支0a920f4→357d99a→ad2b70c由Master直接FF，公共整合7336512→b9322e5通过同Head CI40355496041后进入main，才实际Apply；最终Head/最终main同HeadCI/唯一ZIP以实际manifest及外部delivery-receipt为准。

266唯一资源实际回收；284次变更命令尝试、568条before/command/exit0/after，含原18history瞬时删除后修复重试，不重复计数。实际10WT/11local/13remote/2旧停止容器/24合成卷/13重复Fuseki镜像/18旧history已回收，175 cache逻辑2,530,247,461 bytes。实际After local15/remote15/WT6；Docker shutdown后0containers/24vol/11images/1新恢复history；13共享cache约500.1MB未prune。精确原SHA/tip/ID、全部元数据、归属链与逐项KEEP/解除条件见任务evidence，不依赖历史聊天可见性。

6棵保留树是main、当前Master、g2-master及g2-query/security/sem；前两者当前集成/复审，g2-master实际三组私有runtime/PFX，后三者真实非等价补丁；12非祖先原refs保留（其中9组cherry全等价但tip不满足本轮祖先删除合同，另3组有+patch），不-D/不强推。保持独立托管Worktree并行，Master唯一main集成；不为数量改回共享main写开发。g2-ai目录在Apply之前外部消失，31操作撤回、不计本Master回收；初始bridge→preApply ID外部漂移原因NOT_VERIFIED，严格Apply/正常shutdown期间三个默认网络ID相同。

保留g2-ef979bd04cc0组8数据卷为明确选定可复用G2合成开发环境；两组712190660deb/b59e68191ca0因实际私有runtime/realm/PFX继续保护。恢复入口：保留的g2-master树，已验收scripts/acceptance/wave2-runtime.py run(existing runtime,full,g2,Release)，本轮复现包装见任务reuse-probe-entry.py。原私有值由可信运行器内存消费，禁止复制到源码/ZIP，不重新prepare/bootstrap覆盖旧环境。本轮清理前及初次Apply后的T1四项PG/Jena/RustFS/Keycloak健康全部通过；随后只SIGINT自己验证过的launcher，exit0，9临时容器/会话网络自动退出，数据卷保留。之后T3仅核保留集/元数据，未再次启动AppHost。其它平台和G2业务/E2E没有借此宣布通过。

默认inspect-resources只读；cleanup-resources默认DryRun，显式Apply要求fresh精确ID/版本、提交归属证据、main/URL/PR/边界/过期与指纹。过期计划只能重新盘点/审核，不能覆盖改tip；任何失败记日志停止后续，不扩大到force/prune。POSIX nofollow缓存删除不支持的平台明确REFUSED。存在安全候选但0删除=FAIL。永久DoD已更新。

C4独立全部reachable history/task refs扫描289commit/2235blob/46,825,908bytes，6原生成表达式/合成fixture命中全部not_actionable（高置信度），zero omissions；本地Codex辅助refs不等同公开。有限模式、语义隐私/混淆/未获取对象未验证，不改Git历史。如未来发现真实秘密，先报告轮换/历史处置建议，单独批准再处理。

最终V2构包器沿用已验收合同，ZIP不入Git，旧有效包直到新包独立重开后按精确hash回收；旧唯一metadata/收据已归档，原ZIP bytes重现不保证。最终运行CI/ZIP hash/旧包删除是提交后事实，由实际交付回执补充，避免自引用提交。交付PRE_G3_CLEANUP_FIX_READY_FOR_REVIEW后停等复审。

保留本地/远端各15 refs的完整构成：main + 当前FIX002任务枝 + codex/G2-THIN-SLICE-001-master（46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，为main祖先但仍附着私有恢复树）+ 12非祖先原refs。保护G2 Master的这一祖先ref单独保留，不归入12非祖先组。

关键后验教训：BuildKit0.34单Ref inspect可能留下零计数键，导致rm仅内存deleted；原532即时成功不能当18持久完成。e40修复改offset严格身份/指纹+后端版本/代际+精确DB无记录，40回归/15+9独立专项和同HeadCI40365150329成功后仅原18重验。18强诊断通过，再自然VM0→1/bridge48a→212a仍仅1history，持久未回现。原回现纠正证据不改，不能只看CLI0或listabsence。没有全局重启、配置修改、新依赖或RPC竞态。

修复e40提交后再扫描290commit/2278blob/48,032,661bytes，原6命中集合相同、unscanned0；仍是有限模式及人工triage，不扩大语义隐私保证。
