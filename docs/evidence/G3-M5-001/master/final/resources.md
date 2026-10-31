# 本任务资源实际收尾

8个`g3-m5-7d512550ef69-{alloy,fuseki,grafana,loki,postgres,prometheus,rustfs,tempo}-data`卷在独立Reviewer批准后真实Apply，validated8/completed8。准确context=desktop-linux、Engine=7a8785bb-6b6e-4ae4-8065-996f4bf83016、Server29.9.2、metadata/fingerprint/0refs/24hTTL/已提交CLOSED Synthetic证明均重验；before/准确command/exit/after在`volume-apply.jsonl`，强API精确不存在在`volume-postconditions.json`。未以rm0或列表缺席代替删除证明，未重删。物理回收字节UNKNOWN。

补充后验检查首次猜错错误文本次序而产生FAIL原报告，执行器当时已完成严格验证；修正后只重读8次inspect，确认每次exit1、stdout[]、准确name的no such volume。原错误报告保留。旧G2准确八卷metadata前后一致，保留一套日常开发数据；未额外启动整套旧环境，旧整栈health NOT_RUN。共享canonical Fuseki镜像已真实复用，没有本轮新image/history构建，不清理旧镜像/history。

原生托管树归档：Web40e2已转archived_worktree，recoverable attachment `01a19071-ec27-7a83-8eed-7e8535bbe01a`。ignored的41个SEM/Web过程输出先复制到Master `artifacts/g3-m5/worker-recovery`，散列索引已提交；构建输出/node_modules/pycache可由冻结依赖重建，工具symlink目标未删除。21→20棵实际树，精确before/after汇总另附。E0树g3-m5-e0和SEM树320c各收到原生`Another active task still uses this worktree.`拒绝，各自KEEP，不绕过，不把这两棵宣称已删除；解除条件为原生活跃task guard消失且独有证据仍可恢复。

当前Master b389树KEEP至ChatGPT复审与最终证据移交；其准确私有runtime/PFX/realm在`.tools/security/g3-m5-7d512550ef69`，不读取/打包认证材料，保留仅为恢复审查。原126成员reader及已批工具/共享pnpm store保留至G3复审关闭；解除条件为正式包/回执确认可恢复且不再需当前身份场景。worker codex/g3-m5-e0 / sem分支仍绑定活跃树；web / web-visual refs保留其已推送可恢复审查tip直到外部关口关闭，不通过只允许卷的M5执行器绕过删Git。其他旧任务树/refs/缓存均不属于本任务回收白名单。

Docker Desktop由本任务启动既有应用，后续保留给日常开发，不全局stop/restart。所有本任务AppHost/短fixture均在finally关闭；任务级monitor仅精确PID6932在正式包独立重开后SIGTERM，终态在包外host closure回执。没有全局killall/prune、跨项目清理、改DB或重写Git历史。资源工具60个fixture测试通过与上方真实删除分别列证。
