# ADR-003：Next与Aspire首期边界

状态：**ACCEPTED（首期路线获专项授权）**；日期2026-10-23。实际服务编排和发布兼容性NOT_VERIFIED。

## 决定与理由

Aspire研发编排优先采用官方通用JavaScript/pnpm资源方式；不默认依赖Experimental Next.js helper。生产Next使用独立standalone Node进程/镜像，经集成式.NET YARP/BFF入口。服务启动、端口、健康依赖和AppHost/ServiceDefaults实现全部归G1-INFRA-001，本任务不创建。

[Aspire官方JavaScript集成](https://aspire.dev/integrations/frameworks/javascript/)标注AddNextJsApp为Experimental；[Next standalone](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)说明SSR独立发布能力。本任务采纳路线，不把文档示例称为项目已实测。

## 备选、验证与触发

备选专用AddNextJsApp helper可自动处理Next默认值和容器产物，但受实验API升级影响。稳定性、SSR、开发/发布产物、代理SSE和取消、环境参数可见性必须在后续PoC验证。helper稳定或显著降低维护成本时复审，禁止全局掩盖实验警告。AppHost不是生产业务网关，ServiceDefaults不是业务Shared Kernel。
