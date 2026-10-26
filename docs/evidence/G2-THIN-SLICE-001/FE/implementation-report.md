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

## 当前前端可独立实施部分收口

状态仍DRAFT / PARTIAL。当前新增源码与证据将在任务分支持续提交；本节不是S1/S2/S3集成或产品E2E通过声明。

- 最新实测：G2 Edge有界UI **24/24**，G1原Edge回归 **5/5**，Vitest **26/26**；lint/typecheck/生产build全部exit0；SelfTest exit0。完整实际进程输出保存在[日志目录说明](logs/README.md)，保留RED摘录与首次日志格式失败，没有改检查器。
- 三页面×1440/1280/390×dark/light共18张安全合成截图。真实浏览器执行键盘交互、无横向溢出、console/pageerror与SSR水合检查；截图已重开目视检查。Monaco/worker始终PAUSED BY HUMAN，不计PASS。
- 新增内部导航dirty保留/显式丢弃；真实SSE格式的游标续订、去重、断开不取消、独立持久取消、未知schema停止文本并回读快照，均有真实浏览器行为测试。
- 发现默认Active查询绑定已加载releaseId的问题，浏览器先RED（实际releaseId为旧ID），再修为Active发送null由服务端当次固定snapshot；显式历史版继续发ID。Run继承同一受控计划。
- Trace复制失败安全显示提示；固定本地Grafana入口可打开，但精确Tempo trace query仍NOT_VERIFIED，未伪称专业深链已验收。

### 真实服务续接前提

Master需完成受保护的G2 Host composition、真实迁移/PG与Jena资源及同源BFF转发。先交付`/api/v1/ontology-drafts`真实S1入口，再滚动开放release-proposals/approvals/releases/release-activations和capabilities/semantic/evidence/execution-runs/events。端点必须复用可信会话、完整scope、CSRF、If-Match/Command和原ProblemDetails。共享DTO更新（Release/Run真实TraceId）仅由Master生成，本Owner再消费，不手改生成文件。

真实验收需使用既有批准的合成OIDC身份流程，完成四源导入→revision2→结构/验证/Diff→异人审批→发布→正式六态/证据→deterministic Run事件/续订/取消与真实服务故障；本轮界面夹具全部不能代替这些事实。没有读取、展示或打包Cookie、凭证、登录HAR或生产数据。付费模型、生产访问、跨平台/完整OWL推理仍不在本轮已验证事实内。

独立Review、真实后端E2E、同Head CI、Master main集成和唯一标准ZIP仍待后续，当前分支不自行合并main。

最终本轮实施SourceSha=`46b05f073aa9c425bf5c11c3da0160806d73a134`（全部产品源码/测试/截图/日志已在该提交；后续此行仅文档关联提交，不改变已验证源码）。

## 独立Review修复第一轮（1/5）

固定Review Base=`575b41f91844d543662c2423be91fd35e8675888`。本轮由原Owner实施，未派Agent；实现方复验完成，等待原Reviewer限定再审，整体仍DRAFT / PARTIAL。

共享依赖按Master明确指令引入原提交`457911442aaa12f3ba170ee43c70343b64581f39`，本树cherry-pick为`c06f94a`；两者stable patch-id均`265786f489fb762c7d3d4b08cb5e935836d79bca`。该祖先提交包含Master拥有的生成DTO/合同/服务接口和PUB任务卡，属于明确导入，不是FE越权重写；之后共享路径无手工差异。限定审查FE修复可用`c06f94a..修复Head`，全轮仍保留`575b41f..Head`及该依赖说明。

- **I1**：新增`features/agent/event-schema.ts`只验证唯一生成DTO的完整字段/类型/互斥SemanticDatum/全部9类事件payload；完整snapshot包括四源hash、图及所有版本数组，事件与tool.result必须等于所选Run固定snapshot。未知/不完整/冲突载荷不进入答案列表，明确不支持并实际回读Run快照。7个实际错误accepted红例已转绿，另验证全部合法payload及ontology/entity/relationship正分支。
- **I2**：先消费每个完整SSE帧，再检查未完整帧预算；JSON单事件仍限制128KiB UTF8，独立传输帧/残留帧缓冲256KiB，不按多事件网络chunk累计误拒绝。同一70×4096ASCII流以单字节、37B、单一大chunk输入所得70事件完全一致；单事件真正超128KiB在单/多chunk均拒绝。
- **M1**：文件使用arrayBuffer与严格UTF8 decoder（fatal、保留BOM），无替代字符；BOM/CRLF/中文/空源roundtrip逐字节一致。非法UTF8保留旧缓冲并明确报错。optional vocabulary absent保持null并禁用伪空文件导出；显式导入空文件仍是合法空源。
- **M2**：只删除历史红日志多余EOF空行，原失败内容保留。原实施Base69e2ed7和本轮Base575b41f的diff --check均exit0。
- **集成待办**：每次接受持久事件即推进本地run.lastSeq，取消CAS不再等待下一次GET；浏览器红例expectedRevision0→1已转绿。ReleaseSummary/ReleaseActivation/ExecutionRun消费Master真实TraceId，缺失显示未关联，固定Grafana入口不伪造Tempo深链。

实际命令/退出码/输出见`logs/review-round1-*`：`tsc --noEmit`0、ESLint0、Vitest **53/53（6 suites）**、生产Next build0、G2 Edge有界UI **30/30**、原G1 Edge回归 **5/5**、`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`0（ReviewPackage35/0）。RED完整SSE输出与M1/CAS/EOF真实观察单独保留；日志仅规范化LF/行尾空白。没有修改旧G1断言、生成器、包锁或Tokens；Monaco无安装/import/override。

Master已准备新隔离Host环境，本Owner按指令等待可用通知后开始真实服务联调；本轮所有夹具依然不代表PG/Jena/Keycloak/RustFS/MAF真实G2 E2E。CI NOT_VERIFIED。新增同owned feature helper已向Master登记，审查/集成责任仍在Master。

第一轮修复SourceSha=`9b0e0d1ed18edb90231fe0b46273da7c1f101f91`；本行仅文档关联，不改变该提交已验证源码。

## S1真实布局缺陷的限定修复

修复Base=`037cab14cfbeb1511c3f6f368216beef2bbd64c7`。Master提供真实Synthetic页面红证据：1440 viewport、scrollWidth1684，inspector面板417但隐式grid列及所有子section678。读取其明确提供的JSON/截图和后续computed/CSSOM证据，未读取private runtime/凭证，未改Root QA脚本。

根因和红绿：首版从1440起步的长IRI夹具未复现，保留`long-layout-first-not-reproduced.txt`，不伪称RED。按Master补充的真实时序，在1280两列完成结构新增Class、SHACL、长JSON Diff后，同页首次切1440三列，精确复现scrollWidth1684/子section678，`long-layout-red.txt`实际exit1；原始红几何保存在`long-layout-1440-dark-red-observed.json`。Cytoscape已初始化的画布宽度参与隐式auto列min-content，断点收窄后锁住旧宽度。

产品修改仅局部`features/ontology/workspace.css`三组约束：g2-stack显式minmax(0,1fr)、其直接子项min-width0、Cytoscape生成wrapper/canvas的max-width100%。前两组消除持久锁宽；观察到图resize回调前仍可能瞬时溢出1683，第三组防止旧画布绘制区域在回调前越界。没有新增overflow hidden/clip、裁切内容、修改global tokens或业务源码；原有全文换行和键盘节点列表保留。

有界浏览器新增用例`tests/g2/long-layout.spec.ts`：标准5类/4关系/5数据属性的27条IRI断言，加Class后15节点/28条，hash按实际UTF8计算；模拟结构命令/SHACL/Diff接口，不在产品中解析OWL。按1280完成→1440→1280→390同页变换，六种深浅组合均验证双rAF即无横向溢出、后续canvas正确resize、完整IRI/Diff可读、节点/重布局按钮可键盘访问；多次布局与resize不产生语义写入（只有结构和验证两次POST，revision保持3）。没有以隐藏overflow满足测试。

实际最终几何：1440×dark/light均scrollWidth1440、子section375；1280均1280、子section678；390均390、子section328。六张新安全Synthetic截图已重开检查，所有几何/RED/命令输出见`logs/long-layout-*`。

最新本树验证：生产Next build0、lint0、typecheck0、Vitest53/53、G2 Edge31/31（新增1条覆盖六组合及resize）、原G1 Edge5/5。SelfTest输出亦保存。Master此前真实OIDC/HTTP及S1业务操作通过的事实仍归Master证据，本树夹具不计真实服务E2E；待Master将本修复集成后重跑真实S1完整页面，并安排限定独立复审。Monaco保持暂停，任务整体仍DRAFT/PARTIAL。

限定布局修复SourceSha=`d52acc0aeef55a58189194708822233952dac620`；本行仅文档绑定，未改变已验证CSS/测试。
