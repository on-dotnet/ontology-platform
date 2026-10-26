# G2-SEM-001 实施账本

当前状态：SEM实现已提交分段里程碑，33项真实范围测试通过，准备独立复审；总体仍DRAFT / PARTIAL，不能把此结果扩大为认证HTTP/FE/完整Publishing闭环通过。下方早期账本保留当时事实，最新验证以末尾“PG集成与交付边界”为准。

- 独立树：`/Users/chasen/.codex/worktrees/g2-sem/ontology-platform`；分支`codex/G2-SEM-001`。
- Common Base：`bd52431b31d560a3b83f4b2e705cea9a0fb40c4d`；write-start Base：`39bf3afac3c41afed09fda3940721e244bde20b3`，开工fetch成功后ff-only同步。默认沙箱首轮fetch因Git worktree元数据权限拒绝，按授权升级后成功。
- 模型里程碑：`fffb1aff4c5fdbb74a6efde5840341daabaa31f5`，独立提交并已push；Master生成迁移，SEM不写任何迁移/项目/锁/共享合同。

## 实际命令与结果

1. `dotnet restore backend/tests/OntologyPlatform.SemanticTests --locked-mode`：exit 0，见restore.txt。
2. `dotnet test --project backend/tests/OntologyPlatform.SemanticTests --no-restore`：初始真实实现不存在，1测试失败/0通过，exit 2，runtime-red.txt。没有空工程通过声明。
3. `dotnet build backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology --no-restore`：exit 0，0 warnings/0 errors，model-build.txt；该build发生于模型commit之前，本地未提交的Domain/codec当时也可编译。模型提交自身独立构建由Master再次核验。
4. `python3 scripts/acceptance/semantic-roundtrip.py --label runtime-integration-first`：exit 1；runner局部import导致变量遮蔽，在测试前失败；已修复，原证据保留。
5. `python3 scripts/acceptance/semantic-roundtrip.py --label runtime-integration-red`：13/13真实测试通过，但收尾SPARQL请求缺Accept导致脚本exit 1。旧JSON exitCode记录为0是首次runner错误（异常时未重置）；该文件含FAIL且不能当整体PASS。已修复runner异常exitCode和Accept。
6. `python3 scripts/acceptance/semantic-roundtrip.py --label runtime-integration-green`：exit 0，13/13通过，真实暂存图残留三元组0。
7. `python3 scripts/acceptance/semantic-roundtrip.py --label shape-cycle-red`：exit 2，14总计/13通过/1失败；`sh:property`自循环到Jena后503，未按安全边界提前422。
8. 同命令`--label shape-cycle-green`：exit 0，14/14通过，暂存图三元组0；新增单层PropertyShape守卫使递归在执行前拒绝。
9. `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`：首轮exit 1（本地缺已批准的YAML解析缓存/测试输出尾随空白/直接重定向目标被自扫描）；原selftest.txt保留。复制既有批准pythonlibs到任务树隔离.tools并将纯文本证据LF/尾空白归一化后重跑，见selftest-green.txt。

## 当前实现与支持边界

纯Domain只含确定性hash/完整scope/源预算规则，无EF/HTTP/Jena依赖。每源256KiB/总1MiB、5000三元组、1000节点/2000边，真实RIOT分别解析四类源，Shape先标准解析再Core谓词与无递归安全检查，操作5秒/并发2，响应体8MiB硬上限，finally独立清理预算。无重定向、任意请求SPARQL/URL、imports抓取或收费模型。

完整原文从未通过投影重建；no-op保留注释及精确字节。复杂OWL/空白节点/import保留完整图和源码并明确阻断结构编辑/发布；OWL推理NOT_RUN。SHACL报告实际按`sh:conforms`判定，真实focus/path/value/sourceShape/component/message映射，原始报告hash按响应UTF8计算。业务定位正文仅返回受保护业务模型，普通日志无正文。正式图按照Master确认GuidN派生，与内存解析的词法/数量逐项回读比对；正式部署/回读当前尚未真实测试。

合成样例包含五类、两个厂区相同外部号不同IRI、Slab到多个RollingEvent到多个Coil及多对多。所有业务断言有命名rdf:Statement/PROV来源、sourceId/sourceRecordId/validFromUtc/observedAtUtc/modelVersion；mappingStatus明确absent。通用运行时没有行业类名称。元数据命名空间`urn:ontology-platform:vocabulary:`已告知Master统一QRY消费。

已编译草稿服务提供CRUD/CAS/历史/真实Diff/报告持久模型、同连接事务审计、幂等回执和发布前只读锁定。PG真实验证暂NOT_RUN：等待Master唯一生成迁移与真实Governance审计writer/测试项目引用。clone的BaseReleaseId目前固定503，等待Master补`IReleaseCatalog.ReadAsync`后立即实现；不猜assetId或绕过scope。save/edit不改变asset/scope；未知bnode只给源码Diff并标图同构未运行。

## 尚未验证/交接

NOT_RUN：PG并发CAS/审计回滚/幂等/旧报告绑定、正式Jena TDB发布回读、HTTP安全guard与OpenAPI、审批失效交叉测试、浏览器、性能基线。CI：NOT_VERIFIED；独立最终Review与唯一标准ZIP由Master组织，此分支不自行main。真实模型/Windows/Intel/生产维持NOT_RUN。继续当前Task2授权，不进入下一阶段。

## e4f6ade独立审查后修复与真实扩展

独立Review（Master报告）：0 Critical / 2 Important / 1 Minor，仅可DRAFT集成，不满足S1。I1短role不匹配真实Claims，已改完整`platform.operator/platform.viewer/platform.auditor`；成功审计改`allowed`。I2已提交create/save回执应先于Jena分析，已添加前置Replay，数据库+依赖故障实际证明仍等待Master共享迁移/writer。M1 selftest.txt文件末尾多空行已修。

- `python3 scripts/acceptance/semantic-roundtrip.py --label published-roundtrip-first`：exit 0，15/15测试通过（含一个实现类型存在检查）。真实临时TDB2证明隔离两版本、规范词法回读通过、01 typed lexical规范化回读失败且旧图仍通过。
- `--label empty-shacl-regression`：exit 2，16项中1失败，空有效Turtle因Fuseki不保留空named graph而503。`--label empty-shacl-green`：exit 0，16/16通过；官方`graph=default`用于空输入，但必须先真实读取证明default为空，应用永不向default写入，不混用其他暂存图。官方依据：[Jena SHACL Fuseki集成](https://jena.apache.org/documentation/shacl/index.html)。
- `--label published-subclass-red`：exit 2，17项中1失败；只验证正式data图漏掉本体父类target。`--label published-subclass-green`：exit 0，17/17通过；正式ontology/data真实回读先逐项对账，再把实际回读合并到独占验证图执行同一Shapes，绝不拿原始源冒充回读内容。
- `--label relative-iri-red`：exit 2，20项中1失败；相对fragment默认解析成含随机暂存IRI的请求URL。`--label relative-iri-green`：exit 0，20/20通过；Master批准稳定文档base `https://ontology.invalid/source/{0..3}/`（ontology/shapes/vocabulary/data顺序），显式BASE优先，不网络抓取。解析、Shapes执行、编辑后再解析和正式部署保持同一语义；原始UTF8源/hash完全不变。该基址不自动提供组织/厂区身份，样例业务IRI继续绝对含org/site/source。
- 同一边界组实际证明非no-op精确编辑其余图不丢失、UTF8单源预算、5001三元组、1001节点、2001边、129项枚举与rdf:rest环拒绝。
- `--label concurrency-cancellation-green`：exit 0，23/23通过；两个真实请求在受控时序门占槽，第三个429；gate只延迟真实HTTP、不返回模拟RDF；调用者取消保留OperationCanceledException，内部五秒预算固定503/semantic_timeout；已有真实PUT后的finally删除，脚本查询所有暂存三元组0。

截至此里程碑真实测试总数23，其中1项只是生产类型实现边界存在，不能把总数写成23次独立引擎执行。PG/HTTP及跨模块审批仍NOT_RUN。新增正式图与安全边界测试没有替代最终PG/端到端验证。

## 共享依赖同步前保存点

共享合同`749cfa86d23a2189c4e63fa3c6889a0ecf5ee228`已cherry-pick为本树`1bfa868`。clone已通过新增`IReleaseCatalog.ReadAsync`消费重新授权的正式清单，只继承assetId和完全相同scope，非Active/Superseded拒绝；S1没有目录时BaseRelease明确503，普通新建不受影响。模块及SemanticTests编译exit0/0 warnings。

新增`OntologyPlatform.Ontology` ActivitySource/Meter只含固定operation/phase/outcome与耗时，不含源码、理由、主体/厂区标签。Host注册由Master负责，端到端OTel导出NOT_RUN。owned HTTP adapter已按实际SEC guard签名绑定，等待共享guard/Host引用后编译与联调；此保存点整体仍DRAFT/PARTIAL。

`python3 scripts/acceptance/shacl-validate.py`首次使用错误树形筛选返回零测试exit8，保留shacl-validate-red-filter.json；改为MSTest实际`FullyQualifiedName~ShaclTests`后12/12通过、exit0，shacl-validate.json。绝不把零测试当PASS。draft-revision入口已准备真实两个模块迁移、临时PG内存/CPU限制和整连接串脱敏；PG测试源码在临时草稿等待共享引用后移入owned目录，未将其当已运行。

## PG集成与交付边界

Master指定的共享提交已顺序同步，无冲突且不手改共享文件：`95d9c37452e6fa096359570a3484dc184f059737`、`5525f71cec05aa8814dbf367d0c2c87d5b12d276`、`8971ea6f09dce63ad31302a8c7c20edf0df7e66e`、`4eeaa56c3a6c3e10ccc54b84cf779f5cbd7570d5`、`3f96b25c194654651812a3024ff38f509d001b2f`、`3f7771416856ad0a0ff6d963847663de15db3094`、`18877aee3a4d6ce26058720555a61100b7f128f2`；共享同步本地Head为`d39a5e1`。SEM自己的HTTP/clone/诊断保存点为`8308340`；之前两个可复检语义Head为`e4f6ade`与`7e24d873c56be50030c3f5aa583330c67424973c`。

### 真运行命令、失败和结果

- `dotnet restore backend/tests/OntologyPlatform.SemanticTests --locked-mode`、`dotnet build backend/tests/OntologyPlatform.SemanticTests --no-restore`：exit0，0 warnings/0 errors。
- `python3 scripts/acceptance/draft-revision.py`：首轮exit0，30/30通过、0跳过。真实应用Governance两迁移与Master生成的InitialOntology迁移，未用EnsureCreated。启动新库先查询尚不存在的migration history产生的SELECT提示属于EF的首次建库路径，随后迁移命令exit0；不隐去该输出。
- `python3 scripts/acceptance/semantic-roundtrip.py --postgres --filter FullyQualifiedName~CommittedCreateAndSaveReplayWithoutJena --label idempotency-mutation-red`：暂时禁用create/save前置回执返回后，真实PG已提交create在不可达Jena下重试失败，1/1 FAIL、exit2；变异在finally恢复，未提交变异代码。
- 同一命令`--label save-replay-mutation-red`：仅禁用save前置回执返回，create重放成功后save在不可达Jena下重试失败，1/1 FAIL、exit2；同样finally恢复。
- 同一命令`--label replay-restored-green`：恢复生产实现后create/save重放1/1 PASS、exit0，源修订及审计均不重复，异载荷409。
- `python3 scripts/acceptance/semantic-roundtrip.py --postgres --label draft-revision-green`：新增并发幂等/Down保护后，第一次33项中32通过、1失败。真实Down已正确55P03拒绝并发锁，但测试误以为PostgresException直接抛出；实际Npgsql包装InvalidOperationException。失败保存在migration-down-red-wrapper.json；修改测试明确核查InnerException的真实SQLSTATE后再次运行33/33 PASS、0跳过、exit0，见draft-revision-green.json。
- 同scope相同幂等键并发实际只有1草稿/1回执/1审计；相同载荷返回相同固定结果，异载荷只有1成功+1个409。不同键相同旧revision的并发保存只有1个CAS成功，另一409，无丢失更新。
- 审计故障注入先调用生产Governance writer真正写入同物理事务，再抛异常，真实验证草稿/回执/审计全回滚；并非用“返回固定审计ID”模拟成功。
- 发布读取锁使用真实同一Npgsql连接/DbTransaction，当前revision/hash/真实SHACL报告一致才返回；源修改后旧report/revision409。此项证明Ontology边界，未宣称完整Publishing审批状态机已运行。
- 三个完整platform角色均真实可读；只有platform.operator可写；短名/未知role拒绝。双厂资源对单厂/异组织403、目录不泄露、不存在404，非法Turtle422且源修订不变。
- clone测试的PG/Jena/审计为真实实现，但IReleaseCatalog是**明确的合同替身**：只验证消费端继承asset及完全一致scope，缩小到首厂仍拒绝。真实Publishing目录/审批clone联调NOT_RUN，不用此测试冒充。
- Master迁移Down在真实业务行锁存在时55P03拒绝，释放锁但仍有历史时P0001拒绝；源字节、当前草稿和migration history实际仍存在。
- 整个`backend/OntologyPlatform.slnx`受锁restore/build和三个owned范围format命令全部exit0，见integrated-build-format.json。初次误用根目录不存在的solution路径exit1保存在integrated-build-red-path.json；修正真实路径后执行成功。HTTP adapter已随真实API工程编译，尚未代表宿主已挂载或认证HTTP验收。

33总计包含1个生产类型存在检查、1个明确catalog替身消费边界；其余为真实Jena/PG或对真实执行路径的安全/资源/故障验证，不宣称33个独立端到端场景。所有临时容器使用已批准固定镜像、随机回环端口和独立存储，用完删除；不读历史runtime/认证材料，证据不含生成密码或连接串。样例文件大小和真实SHA256见sample-hashes.json。

### Master下一步集成点与准确未验证项

- 已实现入口：`services.AddOntologyModule(configuration)`；`app.MapOntologyEndpoints()`，`Semantics:ValidationOrigin/PublishedOrigin`由Master配置，PG使用ConnectionStrings:governance。宿主应注册ActivitySource/Meter `OntologyPlatform.Ontology`。配置/Host/迁移/锁均为Master唯一写入。
- IReleaseCatalog建议由独立只读实现提供；若Publishing同一服务反向依赖IDraftPublicationReader并实现catalog，需避免DI循环。当前两个公共接口无变更，后续由Master协调实际组合。
- 当前分支不自行main或生成第二份Review ZIP。独立复审、认证HTTP/CSRF+ETag与FE完整S1集成、真正Publishing审批/激活/回滚/clone、导出OTel的端到端验证、正式性能基线、同Head CI和唯一Review ZIP由Master后续关口完成，当前标NOT_RUN/NOT_VERIFIED。
- OWL逻辑推理、收费/真实LLM、Windows/Intel/生产继续NOT_RUN；不自动进入G3–G8。

### 最终格式诊断的适用范围

全solution无过滤format首次exit2发现自有初始化器/导入格式与共享WireContractTests格式。随后两轮按repo根cwd的相对/绝对`--include`虽然exit0却未实际选择文件，不能当格式已修的证据（final-verification.json前两条仅保留真实命令事实）。诊断确认应在`backend` cwd使用相对该目录的`src/...`、`tests/...`路径。以此实际格式化自有JenaSemanticRuntime、OntologyService、SemanticFixture，owned精确清单verify exit0；不带include的whole-solution verify确认只剩Master-owned WireContractTests.cs:158–159的WHITESPACE（exit2），已报告Master，不跨写。详format-root-corrected.json。

其余最终检查：whole-solution build exit0；G2ContractTests 19/19 PASS、0跳过、exit0；SelfTest exit0（35 ReviewPackage等检查器正反例，不冒充产品测试）。AppHost格式加载ASPIRE010和生成迁移namespace建议为已记录warning，没有擅改共享配置或迁移。Master修复共享格式后需整体重新verify；当前不把whole-solution format标PASS。

最终已格式化自有源码再次执行`python3 scripts/acceptance/semantic-roundtrip.py --postgres --label formatted-final-green`：33/33 PASS、0跳过、exit0；真实暂存三元组0，临时Jena/PG容器均已删除，见formatted-final-green.json。仅源码格式调整后复验，没有把旧未格式化运行冒充最终快照验证。

## 限定复审后的合法空文档与路由授权元数据修复

本批修复基于已推送 `13cba4fcb07743458f946627ced0b9300c3f58a5`。Master转述原2I/1M已全部ADDRESSED，新增Minor仍应修复后限定复验；本批仍DRAFT，不自行合main或扩大当前关口。修改前`git fetch origin` exit0、工作树干净。只改自有JenaSemanticRuntime、OntologyEndpoints、RoundtripTests与本证据目录。

根因：RIOT接受注释/空白/prefix-only文档并产生零三元组，但Fuseki不保留对应空named graph；随后GSP GET404被正确的通用依赖错误映射为503，因而合法源无法保存。不能从字符串关键词猜测Turtle是否为空，也不能全局把404当空图。

处理：仅在`ParseSourcesAsync`的独占临时解析图前置随机GuidN生成的全绝对IRI三元组。RIOT完整解析原始文档，实际回读必须精确包含本次marker，随后仅剔除该完整三元组。前置位置保证用户BASE/prefix/末尾注释不能改变marker或补齐非法语法；随机marker从未进入权威SourceBundle、原文hash、业务投影、Shape安全检查、预算、编辑序列化或正式图。不得按命名空间广泛过滤，以免丢失用户公理。GSP404仍是503；即使200而marker缺失，也返回503/temporary_graph_incomplete，避免Jena重启/临时图替换被误当成合法空图。原有独立finally清理保持不变。

- 红灯实际命令：`python3 scripts/acceptance/semantic-roundtrip.py --filter 'FullyQualifiedName~LegalEmpty|FullyQualifiedName~LostOrReplaced|FullyQualifiedName~MissingPublished' --label empty-documents-red`，exit2，7项中5失败/2通过/0跳过。三种合法空本体（`# comment\n`、纯空白、仅prefix）连同仅prefix Shapes均复现503；空图新增编辑同样失败；实际替换临时图时旧代码没有检查回读完整性。真实删除临时图和正式图两个既有失败关闭场景已通过。见empty-documents-red.json。
- 绿灯全量命令：`python3 scripts/acceptance/semantic-roundtrip.py --postgres --label empty-documents-full-green`，exit0，40/40通过、0跳过；覆盖原33项及新7项。真实PG先应用交付迁移，真实Jena RIOT/SHACL/TDB2运行；测试结束查询暂存图三元组总数0，两临时容器已删除。见empty-documents-full-green.json。
- 新回归核对空图投影0条、原文hash准确、Shapes原文和hash不变、官方SHACL报告符合；对空源新增Class的导出必须恰好一条指定业务三元组，后续RIOT投影也只能一条。临时图删除/替换是通过真实GSP在PUT之后GET之前操作，没有伪造引擎响应。正式测试先真实部署两个非空图，再删除数据图，ReadPublished与Verify都明确503。
- 本体7路由补`.RequireAuthorization`：3个GET使用`semantic.read`，4个POST/PUT使用`ontology.edit`，与各自guard相同策略。认证授权中间件可在body绑定前处理策略；原guard继续CSRF/scope/If-Match/业务错误边界。未修改Host或共同guard。最终匿名/不允许角色+坏body的HTTP与拒绝审计验收由Master真实Host集成验证，本批不宣称该HTTP链路已运行。
- `empty-documents-verification.json`保存真实cwd、命令、完整输出和退出码：backend cwd精确三文件`dotnet format OntologyPlatform.slnx --no-restore --include ... --verify-no-changes`；`dotnet build backend/OntologyPlatform.slnx --no-restore`；规定SelfTest；`git diff --check`，四项均exit0。SelfTest中的35项ReviewPackage及其他检查器正反例不是业务测试。全量构建仍有既存ASPIRE010 warning，不改共享配置。

40总计仍含1项类型存在检查和1项明确catalog替身消费边界，不能称40个独立端到端场景。其他真实链路与未运行边界见前文；同Head CI、Master认证HTTP/FE集成、唯一ZIP仍NOT_VERIFIED/NOT_RUN，待Master限定复验与集成。

## 正式读取同批完整性绑定修复（QRY Review缺口）

当前修复授权来自Master限定派工：仍属G2原Ontology owned范围，修复Catalog Verify之后再ReadPublished的二读窗口，不扩展业务或依赖。读取了适用AGENTS/原任务卡/Task2 brief及指定SDD `subagent-driven-development/references/fix-loop.md`；复用原实施报告保存真实修复证据，不派子Agent、不手改公共配置。源代码独立提交已push：`21ed0172fc207db55164985f3c97fd2a640f1519`，仅JenaSemanticRuntime及新增owned VerifiedReadTests.cs（新增测试文件已通知Master）。

共享接口由Master冻结`0e970f948aede10be0a86570a05d958d135a2761`，本树cherry为`098418c`。G2Services自动合并；冻结doc因本树缺少Master中间追加段发生上下文冲突，按Master明确批准保留本树原文、只精确追加0e970f9新增条款。未自行修改合同语义，Master集成时应使用自身完整上游合同，无须重复cherry本树共享提交。

实现仅新增`ReadVerifiedPublishedAsync`和私有绑定检查：先核清单SchemaVersion1、服务端GuidN release/固定graph关系、manifest完整五hash（四源+BundleHash），以及snapshot release/两个graph/四源hash逐项与清单一致；再经唯一ParseSourcesAsync真实RIOT及Shape/支持边界解析完整原文。每个正式图仅GET一次，将这两批实际数组与源规范三元组逐项精确比较，返回**同两批数组**。不调用Verify后再Read，不重新发GET，不新建解析器。词汇源并入正式ontology图，可选词汇absent仍按null参与hash。所有源/清单错版、坏语法/预算、缺图/篡图和typed lexical不一致失败503；并发429和用户取消保持共享Execute原语义，内部五秒超时固定semantic_timeout503，finally仍独立清理暂存图。此方法验证所返回批次与不可变源一致，不承诺返回后外部存储永远不再变动。

覆盖文件：`backend/tests/OntologyPlatform.SemanticTests/VerifiedReadTests.cs`；原40项SemanticTests保持完整回归。新增10项包括旧接口默认fail-closed正控、同批真实读取、四种图篡改/删除/01词法变化、16种单字段错版+源码注释错版、可选词汇/缺失绑定、调用者取消与内部5秒超时。旧适配器测试仅验证默认接口不调用旧入口，明确不是引擎调用；其他故障注入通过真实临时Jena GSP改变测试独占图，未伪造RDF响应。新方法不承担Catalog授权、对象存储逐字节核验或QRY六态映射，它们仍由对应Owner真实集成。

实际命令与结果：

- `python3 scripts/acceptance/semantic-roundtrip.py --filter FullyQualifiedName~VerifiedReadTests --label verified-read-red`：exit2，10项中5失败、5通过、0跳过。生产尚无新实现，默认503导致合法读取/同批返回/optional词汇/取消超时路径真实红灯；初始默认503下的故障正控通过不能单独证明生产实现，后续完整绿灯和变异为补充证据。
- `python3 scripts/acceptance/semantic-roundtrip.py --postgres --label verified-read-full-green`：exit0，50/50通过、0跳过（原40+新10）。真实应用治理和本体交付迁移、真实RIOT/SHACL/TDB2；运行完临时named graph三元组总数0，两容器均删除。见verified-read-full-green.json。
- `python3 scripts/acceptance/semantic-roundtrip.py --filter FullyQualifiedName~VerifiedReadReturnsExactlyTheComparedBatch --label verified-read-reread-mutation-red`：只把生产新方法返回数组临时变异为比较后重新GET；真实第一次本体GET后、data GET前修改正式ontology图，测试exit2/1项失败，发现正式读取次数实际4而期望2。变异脚本finally恢复原源码，未提交变异。测试同时断言返回原正确ontology/vocabulary/data和下一次读取篡改图必须503；该变异证明能检测实际二读窗口。
- `python3 scripts/acceptance/semantic-roundtrip.py --filter FullyQualifiedName~VerifiedReadTests --label verified-read-restored-green`：恢复原实现后exit0，10/10通过、0跳过，暂存图零残留，容器已删除。
- backend cwd：`dotnet format OntologyPlatform.slnx --no-restore --include src/Modules/Ontology/OntologyPlatform.Modules.Ontology/JenaSemanticRuntime.cs tests/OntologyPlatform.SemanticTests/VerifiedReadTests.cs --verify-no-changes`：exit0，精确选择自有两文件。`dotnet build backend/OntologyPlatform.slnx --no-restore`：exit0，既存ASPIRE010 warning保留。`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`与`git diff --check`均exit0，实际输出一并存verified-read-verification.json，未把检查器正反例计入50产品测试。

新方法源提交与证据提交分离，供Master和QRY Owner独立消费和限定复审。整体继续DRAFT/PARTIAL；QRY读取不可变对象+本新方法+真实HTTP六态/证据链的跨模块联调、同Head CI、唯一审查ZIP由Master组织，本SEM专项不宣称这些链路已运行。原空文档修复8b9bd188及本修复等待Master组合限定复核，无main合并。

## 限定复审M1：内部marker不占业务三元组预算

Master限定复审确认旧空文档Minor已ADDRESSED，同批读主路径C0/I0；新增M1为合法单源5000条业务三元组加marker后在RDF/JSON映射层误超5000。按Master本轮明确修复指令执行，已重读指定SDD fix-loop。基线为`85bf03ca26590551a96ad4b74e156d7b7141ceeb`，修改前fetch exit0/工作树干净。仅修改自有JenaSemanticRuntime/JenaRdfCodec/VerifiedReadTests与SEM证据；Linux runner已由Master接手，本轮完全未改runner、共享文件或依赖。

源码小提交：`c2ca4c3279eb8b57e9d022b1c2890e0adbb702d3`。JenaRdfCodec.Parse新增默认false的内部marker许可，只能额外容纳一条。唯一显式true调用位于ParseSourcesAsync本次带随机marker的临时GSP响应映射；随后仍要求精确marker出现一次、剔除后按四源合计严格5000检查。正常正式图ReadGraphAsync、SHACL响应等所有其他调用仍使用默认5000，不一般放宽到5001。没有新解析器、无源/hash改写、无正式图marker、无清理/取消策略变化。

覆盖测试仍在`VerifiedReadTests.cs`：新增7项，单源4999/5000成功且源hash准确、5001拒绝；正式已验证读取四源合计4999/5000成功并恰好两次正式GET，5001在正式读取前503；实际注入5001条正式图后，旧底层读仍422/rdf_triple_budget、新消费边界503。测试图用同主体/同谓词/短literal避开节点、边与字节限额。正式正控用ontology一条与data余下条数，两图非空，明确测合计预算；单源5000边界由Analyze真实RIOT测试直接覆盖，不把空正式图缺失当成功。

- 红灯：`python3 scripts/acceptance/semantic-roundtrip.py --filter 'FullyQualifiedName~TemporaryMarkerDoesNotConsume|FullyQualifiedName~VerifiedReadRetainsAggregate|FullyQualifiedName~PublishedGraphDoesNotReceive' --label marker-budget-red`，exit2，7项中1失败/6通过/0跳过；唯一失败为单源5000，真实堆栈JenaRdfCodec.Parse原第44行，符合Review根因。原始输出见marker-budget-red.json。
- 绿灯：`python3 scripts/acceptance/semantic-roundtrip.py --postgres --label marker-budget-full-green`，exit0，57/57通过/0跳过（原50+新7）；实际PG交付迁移/真实Jena RIOT/SHACL/TDB2，旧同批2次读取、各hash/snapshot绑定、取消与超时清理均继续通过。全部暂存图三元组0，两临时容器已删除。见marker-budget-full-green.json。
- backend cwd精确三文件`dotnet format OntologyPlatform.slnx --no-restore --include src/Modules/Ontology/OntologyPlatform.Modules.Ontology/JenaSemanticRuntime.cs src/Modules/Ontology/OntologyPlatform.Modules.Ontology/JenaRdfCodec.cs tests/OntologyPlatform.SemanticTests/VerifiedReadTests.cs --verify-no-changes`：exit0。
- `dotnet build backend/OntologyPlatform.slnx --no-restore`：exit0，既存ASPIRE010 warning保留。`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`与`git diff --check`均exit0，记录在marker-budget-verification.json（完整命令/cwd/退出码/输出）；不把SelfTest检查器正反例混入57项产品测试。

本轮仍DRAFT，源码/证据分提交push，等待Master限定独立复核。57项中依旧包含生产类型存在和旧适配器默认行为检查、明确catalog替身消费边界，不称57独立端到端场景。跨模块QRY/Host/FE与同Head CI、唯一ZIP由Master总集成确认；未合main、未派Agent、未读历史runtime或认证材料，完成即停止。
