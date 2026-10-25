# Kiota TypeScript PoC

工具 Microsoft Kiota1.36.1 实际读取冻结 OpenAPI 生成 TypeScript源码；输出见 [kiota-generation.txt](kiota-generation.txt) 及 kiota-poc目录，生成成功。工具更新检查发生TLS EOF，不影响本地生成；未禁用TLS验证。生成器明确提示 TypeScript语言preview，schema未配置servers要求手动配置RequestAdapter源。

PoC产生导航构建器、模型序列化及SDK工厂，依赖 @microsoft/kiota-abstractions 和 JSON/Text/Form/Multipart序列化器等额外运行包；这些包没有加入产品清单。与当前仅me/resources/audit/csrf的同源BFF消费者相比，SSR显式Cookie、no-store、取消与统一401/403处理仍需适配层；增加预览运行依赖暂不具有维护优势。

按冻结合同采用OpenAPI生成类型+内置fetch，保持生成类型与手写适配分离；6项实际Vitest覆盖取消信号、同源凭证、no-store、401/403/503、网络错误、厂区编码与空响应拒绝。没有引入Hey API。本PoC未安装/运行Kiota TypeScript运行包，其类型编译、浏览器运行和性能比较均NOT_RUN，不能声明SDK完整通过。kiota-lock.json仅生成器描述hash证据，不是共享pnpm锁。
