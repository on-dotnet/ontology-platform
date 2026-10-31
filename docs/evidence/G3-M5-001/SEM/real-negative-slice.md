# M5真实RIOT最小负例增量

范围封顶：只改G3M5ExpressionTests.cs及本证据；不改产品实现、不启动容器、不重复已有完整Semantic或PG验收。

新增两个Real前缀方法，共6项实际发现用例：

- RealRiotRestrictionNegativeShapesPreserveSourceHash，5个DataRow：缺onProperty、someValuesFrom literal、allValuesFrom literal、qualified cardinality的onProperty为literal、两个互斥constructor。
- RealRiotNodeBudgetPreservesSourceAndFailsClosed，513个不同命名主体/513条Class声明，远低于5000 triples和256KiB源预算，单独触发512节点结构预算。

全部通过既有SemanticFixture.Runtime及IG3ExpressionRuntime生产RIOT入口；restriction预期INDETERMINATE及restriction_invalid，预算预期expression_budget_exceeded及512节点有限结果。每例独立计算输入UTF8 SHA256并核对sourceHash，断言sourcePreserved=true、readOnlyStructured/editable/inferred=false、publishEligible=BLOCKED，不用合成解析三元组代替真实输入。Turtle语法按源码人工静态核对：标准完整prefix、合法IRI/typed或plain literal、标点闭合；反例针对OWL槽位而非损坏RDF语法。真实RIOT执行由Master在现有harness精确执行，本worker尚未运行，不预填PASS。

实际短验证：SemanticTests构建exit0/0警告0错误；直接MSTest应用--list-tests按下列filter真实发现6项、exit0（47ms）；仅owned文件dotnet format --verify-no-changes exit0；git diff --check exit0。

精确增量filter：

```text
FullyQualifiedName~RealRiotRestrictionNegativeShapesPreserveSourceHash|FullyQualifiedName~RealRiotNodeBudgetPreservesSourceAndFailsClosed
```

Master入口为既有semantic-roundtrip.py --filter <上述filter> --label g3-m5-real-negative，无需--postgres。实际运行需本轮TaskId/证据路径及已验证canonical image，不能沿用旧默认tag。不会因此重跑先前296项。

保留一次便宜参数探测失败：dotnet test --project ... -- --help触发锁定SDK的Unexpected help IPC FailFast，未执行测试，原日志在本树ignored artifacts/g3-m5-sem/test-help.log；该命令单独exit未捕获，不假报数值，不计为产品失败。随即改为直接已构建测试DLL的--help核实支持，再用--list-tests发现6项；原失败不删除，不重复相同命令。新增用例执行状态NOT_RUN，CI/Windows/Intel NOT_RUN。
