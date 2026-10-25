# SEC OpenAPI 元数据审查修复

状态：PARTIAL，2026-10-25。Owner前置提交`bcd28efaac8223b793ffcaba0315dab4fc6608c7`。本增量仅修改SEC的PlatformEndpoints元数据与HttpSecurityTests；公共DTO、DocumentTransformer和Host调用均由Master单写提交后原样cherry-pick消费，没有从SEC跨写公共合同或共享注册。

Master前置：`9748102cd923288875931f7c6c0afc20267873af`（六DTO JsonRequired及Contracts.PlatformProblem）、`a955380`（session/health方案DocumentTransformer）、`5009ba7`（Host注册扩展及局部注释）。SEC不重复提交这些文件的修改；Master集成只需本次新增SEC修复提交。

## 修复及真实验证

- RED：实际Kestrel导出的GET /auth/login仅有默认200，冻结应为302/400；新测试exit2、1失败。原始脱敏输出见openapi-metadata-red.txt。
- endpoint metadata补齐login302/400、logout302/401/403、既有callback fallback400、live200/401、ready200/401/503，以及/me200/401/403/503；资源/审计保持冻结状态集。
- 所有错误元数据声明application/problem+json并引用Master的Contracts.PlatformProblem（SEC用PlatformError类型别名避免与原有结果工厂冲突）。登录、注销、框架认证callback、中间件顺序和实际结果创建逻辑均未改动，没有新增伪回调路由。
- RuntimeOpenApiDeclaresRedirectsAndCompleteErrors通过真实HTTP获取/openapi/v1.json，检查10条实际路由状态集、每个错误响应媒体类型/schema引用、六DTO及Problem的required字段（含可null但字段必须存在的审计范围）、session Cookie及health头安全方案。没有以静态配置检查替代文档生成。
- 完整C#源测试在独立随机端口PG18临时容器和正式Kestrel运行：exit0，总13、成功12、失败0、跳过1。唯一NOT_RUN为RealIssuerPush（按Master持久化检查并发边界未消费共享身份runtime）；既有真实PAR的11/11及五身份310项历史证据仍在real-stack.md，不把旧执行冒充本提交全13通过。完整脱敏命令/输出见openapi-security-suite.txt。测试只改自身随机会话/合成审计；容器已删除。

format whitespace --verify-no-changes与verify.ps1 -SelfTest均exit0，输出见openapi-metadata-format.txt、openapi-metadata-selftest.txt；git diff --check通过。

独立Review、Master统一栈重启后的真实导出与冻结JSON语义对照、同Head Linux完整13项CI仍待总集成；本提交不声明Wave2总PASS，不进入main或G2，不生成第二个ZIP。
