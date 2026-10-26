# G2-FE-001 实施记录

状态：DRAFT / PARTIAL；Owner=g2_fe。实施起点SHA=`69e2ed746e376a36cf3a32d3ee39992b85007c36`，任务分支`codex/G2-FE-001`。任务卡BaseSha保持原值；本报告只记录本Owner新增事实，不代表独立Review或完整G2验收。

## 已实现

- 原有可信SSR身份、彩色Shell、Tokens与深浅主题复用；新增本体资产、发布治理、语义查询路由。
- 原始四份Turtle上传/textarea备用编辑/原字节导出，真实草稿创建/保存、CAS、冲突保留本地文本、显式远端对比/丢弃、结构命令、SHACL与固定修订Diff。
- Cytoscape3.34.4客户端边界懒加载，服务端RDF投影、清理destroy、键盘节点列表、布局不发送语义写入。
- 新G2 transport只消费唯一生成DTO并复用原PlatformApiError/CSRF，same-origin/no-store/redirect-error/取消；写入不自动重试。保存显式重试复用同payload/幂等键。
- 发布审核绑定精确revision/hash/scope/主体/过期，独立批准/拒绝、激活CAS、旧正式Manifest回滚提案。
- 正式能力查询、六态结果、snapshot/来源/证据再次读取、持久Run/harness明确标识、SSE Last-Event-ID/UTF8跨chunk/多行/去重/断开与持久取消分别处理、未知协议停止接收。

## 实际验证

2026-10-26：Node24.22.1，pnpm11.28.8冻结install（批准栈，无Monaco）；读取实际安装Next16.4.3的`dist/docs` use-client/lazy-loading。

- RED：新增3个测试套件首次因尚无实现失败。其后14个用例GREEN（CSRF/CAS/状态/空响应/dirty保留/显式丢弃/SSE跨chunk/未知协议/取消）。
- 首次全量ESLint发现render Date.now purity错误，改为可清理定时器驱动时钟；重跑ESLint exit0。
- 全量Vitest：5 suites / 23 tests PASS（含原G1测试，未改断言）。
- `tsc --noEmit` exit0。
- `next build` exit0，包含真实动态路由 /ontologies /releases /analysis，Cytoscape编译成功。
- 浏览器布局/键盘/ARIA/SSR水合/产品真实E2E：尚未运行；后续补充，不能以单元测试或build代替。
- G2实际Host业务endpoint尚未组合，真实PG/Jena/BFF全链联调 NOT_RUN。
- CI NOT_VERIFIED；独立Review待Master组织；标准唯一ZIP由Master阶段收口。

## 人工暂停与限制

Monaco人工继续暂停：不安装/import/override或新增替代编辑器。原生textarea是同一真实草稿备用路径，绝不计Monaco PASS。专业诊断显示真实TraceId并可复制，固定本地Grafana首页；精确Tempo query deep-link尚未实机验证，不生成伪链接。Release/Run DTO暂未有TraceId，显示关联待后端字段。

GET semantic/discover按Master即时明确对齐：assetId必需、releaseId可选，返回唯一SemanticQueryResult（data.kind=ontology）；此变更由Master落实冻结合同。真实S2/S3接口可用后继续滚动联调，不将有界夹具当E2E。

## S1 UI浏览器里程碑

- 真实Microsoft Edge + 生产Next server，6/6有界界面测试PASS（非真实后端E2E）：1440/1280/390 × 深浅主题6张截图；键盘焦点/节点选择、无横向溢出、SSR水合及console无error；409后本地文本保持并显式远端对比/丢弃；真实仓库四源文件逐字节上传及默认单scope；加载/503/403/404区分。
- 首轮4/6：2条因新测试role=alert与Next内置路由播报节点歧义失败，改为定位组件自身alert后全绿，未放宽行为断言。
- SSE追加已知类型但缺payload字段的真实RED（原实现错误接受），加强判别验证后GREEN；另有真正单字节UTF8跨chunk中文测试。当前全量Vitest25/25，lint/typecheck exit0。
- SelfTest首次缺本树PyYAML失败，复用Master已有批准隔离parser路径后重跑exit0：工程自测8、结构解析正负4、环境状态3组、ReviewPackage35/0。工具环境软链位于Git忽略.tools，不改系统环境/包锁。
- 修复创建缓冲保护、503未读取不显示假空集合、图形主题切换订阅及dispose清理；G2页不额外读取隐藏的G1资源。
- 截图内容仅合成界面身份/合成源，无Cookie/token/HAR/登录材料。无Monaco，Monaco/worker保持PAUSED BY HUMAN。

## S2/S3 UI行为与结构新增里程碑

实施源码起点`7ff7fd53335923661e8b2fa62ad51f0ec12a712c`。

- 结构表单扩展为标准Class/ObjectProperty/DatatypeProperty/NamedIndividual声明、subClassOf/domain/range/label/comment及已声明属性的精确新增/替换/删除；仅发送唯一SemanticEdit，完整源编辑由服务端负责。新增Class浏览器先RED（缺结构操作入口），实现后GREEN。
- 真实Edge有界UI套件16/16 PASS：前述6项加六态、XSS文本、不执行HTML、证据重新授权403、提交者自批禁用、异人审核、激活绑定真实当前CAS、Run确定性标记/真实格式事件重放/唯一终态、结构新增及dirty阻断验证/结构写入、布局无语义写请求。
- 原G1 UI测试5/5 PASS，原断言完全未改；截图隔离到临时目录，不改历史证据。
- Vitest26/26 PASS（新增Last-Event-ID真实fetch流/取消传播测试）；typecheck/lint/build全部exit0。生产Next构建真实路由/客户端chunk成功。
- SSE已知事件缺字段也拒绝、单事件128KiB字节预算、512序列上限；未知协议显式提示并回读持久Run快照。断开订阅/持久取消是独立动作。
- 六张最新界面截图已重开目视检查，1440三栏与390图/校验面板、深浅Tokens正确；不包含真实认证材料。
- 这些测试的API为有界夹具，所有PG/Jena/Keycloak/RustFS/MAF真实G2全链仍NOT_RUN；不能将测试名称中的“真实展示/持久事件”解释为后端验收PASS。CI仍NOT_VERIFIED，独立Review待Master。
