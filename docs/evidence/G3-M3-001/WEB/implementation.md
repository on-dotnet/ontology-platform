# G3-M3-WEB 实施与验证（PARTIAL）

Base=a1b719d；分支 codex/g3-m3-web；独立托管树 g3-m3-web。状态切片8c7ea41已先提交。所有权仅 ontology切片、新增M3浏览器tests、WEB证据；Master另明确允许旧workspace.spec.ts精确同步默认source/显式graph/canvas。没有修改共享client/生成类型/锁/脚本/Tokens。

## 实现

- E0-B显式source初始/open/new，graph/source保持选中IRI，窄屏panel显式；原导入竞态宿主补齐真实reducer调度。
- 中文SKOS目录搜索、多语言名称/别名/隐藏标签/编码/定义、Scheme/层次/对齐/废弃；保留多值、同名不同IRI和全部四源引用。
- Synthetic单位版本、canonicalUnit、quantity kind、量纲IRI及七项整数指数、符号、精度、标准来源/原始引用、属性nominalUnit均有明确受控字段。只编辑显式RDF，不推断身份或换算。
- 精确源批次1..64，旧对象保留kind/value/language/datatype；真实editVocabulary携带完整四源hash及同revision Command/If-Match。原始shapes/data/空白节点和未知字段只读。未保存源码、只读、busy、未知profile能力均阻断结构写入。
- 待提交批次切view保留，源码编辑与资产导航阻断，取消明确；409保留队列。保存后同工作区接受新revision、重置assessment、读取真实Diff，再走既有评估/发布/异人审批。
- 历史Release按精确ID走releasedVocabulary，要求回包releaseId/manifestHash；profile由服务端manifest提供，缺失显示LEGACY_G2 / UNKNOWN。迟到/卸载/输入改变请求取消；词汇快照需draftId/revision及全部hash匹配。

## 实际验证

2026-10-28。命令均在本树apps/web，除注明根目录外；日志统一LF。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 本树锁定依赖恢复 | PASS，391包；CI=true且绝对store路径离线install exit0，重建本树shim | install.txt |
| 状态合同 | 缺失模块RED，实施后3/3 PASS | e0-state-red/green.txt |
| M3模型合同 | 缺失模块RED，实施后4/4 PASS | vocabulary-red/green.txt |
| M3组件合同 | 缺失模块RED，实施后2/2 PASS | views-red/green.txt |
| node node_modules/eslint/bin/eslint.js . | PASS，exit0 | 空输出，命令实际已运行 |
| node node_modules/typescript/bin/tsc --noEmit | PASS，exit0 | 空输出，命令实际已运行 |
| node node_modules/vitest/vitest.mjs run | PASS，16文件/148项 | tests.txt |
| NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build | PASS，exit0 | build.txt |
| node apps/web/scripts/generate-types.mjs --check（根目录） | PASS，exit0；无生成漂移 | 空输出，命令实际已运行 |
| 新增M3 Playwright三场景 | PASS，1440/390精准发包/队列/409/历史档案，5.2秒 | browser.txt |
| git diff --check（根目录） | PASS，exit0 | 提交前检查 |
| verify -SelfTest | RUNNING，另交后置日志 | 不预填完成 |
| 真实PG/Jena/RustFS/Keycloak完整M3浏览器 | NOT_RUN（本worker）；Master整栈门禁 | 不能以有界UI夹具替代 |
| 同HeadCI / 独立Review / V3最终包 | NOT_VERIFIED；Master集成后执行 | 本worker不push/merge |

首次全量Vitest因旧TSX夹具未模拟useReducer而13项失败；补齐调度后148项全过，未改变原13项断言。该首次原始日志在后续运行中被覆盖，本记录保留失败事实。首次有界浏览器两项因getByRole(alert)同时匹配Next路由播报器失败，原始日志见browser-initial-fail.txt；精确选择.g2-notice[role=alert]后3项通过，无超时放宽。

## 操作入口

草稿→变更理由→“术语与单位”。目录选IRI；表单逐项“排队登记资源类型”/“排队添加字段”，或展开“精确替换 / 删除已保存字段”后“编辑字段N”→“排队精确替换”。“批量原子提交”保存真实修订；“取消待提交批次”明确取消。右侧“固定词汇Release ID”及“读取固定Release词汇”显示不可变正式来源。继续真实评估及原/release审批链；没有自动批准。

## 保留与停止

没有新Docker/付费/第三方资产；复用的.tools缓存与node_modules仅本树开发依赖，保留至集成验证完成再按Master白名单回收。原G2资源、私有runtime/PFX、全局配置均未读取或修改。只交M3+E0-B候选，不自动进下关口。

## 后续自审修复（2026-10-28）

- 本地队列取消不应被空理由/失去写权限阻断：新增浏览器断言先真实FAIL，修复取消/本地移除仅在命令busy时锁定；1440/390均PASS。cancel-red/green.txt保留。
- 网络失败后的相同批次显式再次提交复用原Command与幂等键；更改理由或任何载荷后才创建新命令。实际workspace事件测试先FAIL再PASS，含原13项文件导入竞态。retry-red/green.txt保留。
- 缺少单源hash的响应不能仅凭bundleHash匹配：新增断言先FAIL，固定检查全部5项hash，完整149项Vitest通过。hashes-red.txt保留。
- 最终源码验证：lint exit0、typecheck exit0、16文件149项Vitest、Next production build exit0、新增3项有界浏览器4.7秒PASS。tests-final/build-final/browser-final.txt保留；此为后续修复后的最新结果。
