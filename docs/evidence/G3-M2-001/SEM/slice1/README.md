# G3-M2-SEM 首个纵向切片

状态：PARTIAL / 待独立Review及Master同HeadCI。Base=9bac1ff1f1ba493af29ed386e027870fd12e66b6。只改Ontology模块、SemanticTests及SEM证据；不改公共合同、依赖或发布生产模块。

实际验证：`m2-semantic-full-fixed.json`记录完整真实PG/Jena SemanticTests=106成功、0失败、0跳过，exit0；临时解析图残余三元组0；全部fixture容器精确删除并重验不存在。`m2-slice1.json`为11项最小slice PASS。canonical共享镜像cache hit，未执行docker build。真实迁移首次查询历史表不存在的EF诊断不影响随后成功迁移。

生产变化：原v1完整工厂移至LegacyM1，golden hash保持54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86；Current同ID版本2，09–11 BASIC；Matches仅接受登记v1/v2精确hash。命名等价/互斥两端显式Class，逆属性两端显式ObjectProperty；编辑前后全图检查，删声明不能遗留非法公理。IRI元数据及冲突literal失败关闭，规范langString+language可精确操作；旧非法surrogate错误码保留。WrapDiagnostic直接携带真实SourceShape。

真实PG验证覆盖四源非ontology字节/hash不变、保存及重开、no-op新修订/原字节、当前assessment绑定、权限、stale CAS、类型失败、旧assessment拒绝。既有106项包括复杂图、RIOT/SHACL、预算、历史修订与发布冻结入口。历史profile正式发布/回滚扩展将在下一测试切片继续，不能把此状态提升为最终M2完成。

RED保留于../red：9项中8项预期失败；PG测试首次API拼写编译失败后已修正并观测真实命名编辑失败；SourceShape 4项真实失败。完整回归首跑104成功/2失败，是统一错误码映射覆盖旧surrogate码，收窄映射后106/106成功。环境SelfTest首跑缺隔离PyYAML，复用既有项目隔离parser后重跑仍进行中，未在此预填PASS。

复现（已locked restore）：

```sh
python3 scripts/maintenance/canonical_fuseki.py --task-id G3-M2-001 --run-id sem-review
PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/SEM/review G2_TEST_JENA_IMAGE=ontology-platform-fuseki:context-6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018 python3 scripts/acceptance/semantic-roundtrip.py --postgres --label semantic-review
```

源码format实际运行exit0（workspace warning详见format.txt），最终`git diff --check` exit0。本切片墙钟及活跃工时UNKNOWN；canonical UTC与资源重验UTC取真实回执。CI/独立Review/main集成由Master后置记录，当前NOT_VERIFIED。
