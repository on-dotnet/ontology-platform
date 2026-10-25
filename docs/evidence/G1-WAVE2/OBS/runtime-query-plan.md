# 真实OBS查询与安全证据计划

状态：DRAFT/PARTIAL，Owner=OBS；AppHost/全部进程生命周期由Master控制。只连接本轮回环开发栈，不启动第二栈，不请求生产、不外发通知。helper位于infra/observability/query-runtime.py，仅Python标准库，无新增依赖。

## 可复现命令

在OBS独立树中执行以下命令。全部输出写入新建OBS证据runtime/UTC目录，已有目录不覆盖。首次两个API匿名me401是受控真实请求，不声称已做已授权资源访问或PG审计。认证闭环和审计由SEC/Master验收提供。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/observability/tests -v
python3 infra/observability/query-runtime.py --capture integration --api-origin http://localhost:15100 --api-origin http://localhost:15101
python3 infra/observability/query-runtime.py --capture query --trace-id 实际32位小写TraceId
python3 infra/observability/query-runtime.py --capture health
```

integration生成真实401请求，保存安全ProblemDetails和TraceId，等待默认45秒OTLP导出后回查。query不发新API请求，可在Master重启相同卷后按原TraceId再次读取，不能用新造数据冒充持久化。helper禁用环境代理和重定向，仅允许无userinfo/path/query的HTTP localhost/127.0.0.1 origin；不会跟随OIDC。网络错误、空数据、缺实例、索引越界均FAIL；未注入Grafana开发认证时相应项NOT_RUN，退出2；任一FAIL退出1。只查询项全部满足时为PASS_SELECTED_QUERIES，不表示截图、故障注入、持久化或完整G1通过。

## 认证与原始输出边界

Master仅在启动helper子进程时注入WAVE2_GRAFANA_PASSWORD，用户固定platform-dev-admin。不将秘密作为CLI参数、不打印环境，不读runtime文件；helper仅在Grafana回环origin构建内存Basic认证，不记录请求头。只保留响应Content-Type/X-Trace-Id/X-Audit-Id/X-Correlation-Id，不保存Set-Cookie或Location。JSON在捕获时递归屏蔽password/token/cookie等字段、JWT模式、运行时已注入秘密及其Basic编码；非JSON正文省略仅记字节数。响应JSON除该有限脱敏外保留原结构；此扫描不是完整泄漏检测。禁止HAR、认证storageState或trace包。

## 实测查询与判断

1. Loki query_range用实际TraceId筛选，Tempo/api/traces/同TraceId必须返回同一链路。响应中的日志body/metadata来自实际采集，不造示例图。
2. Loki真正索引用/loki/api/v1/series检查，只允许service_name/service_version/deployment_environment_name。[官方结构化元数据说明](https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/)指出查询可返回非索引metadata；不能把query_range返回的所有stream字段误判成索引。首次helper曾发生此误判，原始FAIL保留，后续改用series复验。
3. Prometheus series按本服务查询，排除用户/厂区/Trace/审计等无界标签；允许受控instance=platform-api-1/2和固定路由。请求Counter先读取两个instance，再按同一time参数查询sum并严格比对；无样本/NaN/无界实例均失败。此查询证明实际series身份和聚合，未单凭快照声称整个时间段不存在重置/乱序。
4. Grafana读取四个实际uid，meta.provisioned与中文标题均满足；三个datasource health必须OK；经Grafana/api/ds/query返回真实数据frame。只证明选定查询；中文安全截图需浏览器实拍，不能用API JSON渲染截图冒充Grafana。
5. 告警只保存当前/api/v1/alerts快照。触发/恢复由Master受控停启API或指定Tempo容器，再追加带UTC的pending/firing/resolved与ALERTS范围证据；helper不kill、不stop任何进程。
6. 持久化先固定原TraceId/时间范围和历史指标，再由Master保留相同卷/秘密重启后复查；截图仅登录后中文面板和安全合成数据，不含登录表单值、Cookie、URL认证参数。未执行项保留NOT_RUN。

## 已观察与修复

新鲜收尾回归输出见verify-runtime-query-tests.json（9项）。初始边界测试未覆盖成功HTTP，真实health触发Request.method AttributeError；补真实ThreadingHTTPServer正例复现后改get_method，9项测试通过。第一次实际集成查询成功产生两个Trace并查询Tempo、Prom，但Loki metadata误判导致PARTIAL；后续query按原TraceId复查日志、Trace、真实索引和两实例sum通过。完整证据位于runtime/20261025T092157Z及runtime/20261025T092336Z，前者FAIL不删除。Grafana认证结果以Master实际注入调用对应目录为准；截图、告警故障、重启在本计划创建时仍NOT_RUN。

SelfTest首次收尾检查因局部变量password被有限凭证赋值规则误判，原始FAIL见verify-runtime-milestone.json；仅将内存变量改为grafana_password，不改变读取/脱敏行为，重跑见verify-runtime-milestone-final.json。未降低或修改公共检查规则。

第二次SelfTest因状态文档引用本次尚未落盘的结果文件而失败（verify-runtime-milestone-retry.json）；最终运行先创建RUNNING记录，再保存实际退出码和完整输出，避免将证据创建时序误当通过。
