# SEM 独立Review no-op纠偏

Reviewer提出literal合法表示差异可能造成RDF未变但原文被重写；Master明确授权仅同根真实核验/修复。测试先于生产改动：language+datatype缺席/规范langString、plain/显式xsd:string、语言tag大小写，各重复新增/精确替换，共6项真实RIOT全部RED（exit2、0skip），详见literal-noop-red.json。

最小修复仅在最终no-op图集合判定使用规范副本：语言转小写且比较类型langString；无语言且datatype缺席的string按xsd:string比较。不归一化任何typed literal的数值词法，不修改权威SourceBundle或实际导出三元组；oldObject的record精确Remove不变。新测试同时证明等价但非精确的oldObject全部edit_source_conflict，不能扩大删除匹配。

修复后完整真实PG/Jena测试112成功、0失败、0跳过、exit0，临时解析图残余0，详见literal-noop-full-green.json。format实际exit0，workspace warning原文保留。新3个fixture容器准确ID及删除后重验见resource-lifecycle.json；没有修改或删除旧G2资源、依赖、公共脚本或合同。

复现：

```sh
PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/SEM/review G2_TEST_JENA_IMAGE=ontology-platform-fuseki:context-6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018 python3 scripts/acceptance/semantic-roundtrip.py --postgres --label m2-noop-review
```

SelfTest在前一源码版本905d3ca已经完成96个ReviewPackage及其它维护回归，完整输出见../slice1/selftest.txt；本补丁后同HeadCI/SelfTest由Master实际执行，当前NOT_VERIFIED，不用旧SelfTest冒称新HeadCI。独立Review/集成/最终M2验收仍待Master，无下阶段授权。
