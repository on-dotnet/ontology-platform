# 后端独立初审

Reviewer m1_contract_review（Astra/high），固定a4e677a..dbff433后端/迁移/测试/语料。Spec FAIL/Quality FAIL，C0/I1/M0：OntologyAssessment.WrapDiagnostic将旧报告synthetic-data标记直接当data+DataHash；真实SHACL在ontology/vocabulary/data合并图验证，focus只在ontology且data为空时误定位。要求实际唯一源定位或bundle，补单源/歧义真实用例。问题不构成发布绕过。其余已审assessment事务/锁序/expiry/legacy Binding/V1-V2同批读/字节/精确预算未见阻断；SEM89/PUB53零skip证据已读，不重复测试。Query/Agent、最终组合、兼容二进制和同HeadCI另验。
