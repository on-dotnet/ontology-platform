# ADR-001：单Web消费者的Design System目录

状态：**ACCEPTED（用户G1-ENG-001专项授权）**；日期2026-10-23。实现范围仍只工程基线，UI产品实现NOT_RUN。

## 决定与理由

当前只有一个真实Web消费者，暂不建立根`packages/`或`packages/ui`。未来Design System在`apps/web/src/components/ui`和`src/styles`内实施，减少无消费者的独立编译、版本和发布成本。此决策只改变物理目录，不降低既有产品标准。

必须保留Tokens、深浅主题、统一Shell、中文、高信息密度、可复用组件、无障碍、明确迁移边界。技术为Next.js App Router + React/TypeScript + shadcn/ui + Base UI，Tailwindadmin风格彩色企业后台，自主开发，不复制商业模板源码。Rhea仅待核实视觉参考，不是依赖。

## 备选、后果与未来触发

备选立即建立`packages/ui`，可提供独立消费契约，但当前带来额外构建和依赖维护。选择应用内目录仍需限制业务依赖渗透、稳定Tokens/API、主题与可访问性测试；出现第二独立消费者或组件编译/版本/发布需求时复审提取。提取时保留导入兼容层、迁移调用方并运行主题/交互回归，不能复制形成两套设计体系。

## 验证

本任务静态检查workspace只含apps/web、无共享包/产品源码。组件、主题、Shell和浏览器验收均NOT_RUN，归G1-FE等后续授权；文档不能证明UI完成。
