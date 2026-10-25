# SEC 独立审查修复增量 · PARTIAL

前置提交：`1f2d2056555ecbed12aad3dcd369c9e7a4d2d023`。只改SEC白名单，不改公共合同/锁/迁移/solution/AppHost，不自行合main。

- Reviewer Important：YARP2.3默认框架日志记录完整RequestUri，query可能含敏感材料。新增真实Kestrel代理请求与捕获全部日志正文的负例，RED为1失败/7成功/1PG NOT_RUN；加 `Yarp.ReverseProxy` 日志类别None后复验。保留自定义路由模板/状态/trace/audit日志。测试不输出捕获正文，只检查固定合成标记。
- Master复现：`Path.open`不接受opener，bootstrap在新realm创建后写私有文件会TypeError。新增本地真实HTTP fixture与临时私有文件正例，RED准确TypeError；改内置`open(output, ...)`，GREEN验证0600、五个身份及秘密不在stdout。该fixture只证明helper HTTP/文件成功，不冒充真实OIDC。
- 新增真实OIDC协议驱动`infra/security/verify-oidc.py`及2项目标地址/form边界测试；统一栈尚未运行，真实OIDC验收NOT_RUN。只打印安全检查结果，浏览器与PG重启另计。

真实命令：Python `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/security -p 'test_*.py'` 6项，exit0；C# `dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore` 8项成功/1项PG NOT_RUN，exit0，见yarp-log-green.txt；`dotnet format <同测试工程> --no-restore --include <SEC两文件>` exit0；SelfTest exit0，见review-fixes-selftest.txt。原始安全输出保存在同目录；PG未注入依旧NOT_RUN，CI=NOT_VERIFIED。最新milestone2-selftest.txt更新覆盖文件数240，仍exit0。
