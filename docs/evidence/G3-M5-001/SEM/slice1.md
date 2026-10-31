# M5 SEM 首个可编译切片

状态 DRAFT/PARTIAL，Base=3e71049。独立托管树320c，分支codex/g3-m5-sem。Owner仅新增JenaExpressions/OwlExpressionProjection/OntologyExpressions、两个约定测试文件、samples/g3/m5和本证据路径；公共合同/DI/路由/profile/既有Jena文件未改。其他开发者并行工作，未回退其变更。

真实执行：受锁restore、SemanticTests构建成功0警告0错误；仅纯投影24测试通过0失败0跳过。覆盖基数正负词法/类型/语言、qualified条件、blank前缀/共享/跨源、列表顺序/长链/断裂/分叉/纯环/共享尾链、匿名环/合法命名类环区别、未知OWL/imports、节点/深度预算和取消。纯项单测不冒充RIOT、PG或真实业务验收；Real开头的RIOT测试已编译，等待Master本轮隔离服务执行。未运行远程CI、Windows/Intel。

新入口ProjectExpressionsAsync复用原Execute/ParseSourcesAsync(checkShapes:false)，仅新snapshot blank统一_:，不改原codec/持久协议/profile/hash。成功ReadExpressionsAsync复用ReadVersionAsync授权与权威hash，读取不写源/投影/修订/新业务审计。现行发布策略仍失败关闭，读取不授予发布资格或推理。

结构预算：512主体/32表达式层/512总展开列表项，rest链不作表达式层；共享引用不无限复制。原5000 triples/源字节/5秒Execute继续有效。原始测试日志保留在本树ignored artifacts/g3-m5-sem，交付前由Master核实恢复索引/必要证据。

## 独立Review后的restriction修复

Reviewer发现literal onProperty、量词literal目标和多constructor可能误标COMPLETE，已以完整合法restriction作为正例基线修复：唯一显式类型、唯一命名属性、唯一构造；some/all目标为类/数据范围项；qualified有唯一合法限定；ordinary不混限定；匿名hasValue本版明确INDETERMINATE并保持原项。hasValue支持IRI/typed/lang literal，hasSelf仅真值。实际受影响纯Projection回归37/37，0失败0跳过，构建0警告0错误。原24项记录保留，37项是输入变化后的适用增量复验。

语法依据：[W3C OWL2 RDF映射](https://www.w3.org/TR/owl2-mapping-to-rdf/)及[OWL2结构规范](https://www.w3.org/TR/owl2-syntax/)。限制的槽位检查不声称完成OWL DL类型判定或逻辑一致性证明。XML Schema非负整数保留原词法，+01、前导零、XML首尾空白折叠及负零按值域处理，不转换为有限机器整数。
