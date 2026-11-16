# Web工程规则

继承根AGENTS。当前已有Next应用、页面及build/lint/typecheck/Vitest/Playwright入口；源码存在不等于本轮验收通过，实际结果按任务证据记录。

- Next.js App Router + React + TypeScript + Tailwind CSS4 + shadcn/ui/Base UI，自主Design System。保持Tailwindadmin风格彩色企业后台、高信息密度、中文、深浅主题、Shell、可复用组件和无障碍；不复制商业模板源码。
- ADR-001批准当前单消费者暂不建`packages/ui`。组件/Tokens在`src/components/ui`、`src/styles`维护；第二消费者或组件编译/版本/发布需求触发复审。是否修改由当前任务授权限定。
- Rhea仅待核实视觉参考，不新增Rhea依赖，不替代Tokens。禁止Ant Design/Fluent UI正式组件依赖。
- 路由/layout放`src/app`，业务切片在`src/features`；Monaco/Cytoscape明确客户端边界；SSR、权限、错误/空/加载、SSE重连取消均真实验收。TS2空格；重要组件、Hook、公共类型及复杂业务函数用中文JSDoc/TSDoc。
- 修改Next相关代码前首先读取安装版本`node_modules/next/dist/docs/`；由脚手架/next dev产生的管理区块仅在本文件维护，保留项目规则，审查差异；不伪造生成管理块。
- 不把浏览器凭证、源库或模型密钥写入NEXT_PUBLIC变量。OpenAPI生成客户端与手写适配分离，SDK按ADR-005先PoC后选择。

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `dist/docs/` before writing any code. Heed deprecation notices.

<!-- END:nextjs-agent-rules -->
