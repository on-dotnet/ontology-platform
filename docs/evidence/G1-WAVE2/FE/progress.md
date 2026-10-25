# G1-FE-001 开发进度

状态：PARTIAL / DRAFT，真实 OIDC 浏览器两项已运行通过，等待独立审查与 Master 最终集成验收。基线：87eb51a77bffe7468164a0e418bbbd2e101d95bc。树：/Users/chasen/.codex/worktrees/g1-wave2-fe/ontology-platform；分支 codex/G1-FE-001。

已读取根/目录 AGENTS、PLANS、当前授权、总/FE任务卡、冻结合同/OpenAPI、bootstrap冻结决策、授权V2第0/1/4/7/8/9/10节。执行前git clean且fetch成功。仅FE owned_paths写入。

## 首个里程碑（2026-10-25）

真实Next16.4.3 App Router，SSR显式Cookie/no-store访问固定可信BFF，401重定向；公开signed-out；资源/审计/授权三个视图；内置fetch适配+OpenAPI类型生成器；BaseUI焦点弹层；自研深浅Tokens和响应式Shell；同源CSRF后隐藏字段原生POST/logout。

实测Node24.22.1，隔离pnpm11.28.8。安装解析504包/添加382包；最终exit1：pnpm默认禁止unrs-resolver@1.12.2安装脚本，未擅自允许。后续Next生产编译可用，原生绑定已由可选包恢复。根锁未写入。

已安装Next官方docs/index.md、installation.md、cookies.md、css.md已读取；包自带AGENTS管理区块复制保留在apps/web/AGENTS.md。

测试先行：client.test.ts先运行exit1，缺少./client（RED），实现后Vitest 1文件6项全部PASS。typecheck exit0。build exit0，Next真实编译，/动态、/signed-out静态。lint exit2：typescript-eslint8.72.0明确拒绝TS7，已向Master提出官方TS6精确版最小修订。该失败保留，不声明里程碑PASS。

尚未运行：真实Keycloak/OIDC闭环、Playwright与截图、Kiota真实PoC（Master已提供工具，下一步执行）、CI、专项独立Review。总状态PARTIAL。

## 第二里程碑（2026-10-25）

PARTIAL / DRAFT，待独立Review与真实OIDC联调；前里程碑Head=59283841cb7a7c2226b4935ef111d03261d0ff08。恢复时已有未提交UI修复，本轮延续，不回退其他Owner。开工fetch确认origin/main=e930935749bcb88d51abb94db4a41695bbbe6717；无根配置/锁/CI修改。

本轮实际 lint=0、typecheck=0、Vitest6/6=0、Next16.4.3生产build=0；Edge4/4=0，覆盖1280/1920/390布局、Dialog键盘焦点恢复、深浅主题持久化、授权范围与搜索空状态、加载/403/网络错误/空集合/401、审计拒绝及signed-out。移动表格横溢根因为滚动容器的定位上下文，已有.table-scroll position:relative修复在4项复验中通过。截图只来自合成夹具，见screenshots目录，不能冒充真实OIDC成功。截图已关闭动画后逐张核对关键深色/移动页面，保证没有中途导航遮挡。

依赖官方版本/许可/弃用风险及npm audit见dependencies.md；安装仍exit1的脚本禁用策略交Master统一根allowBuilds处理，不批准postinstall。Kiota真实生成PoC及选择理由见kiota-comparison.md。

真实Keycloak匿名跳转/成功登录/资源/角色拒绝/跨厂区/注销、HttpOnly会话及双实例等完整SEC+FE联调 NOT_RUN，等待Master提供本轮新隔离Keycloak/API。已保留独立playwright.oidc.config.ts与2项真实suite，不以UI夹具替代。远程CI、Linux/Windows/Intel Mac本轮NOT_VERIFIED/NOT_RUN，独立Review待Master安排。本阶段不打ZIP、不改main、不进入G2。

SelfTest最终exit0：静态检查、8项检查器正反例、Doctor/结构化语法/环境状态组和35项审查包正反例通过。首次因保存的Next输出尾随空白而exit1，规范证据文本后复验。SelfTest旧正例仅stub dotnet，未stub pnpm，新Web目标导致该隔离正例实际运行pnpm并自动恢复到用户默认store，还产生本树未跟踪根锁；已移入apps/web/artifacts保留，最终根锁不提交。此公共脚本隔离缺口已提议Master修复，不跨改。完整输出见selftest.txt，包含预期负例FAIL，不将其误报为本轮最终失败。

## 独立Review移动导航Minor修复（2026-10-25）

Reviewer发现850px以下关闭侧栏仅transform屏外，隐藏菜单仍可Tab/读屏访问。已先添加390px真实键盘负例，修复前明确失败（mobile-nav-red.txt）：skip-link后第二次Tab未聚焦打开导航按钮。实现matchMedia+useSyncExternalStore响应断点，仅移动关闭态aside inert，桌面可用；服务端保守禁用到水合，导航触发器有aria-controls/expanded。窗口390→1280→390及打开/选择后关闭均由Edge真实交互与原生AX树检查；未添加权限业务逻辑。

首轮测试用Playwright角色选择器推断读屏隐藏，发现该选择器不排除inert节点（mobile-nav-ui-selector-failure.txt）；Tab行为当时已通过，改用Edge原生Accessibility.getFullAXTree检查浏览器真正暴露的无障碍节点后，全部UI5/5通过。build/lint/typecheck各exit0，客户端测试仍6/6。原负例保留，未删测试、未改共享配置。真实OIDC另记，不把此UI夹具算作身份闭环。

本次SelfTest最终exit0/审查包35正反例通过，使用仅子进程有效的pnpm11.28.8 wrapper关闭自动安装。旧native正例在临时树没有node_modules，真实lint报command not found但其dotnet位置断言仍给PASS；该既有测试夹具缺口继续交Master，不将其当产品验证。产品lint/类型/构建/6单测/5UI已在真实FE树分别执行通过，详见mobile-nav-*.txt。

## 真实 OIDC 浏览器收尾（2026-10-25）

本轮在 Master 准备的隔离 Keycloak、正式 .NET/YARP BFF、PostgreSQL 与 Next 统一栈执行真实浏览器联调。`oidc-browser.txt` 为原始安全 reporter 输出，exit0、2/2：viewer 匿名跳转 Keycloak、登录回调、HttpOnly/Lax 会话与浏览器存储边界、同厂资源200且仅site-a、跨厂site-b403、审计拒绝、原生表单安全退出及退出后me401；无角色身份登录后资源403并退出后me401。身份与业务数据为本轮合成开发数据；认证/授权/数据库/代理链为真实运行，区别于此前15410 UI身份夹具。

首次真实运行 `oidc-browser-initial.txt` exit1：旧 `getByText(site-a).first()` 命中隐藏的OPTION而非资源单元格；后改为资源API200/数据作用域断言与可见cell断言，保留原失败。`oidc-setup-shape.txt` 保留首次运行时身份结构不符的安全失败，不输出异常细节或私有配置。最终两项均到达logged-out-401，截图 `screenshots/oidc-viewer.png` 为登录后真实资源页；已逐图查看，只含合成开发身份、资源与审计/Trace关联ID，不含认证输入、URL查询、Cookie或Token。

`run-oidc-tests.mjs` 只在内存解析 Master 指定本轮私有runtime/realm并注入子进程，禁止打印或提交这些文件。专用safe reporter只输出固定测试ID/阶段/状态，原始stderr丢弃，trace/HAR/视频/失败截图关闭，框架异常详情在自动产物前清除；runner发现error-context、trace压缩包、视频或HAR时删除产物并失败。`oidc-privacy-probe.txt` 为无需身份/网络的合成失败负探针，预期exit1、两项失败而只保留安全状态，无敏感产物；该负例不计产品失败也不代替真实登录测试。

本次收尾复跑 lint/typecheck 各exit0，Vitest仍1文件6/6，见 `oidc-final-*.txt`；此前OIDC改动初验见 `oidc-lint.txt`、`oidc-typecheck.txt`、`oidc-test.txt`。UI夹具最新5/5及生产build在移动导航里程碑aaf8195验证；本次未启动Next或重跑统一栈。SelfTest历史输出与其中已识别的pnpm夹具缺口保持原样，本次收尾NOT_RUN；公共脚本修复与最终SelfTest由Master记录，不能用FE旧输出替代Master当前头验证。双实例/重放/审计持久化/遥测最终结论依赖SEC与Master的实际证据，远程CI同Head NOT_VERIFIED，Windows/Intel Mac NOT_RUN。专项独立Review及Master最终统一栈复跑待执行，总状态仍PARTIAL / DRAFT；不进入main、不另造ZIP、不进入G2。
