# G1-FE-001 开发进度

状态：PARTIAL / DRAFT，等待独立审查及真实 SEC/FE 联调。基线：87eb51a77bffe7468164a0e418bbbd2e101d95bc。树：/Users/chasen/.codex/worktrees/g1-wave2-fe/ontology-platform；分支 codex/G1-FE-001。

已读取根/目录 AGENTS、PLANS、当前授权、总/FE任务卡、冻结合同/OpenAPI、bootstrap冻结决策、授权V2第0/1/4/7/8/9/10节。执行前git clean且fetch成功。仅FE owned_paths写入。

## 首个里程碑（2026-10-25）

真实Next16.4.3 App Router，SSR显式Cookie/no-store访问固定可信BFF，401重定向；公开signed-out；资源/审计/授权三个视图；内置fetch适配+OpenAPI类型生成器；BaseUI焦点弹层；自研深浅Tokens和响应式Shell；同源CSRF后隐藏字段原生POST/logout。

实测Node24.22.1，隔离pnpm11.28.8。安装解析504包/添加382包；最终exit1：pnpm默认禁止unrs-resolver@1.12.2安装脚本，未擅自允许。后续Next生产编译可用，原生绑定已由可选包恢复。根锁未写入。

已安装Next官方docs/index.md、installation.md、cookies.md、css.md已读取；包自带AGENTS管理区块复制保留在apps/web/AGENTS.md。

测试先行：client.test.ts先运行exit1，缺少./client（RED），实现后Vitest 1文件6项全部PASS。typecheck exit0。build exit0，Next真实编译，/动态、/signed-out静态。lint exit2：typescript-eslint8.72.0明确拒绝TS7，已向Master提出官方TS6精确版最小修订。该失败保留，不声明里程碑PASS。

尚未运行：真实Keycloak/OIDC闭环、Playwright与截图、Kiota真实PoC（Master已提供工具，下一步执行）、CI、专项独立Review。总状态PARTIAL。
