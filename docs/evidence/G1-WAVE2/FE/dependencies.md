# FE 依赖与供应链记录

2026-10-25，第二里程碑。批准范围保持 Next16.4.3、React/ReactDOM19.3.1、Base UI1.9.0、Tailwind/PostCSS4.3.3、Vitest5.0.5、Playwright1.64.1，类型包为 @types/react19.3.0、@types/react-dom19.3.0、@types/node24.19.2；未新增组件、图标库或SDK运行依赖。

Master 明确批准最小兼容修订 TypeScript7.0.2→6.0.3、ESLint10.13.0→9.39.5。官方 npm 元数据见 [peer-metadata.json](peer-metadata.json)：TypeScript 为 Apache-2.0；ESLint、eslint-config-next 和 typescript-eslint 为 MIT。typescript-eslint8.72.0 支持 >=4.8.4 <6.1.0，TS7越界。官方 ESLint9.39.5 已标记不再支持，保留此维护风险交 Master/Reviewer，不擅自升级或改变批准版本。

使用 Node24.22.1、项目隔离 pnpm11.28.8。命令 install --lockfile-dir .tools/fe-lock --store-dir .tools/pnpm-store --ignore-scripts 恢复493包（+56/-47），退出1：ERR_PNPM_IGNORED_BUILDS unrs-resolver1.12.2。脚本未执行、未批准 postinstall。根工作区显式 allowBuilds unrs-resolver:false 与正式根锁由 Master 单写。本树根锁未改。后续脚本 --config.verifyDepsBeforeRun=false 仅避免重复安装检查，实际 lint/typecheck/test/build 已执行，不能把安装exit1写成PASS。

隔离锁 pnpm audit --json exit0，493包已知漏洞各级均0，见 [audit.txt](audit.txt)。此结果是 npm registry已知漏洞查询，不代表完整传递许可、SBOM、ECDSA签名或恶意包证明；完整传递许可/签名审计 NOT_VERIFIED。

Playwright 未启用 HAR/trace/视频/自动失败截图；保留截图仅来自明确合成UI夹具，没有登录页或真实测试密码。产品浏览器存储仅 ontology-theme，不持有身份Token；SSR Cookie只转发配置的可信BFF，浏览器相对路径请求；有限源码扫描无硬编码密码或NEXT_PUBLIC秘密，不能冒充完整秘密扫描。
