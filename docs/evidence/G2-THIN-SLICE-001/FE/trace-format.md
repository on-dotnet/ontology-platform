# G2 Trace 定位链接的限定实现与核实

2026-10-26；Owner=g2_fe；BaseSha=`a47455d336cb4c1c283febf4750f0f01d45daeae`。本轮仅修改semantic-feedback组件、对应单元测试及FE trace-*证据/实施记录；布局基线d52acc0/a47455d保持。Master负责真实Grafana/Tempo中的端到端验收及唯一Review ZIP，本文不表示真实Trace已查询成功。

## 官方依据

- [Grafana官方Explore外部URL文档](https://grafana.com/docs/grafana/latest/visualizations/explore/get-started-with-explore/#generate-explore-urls-from-external-tools)：2026-10-26读取，页面标注latest v13.2。`/explore`接收URL编码JSON的`panes`、`schemaVersion=1`、`orgId`；pane使用datasource UID、queries、range，query包含refId和datasource的uid/type。range接受相对时间。
- [Grafana官方v12.3.0 Tempo datasource源码](https://github.com/grafana/grafana/blob/v12.3.0/public/app/plugins/datasource/tempo/datasource.ts#L312)：实际读取raw官方源，312–357行表明`queryType=traceql`且query为纯hex时进入`handleTraceIdQuery`；534–546行将其转为traceId查询。采用此明确源码支持的入口，不凭记忆直接拼接未知queryType。
- 精确部署镜像在本树`infra/observability/resources.json`固定Grafana13.2.4，读取其同tag官方源码URL返回404。不能声称已复核该tag源码或浏览器行为；latest13.2官方URL文档与可读取v12.3.0源码共同作为实现依据，实际部署行为由Master继续验收。
- 本树provisioning实际Tempo UID为`platform-tempo`，Grafana固定开发root_url为`http://localhost:15330`；本轮只读配置，没有修改数据源或宿主。

## 行为边界

- Trace组件从原来的固定首页，改为固定本地Explore入口；pane和query均指定`platform-tempo`，`queryType=traceql`，query仅为该实际响应TraceId的小写hex；range为now-24h到now，orgId为本地默认组织1。
- 严格要求32个ASCII十六进制字符且非全零；不修剪空白、不接收任意URL/TraceQL/查询参数。无效输入仍以React文本显示并可复制，但不生成导航，并提示无法定位链路。
- URL仅有固定schema/org/pane元数据和受校验TraceId；不读取或编码Cookie、token、CSRF、身份、源文本、Prompt、连接串等秘密。JSON经过URLSearchParams编码，target为新页且保留noreferrer。
- 原剪贴板复制和失败恢复提示保留。关联标识仍取自各实际响应；本轮不修改worker独立Trace设计，不把不同Trace拼成单一parent链。
- UI测试通过只说明渲染及生成链接的契约正确；Grafana登录、Tempo存储/保留期、Trace存在性、真实查询请求及完整端到端均由Master验证。没有将链接存在解释成Trace查询PASS。

## 测试与工具

采用test-driven-development与verification-before-completion技能。新测试渲染真实Trace组件并解析实际href；2个大小写正例和12个负例先对原组件14/14失败（实际首页路径、无效输入仍有href），见trace-red.txt，再在完整套件67/67通过。负例包括空/全零/31位/33位/非hex/前空白/尾换行/查询注入/任意URL/HTML/编码文本/全角字符；正例断言固定origin/path、无用户密码/hash、严格URL参数、完整pane/query、复制入口与noreferrer。

使用已批准隔离Node24.22.1（`/opt/homebrew/opt/node@24/bin/node`）及本树已安装工具，无依赖/锁变更。首轮普通沙箱执行Vitest因不允许写g2-fe树的.vite-temp而在启动阶段EPERM；按明确授权申请该独立树写权限后实际执行，不计该启动错误为产品RED。trace-vitest.txt、trace-lint.txt、trace-typecheck.txt及trace-selftest.txt记录各命令实际退出码。

Monaco继续PAUSED BY HUMAN，无安装/import/override。本轮不接触共享Tokens、合同、包锁、Host、CSS或原G1断言；CI NOT_VERIFIED，独立Review及集成由Master组织。
