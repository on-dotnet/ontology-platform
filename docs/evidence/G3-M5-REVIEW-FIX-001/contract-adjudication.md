# G3-M5-REVIEW-FIX-001 合同裁决

状态：UI_CLARIFICATION，非作者动源码前审查 PASS，见 contract-review.md。Base=580d73e7c0fb38b94dbbed1136ee0b1d24fadc9d。

A. OwlExpressionSnapshot.profileId/profileVersion/profileHash 表示现行支持策略；projectionVersion 表示独立只读投影协议。冻结 g3-m5-contracts.md「读取与持久兼容」明确区分 v1/v4，G2Models.g.cs:3570–3596 注释与之相同。OntologyExpressions.cs:23–36 在权威源读取后使用 SemanticProfile.Current()，与合同一致。

B. v1/v2/v3 Release 的表达式读取应恢复历史源及完整 scope/hash，但快照策略是当前 v4。OntologyAssessment.cs 的 ReadVersionAsync 返回 manifest.Semantics 且保留历史源；表达式用例有意不把它当当前策略。OntologyVocabulary.cs 的 ReadReleaseVocabularyAsync 则明确返回 manifest.Semantics 历史 Profile，并按版本筛诊断；两者是不同 DTO/用途，不得互换。G3M5ServiceTests.RealReadOnlySnapshotPreservesRawBytesAndDoesNotWrite 断言 Current().Hash、v4、projection v1 和无写副作用。以上是合同/代码证据，不冒称本轮已运行历史 Release 后端测试。

C. 无 Semantics 的旧 Manifest 未承诺表达式快照输出历史 Profile。不得为该字段虚构 UNKNOWN 历史元数据，亦不得把现行 v4 写成旧发布事实。历史 Manifest/Run/SSE/Profile/hash 全部保持原语义和字节。

D. 原“SemanticProfile.Current() 导致历史 Profile 错误”的 P1 判定不成立，本轮建议撤销后端 P1，降为前端 P2 展示歧义（最终裁决交 ChatGPT 复审）。ExpressionReadView 紧接“固定正式 Release/固定草稿”显示裸 profile v4，且不显示 projectionVersion，读者可能误以为该策略随历史版本固定。选择 UI_CLARIFICATION：仅把标签明确为“当前平台支持策略 Profile”，单列“只读投影协议版本”，分别说明不是选中 Release 发布时/草稿修订保存时的策略快照。保留实际 Profile/hash、版本 ID、源、权限、预算和 HTML 转义。无 API/DTO/生成物/后端/依赖/令牌变更；无需合同更改，无数据迁移、兼容破坏或新写审计。

E. 必须由非作者 Reviewer 先核对本裁决与上述源码，再实施两个前端文件的最小修改。测试新增 RELEASE/DRAFT 真实组件渲染正反例；定向真实浏览器验证两种读取链，其他已通过后端结果仅按精确 Git 输入绑定复用。审查结果另附，不能以本文件自评替代。
