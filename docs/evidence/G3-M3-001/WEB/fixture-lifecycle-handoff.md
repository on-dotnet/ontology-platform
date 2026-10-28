# G3-M3 E0组件测试容器归属

状态：IMPLEMENTED / PARTIAL，待Master独立Review、集成及真实产品验收。独立树g3-m3-web，开发基线c5aa1b9daf58f92bdeac3eb102ef17611f56e9e7；未push、不改main。

## 实现

五个原入口semantic-roundtrip、release-faults、query-plan、mcp-agent、test-governance统一为成功docker run登记准确64hex ID，创建命令加入project、TaskId、唯一RunId及test-fixture标签。TaskId取PLATFORM_TASK_ID，否则DEVELOPMENT；RunId沿用每次secrets.token_hex生成的唯一name前缀。不能由调用者覆盖归属标签。创建失败或坏ID不授权按预期名字删除。

finally只对已登记ID作固定字段inspect，准确名称/项目/任务/运行/fixture全部匹配才执行docker container rm --force <ID>，随后准确ID再inspect；只接受exit1+空stdout+准确Error response from daemon: No such container: <ID>诊断，不把权限/CLI故障、错误ID缺失或rm0且对象仍在当成功。记录create/before/command/exit/after、真实UTC和rm耗时。失败保留对象、继续其它独立owned对象、最终进程/证据exit1；governance PASS延至实际清理通过后。其它镜像/业务命令/secret env语义保持。

## 实测与限制

- 初次回归真实执行五个入口的创建失败路径；首次测试隔离ROOT错误令两入口产生harness error，原日志保留。修正隔离后原代码五个入口均因名称碰撞仍rm而FAIL，保存entry-red。
- 新协议测试RED因helper尚未存在，保存protocol-red；最后12个tests PASS，包含五入口×成功/失败清理的真实main调用者路径及名称碰撞、foreign标签、权限/CLI异常、错ID诊断、坏创建ID、rm无效果和非0。测试只在外部Docker/HTTP/dotnet边界使用受控替身，不是产品PASS。
- 唯一真实Docker命令为只读container inspect固定64个0的不存在ID，exit1，空stdout，stderr准确Error response from daemon: No such container: <64个0>；未启动/删除Docker资源。
- py_compile六个实现文件exit0；范围diff-check exit0。完整verify -SelfTest已实际运行，但在既存WEB/build.txt及build-final.txt CR/LF检查失败而停止。未越权重写旧证据；Master已有规范化提交，集成后须运行完整SelfTest。
- 开工fetch一次SSL_ERROR_SYSCALL失败，保留事实；本地origin/main仍c8f1040829b2bfe1e9f7e36223092286975643f0，Master本轮最新fetch已确认同值。

Master需将OwnedTestContainers.Tests.py接入SelfTest、CI governance步骤设置PLATFORM_TASK_ID=G3-M3-001，并在最终真实五组件验收中核对labels/准确ID/cleanup records/exit与不存在诊断。不把此fixture测试提升为本机实际回收或跨Run缓存证据。
