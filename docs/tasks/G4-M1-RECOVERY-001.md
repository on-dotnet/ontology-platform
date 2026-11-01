# G4-M1-RECOVERY-001

状态 BLOCKED_WITH_WITNESS，授权内恢复/验收/清理已完成，待唯一V3与独立重开回执。用户最新正式批准见 ../evidence/G4-M1-RECOVERY-001/authorization.md；完整输入合同原字节见同目录input/docs/01-EXECUTION-CONTRACT.md。Base=59edb405dfb4acf4d4a259cffdc3551bafa90d2c；protected origin/main=d1a61daffe844475b07705797e3ad325cc3f2945；任务分支codex/g4-m1-recovery-001。恢复原M1，不合main、不改G3/G6、不进入M2。

DAG：R0基线/来源/资源/独立Review→R1/R2精确ARM64受控取证→R3逐镜像非作者许可裁决→R4限长安全修复/最短PG-TLS-只读/OIDC/API→R5原49项真实矩阵/独立Review/提交绑定/资源回收/唯一V3重开。

Master独占 Host/G4/**、Connections必要公共服务/迁移、实验Compose/运行器/取证脚本、任务证据及必要测试锁。安全测试Worker独占 SecurityTests/G4RequestBodyLimitTests.cs，在独立托管树g4-m1-recovery-http-tests。无其他写者。Reviewer /root/recovery_reviewer只读，无owned_paths。公共Contracts/OpenAPI/生成链/Host由Master唯一写入；G3/G6为只读依赖。

当前精确改动：实际正文读取最多65537字节，>65536在JSON/handler之前拒绝413，身份/CSRF顺序保持。安全测试通过真实Kestrel固定长度/chunked/HTTP2，包含边界与多次短读及handler零调用；这不是PG/OIDC产品验收。

R0下载执行选择：stdlib有界官方OCI下载代替不透明daemon pull，仅实现同一已授权镜像取证能力，无安装工具/新依赖。index原字节→ARM64descriptor→manifest/config/layers hash+size逐级校验；HTTPS准确主机逐跳，未知主机暂停审核，CDN不携带registry token。持久最坏预算预留覆盖失败/重试，3GiB硬上限；任务归档/缓存总12GiB并检查宿主余量。Scout离线扫描任务OCI，不请求外部包仓库；实际容器门禁仍R3。

历史失败→前置回归：错误phase=dispatch退出2保留，用--help核实contract/runtime后纠正；SecurityTests锁缺已有Connections项目引用由Master最小更新，禁新包版本；缺Content-Length绕过用真实协议正反测试；镜像CDN新主机先审；任何昂贵失败先短复现。源码/格式→测试→非作者Review→提交→测试输入绑定→唯一V3→独立重开。

## 恢复阶段实际所有权与收尾状态

Master新增 owned_paths：experiments/g4-m1/**、scripts/acceptance/g4-m1-runtime.py、g4-m1-fault.mjs、任务证据、Connections/Application必要修复、已有Host/G4与最小项目引用lock元数据。Worker独立树另获批准：scripts/acceptance/g4-m1-http.mjs、g4-m1-browser.mjs，以及五个G4 UI角色文件和catalog.tsx/connections.test.ts；公共DTO/Host/迁移/OpenAPI始终Master单写。Reviewer只读，未共享写树。所有新增测试/故障操作均仅任务资源。

2026-11-01当前仍IN_PROGRESS/PARTIAL。正式授权边界已确认：C08没有第二个合法SourceConfig、R04禁止新增G3 Fuseki/RustFS栈，最终应交BLOCKED_WITH_WITNESS而非READY；但仍继续其它范围内验收/回收/唯一V3。详细实际失败、修复及独立审查见recovery-progress.md及runtime-evidence。未完成最终交付/测试输入绑定前不将此页视作回执。

U06精确补充Master owned_path：apps/web/src/features/platform/workspace.tsx，仅section=connections的四处环境文案条件；其它模块fallback与状态/权限/导航不改，已非作者审准。
