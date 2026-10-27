# M2 基础建模持久化覆盖补齐

Master要求核对附件基础子集的逐项真实PG编辑/保存/重读覆盖。原112项含label、命名公理、metadata/no-op、revision/权限/CAS等，但DraftRevisionTests缺完整基础模型顺序链路。本次只补测试，不改任何生产文件、公共合同、脚本或依赖；新增测试属于对既有功能的覆盖，不伪造RED。

新增M2BasicModelingSequencePersistsEachRevisionAndKeepsOtherSourcesExact：24次单三元组精确新增，共25个真实持久修订。覆盖A/B/C类、p/q对象属性、d数据属性、i/j命名个体及简单type、A subclass B、p/q/d命名domain/range、label@zh及comment@en、inverse p/q、disjoint A/C、p(i,j)/q(j,i)及d数据断言。示例全用独立urn:m2:basic命名空间，未加入旧Heat等SHACL target；C没有实例，互斥声明未制造示例类型冲突。最终仅宣称真实SHACL符合，OWL推理仍NOT_RUN。

每步使用独立写上下文及独立读上下文调用生产服务，不直接写表；核对新revision递增、OntologyHash真实变化、服务投影包含本步事实、PG重读源/hash一致、修订历史数量、前一修订原文不变、其余shapes/vocabulary/data源字节及各自hash保持。最终独立assessment绑定revision25、完整四源hash、当前profile v2及精确profile hash，PublishEligible=true，原revision1四源原文再次核验。

实际命令：

```sh
python3 scripts/maintenance/canonical_fuseki.py --task-id G3-M2-001 --run-id sem-basic-coverage
PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/SEM/basic-coverage G2_TEST_JENA_IMAGE=ontology-platform-fuseki:context-6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018 python3 scripts/acceptance/semantic-roundtrip.py --postgres --label basic-modeling-targeted --filter 'FullyQualifiedName~M2BasicModelingSequence'
PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/SEM/basic-coverage G2_TEST_JENA_IMAGE=ontology-platform-fuseki:context-6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018 python3 scripts/acceptance/semantic-roundtrip.py --postgres --label basic-modeling-full
```

受影响filter：1 PASS/0 FAIL/0 skip，exit0。完整真实SEM：113 PASS/0 FAIL/0 skip，exit0；两次临时解析图残余均0。canonical cache hit，未构建镜像；4个实际fixture容器准确ID、删除命令成功及删除后重验不存在见resource-lifecycle.json，未触碰旧G2资源。format实际exit0，workspace warning原文保留；最后只追加循环项中文用途注释，测试逻辑不变。

本次没有重复无关全栈/SelfTest；此前SelfTest输出保留于../slice1，当前提交的完整同HeadCI/独立Review由Master实际执行，当前NOT_VERIFIED，不用旧CI冒称新Head验证。当前Base为ecc975955ef67df91c40870838d473263117b1ce；完整冻结合同Base为9bac1ff1f1ba493af29ed386e027870fd12e66b6。
