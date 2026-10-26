# G2-SEM-001 实施账本

状态：DRAFT / PARTIAL，S1进行中，不能以当前编译或Jena通过代表PG/HTTP/发布闭环通过。

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
