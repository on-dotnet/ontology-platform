# G3-M5-WEB 可审查切片

状态：DRAFT/PARTIAL，等待独立Review与Master真实API浏览器验收。Base=3e71049（完整SHA由Git对象恢复）；分支codex/g3-m5-web，独立托管树40e2/ontology-platform。未写main、未开容器、未改依赖/生成物/tokens。

## 所有权

apps/web/src/features/ontology/{expression-model.ts,expression-model.test.ts,expression-tree.tsx,expression-tree.css,workspace.tsx,support-profile.tsx,m1-views.test.ts}；Master额外批准apps/web/src/lib/api/{g2-client.ts,g2-client.test.ts}，仅只读GET适配/测试。只读依赖为冻结g3-m5合同、生成G2 DTO、现有同源传输/权限/诊断及主题样式。源码来自本分支，其他Agent工作不撤销。

## 行为与真实检查

中间新增“高阶表达式”，实际GET固定draft/revision；右栏可输入固定Release，读取不可变版本。回包必须匹配完整scope、版本、四源hash及slot，不从导入本地源生成假树。读取竞态取消和准确hash定位、dirty禁用定位；成功快照不改源。源保留、结构只读、编辑、发布资格、推理分开；imports只引用，无推理。flat RDF引用按源隔离；有序列表原顺序，shared/cycle不无限展开，无root纯环仍展示；UI1024项/深度32上限显式提示并提供原始源后备，不伪称完整支持。textarea和Monaco安全暂停保持。v4准确23项已登记，缺失/重复/未知仍UNKNOWN。

已读Next16.4.3本地安装文档server/client边界。锁定离线restore成功；首次选择未含包的cache迅速失败，随后按旧树.modules元数据确认准确store后恢复，不联网新增包。首lint因Effect可同步setState拒绝，已改为真实异步请求完成回调后更新；目标测试、typecheck、lint最终全部exit0。目标75项覆盖版本/范围/hash负例、v4集合、blank跨源/共享/环、列表顺序、预算、HTML转义、HTTP权限与非法revision。完整产品/浏览器与Review未运行，不能以此测试替代。

## 浏览器选择器与恢复

按钮“高阶表达式”；region“草稿高阶表达式”；“刷新高阶表达式”；成功region“高阶表达式只读视图”；source details aria-label为“表达式源 ontology”（其它slot同），内ul为“ontology 只读表达式树”；原生details展开后呈现真实predicate与值。源按钮“查看 ontology 原始源码”，diagnostic按钮“定位表达式诊断来源 1”。有序成员ol“有序 RDF List 成员”。右栏折叠“读取固定正式Release高阶表达式”，input“表达式Release ID”，按钮“读取固定Release表达式”。

后续由Master合成SEM/API后运行真实高阶TTL fixture浏览器，覆盖正反权限/故障恢复/键盘/窄屏/主题与旧入口。确认全部输入稳定后按风险完成全Web检查；本切片未做昂贵full suite。
