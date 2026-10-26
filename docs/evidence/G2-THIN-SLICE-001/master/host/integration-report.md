# Master Host S1/S2 DRAFT集成证据

状态DRAFT/PARTIAL；尚未真实S1全链通过，不入main。Base6154ebb..本次提交，当前独立SEM/PUB/FE和整体验收另记。

真实Release全solution build exit0，保留既有ASPIRE010 1 warning，PUB更新后已无EF1003。最初并行MSBuild子节点MSB4166失败；单节点-m:1原样代码复跑exit0，未关共享构建服务器或系统配置。19/19共同wire回归、2/2真实运行OpenAPI+安全选项组合测试、SelfTest、精确Web lint/typecheck/Vitest9/build均exit0。Web尚G1代码，不冒称G2 UI。

OpenAPI原生Kestrel测试最初存在测试SDK interceptor未启用、StartAsync错误重载，明确是夹具编译失败且零测试不当red。修正后真实导出200，但SemanticDatum无互斥oneOf、ExecutionEvent无事件/版本literal，行为1/1失败（red3/red4）；接入唯一生成component后锁定Microsoft.OpenApi2.12.2将integer const1输出string1，首次green命名日志实际仍失败，保留。改为标准等价integer enum[1]并与生成Schema对齐，最后2/2零skip（含安全组合回归）。不升级依赖或手写第二套业务DTO；新g2-schemas.openapi.json为机器生成唯一Schema来源，g2-platform.openapi.json仍只bootstrap，真正产品20路径导出另存openapi-s1-s2-runtime.json，S3路径尚不存在。

G2资源复用同一AppHost：新私有卷前缀、新Realm八合成身份、原生OIDC/BFF两实例、Jena内存校验和TDB2正式dataset、RustFS及原LGTM。凭证仅本轮ignored private runtime。G1默认profile仍wave2原五身份与原版本维度；G2显式开关才增量资源，不修改历史卷。

第一次Fuseki COPY失败，.dockerignore只放行旧entrypoint；增加精确两配置文件白名单后同一批准JRE/Jena原digest build exit0。没有系统安装/新云服务。

真实Edge无头OIDC首次已取得HttpOnly/Lax会话及CSRF，初稿命令错误给long expectedRevision=null产生400，是验收夹具问题（live-s1-fixture-null-revision.json）。修正命令0后missingCSRF实际500（live-s1-host-di-red.json），查到薄端点依赖构造时Aspire localhost S3被数字回环适配器拒绝；Root组合仅将S3 endpoint host改固定127.0.0.1、port仍用Aspire引用，不降低适配器限制。并核对guard取IOptions安全对象而宿主只注册已验证singleton导致未绑定PublicOrigin；真实组合red断言AreSame失败，现G2Composition用Options.Create引用同一已验证singleton，2/2绿。完整环境已待重启复验，不能把局部绿代替真实登录写入PASS。

Governance writer/middleware47项通过限定独立审查C0/I0/M0（18877ae..d2567e1，源码a0e1ccc）；该47使用服务器固定principal+原生anti-forgery，不是OIDC会话。此处实际登录的独立证据严格另记。PUB源码930c223真实clean46项独立审查正在进行；仅DRAFT集成任务分支。所有未知/未跑完整G2/CI/Windows/Intel/真实模型仍保留。
