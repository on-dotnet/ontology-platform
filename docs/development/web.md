# Web 开发与验收

Next16.4.3 App Router + React19.3.1 + Tailwind4.3.3 + Base UI1.9.0，自研深浅Design Tokens和中文响应式平台Shell。当前范围仅平台资源、访问审计与授权范围，不预建本体业务模块。菜单调用真实同源BFF，未实现功能不显示假成功按钮。

## 配置与入口

产品统一从 .NET/YARP BFF源访问。Next内部监听127.0.0.1:15300；PLATFORM_API_ORIGIN是仅服务端可见的可信BFF源，默认http://localhost:15100，不从请求Host派生。生产非回环要求HTTPS，不能使用NEXT_PUBLIC传递秘密。SSR显式Cookie/no-store请求me；401跳转/auth/login?returnUrl=/；资源403呈现无权、401会话结束、网络错误独立呈现。注销先同源获取CSRF，再隐藏字段原生form POST /auth/logout；不使用fetch跟随跨源OIDC注销。

## 项目隔离工具

使用已批准Node24.22.1与.tools/pnpm/package/bin/pnpm.cjs的11.28.8；不得使用机器全局pnpm12改写版本。依赖恢复与正式根锁由Master统一管理，禁止批准unrs-resolver postinstall。FE隔离解析使用 --lockfile-dir .tools/fe-lock --store-dir .tools/pnpm-store。

从仓库根运行：

```sh
node .tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false --filter @ontology-platform/web lint
node .tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false --filter @ontology-platform/web typecheck
node .tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false --filter @ontology-platform/web test
node .tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false --filter @ontology-platform/web build
node .tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false --filter @ontology-platform/web test:e2e
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
```

UI Playwright使用本机已安装Edge，独立127.0.0.1:15310 Next和15410合成身份夹具，仅验证呈现与交互，不代表身份验收。4项覆盖1280/1920/390、键盘详情与焦点、主题持久化、无权/加载/空/网络与会话过期。截图写FE专项证据，测试产物只写apps/web/artifacts，避免提交依赖/构建缓存。

## 真实 OIDC 联调

Master准备本轮隔离Keycloak/API、BFF代理Next并将临时测试密码仅注入测试进程环境WAVE2_VIEWER_PASSWORD与WAVE2_NO_ROLE_PASSWORD。测试不得打印这些值，也不得读取旧项目凭证。默认BFF localhost:15100，可用PLATFORM_TEST_ORIGIN指定本轮源；当前suite预期隔离Keycloak localhost:18080。从apps/web运行：

```sh
node ../../.tools/pnpm/package/bin/pnpm.cjs --config.verifyDepsBeforeRun=false exec playwright test --config playwright.oidc.config.ts
```

真实suite验证匿名→Keycloak→认证后资源→跨厂403/审计无权→安全退出→me401，以及无角色身份403。HAR、trace、视频和自动失败截图全部关闭，防止认证材料进入产物；不要用UI合成夹具宣称这些流程通过。缺少隔离环境或临时身份时保持NOT_RUN，完整纵向验收还依赖Master/SEC双实例、审计及遥测证据。

## 客户端与证据

OpenAPI生成类型在src/lib/api/generated.ts，手写fetch适配在同目录client.ts；重新生成使用generate:types并审查差异。Kiota1.36.1真实生成PoC、依赖许可/兼容风险、测试输出及中文截图见[FE证据](../evidence/G1-WAVE2/FE/progress.md)。第三方签名/完整传递许可和真实联调未完成前总体PARTIAL，阶段ZIP由Master唯一生成。
