# M5 SEM 首个可编译切片

状态 DRAFT/PARTIAL，Base=3e71049。独立托管树320c，分支codex/g3-m5-sem。Owner仅新增JenaExpressions/OwlExpressionProjection/OntologyExpressions、两个约定测试文件、samples/g3/m5和本证据路径；公共合同/DI/路由/profile/既有Jena文件未改。其他开发者并行工作，未回退其变更。

真实执行：受锁restore、SemanticTests构建成功0警告0错误；仅纯投影24测试通过0失败0跳过。覆盖基数正负词法/类型/语言、qualified条件、blank前缀/共享/跨源、列表顺序/长链/断裂/分叉/纯环/共享尾链、匿名环/合法命名类环区别、未知OWL/imports、节点/深度预算和取消。纯项单测不冒充RIOT、PG或真实业务验收；Real开头的RIOT测试已编译，等待Master本轮隔离服务执行。未运行远程CI、Windows/Intel。

新入口ProjectExpressionsAsync复用原Execute/ParseSourcesAsync(checkShapes:false)，仅新snapshot blank统一_:，不改原codec/持久协议/profile/hash。成功ReadExpressionsAsync复用ReadVersionAsync授权与权威hash，读取不写源/投影/修订/新业务审计。现行发布策略仍失败关闭，读取不授予发布资格或推理。

结构预算：512主体/32表达式层/512总展开列表项，rest链不作表达式层；共享引用不无限复制。原5000 triples/源字节/5秒Execute继续有效。原始测试日志保留在本树ignored artifacts/g3-m5-sem，交付前由Master核实恢复索引/必要证据。
