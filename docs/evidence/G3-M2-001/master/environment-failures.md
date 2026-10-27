# 环境与失败分类

合同检查点9bac1ff，CI40519729967：engineering成功，governance-integration在canonical Fuseki Dockerfile RUN下载阶段TIMEOUT600s，receipt的输出hash/有限stage保留在contract-ci-failure.txt。业务PG/Jena/发布/查询/Run未启动，不能算业务FAIL或PASS。未延长预算，未盲重跑整栈；后续新稳定Head实际CI另查。

一次沙箱内 node --test scripts/tests/G3ReadBackpressure.Tests.mjs exit1，6项均listen EPERM 127.0.0.1，分类ENVIRONMENT_PERMISSION；相同命令申请本地socket所需执行权限后6/6/0skip exit0，backpressure-green.txt保留，不改代码或预算。

SEM一条尚未执行的后续回归命令被自动审批拒绝，理由误认为会写旧G2证据。Owner确认没有源码/容器变更；Master只读核实evidence_paths明确优先PLATFORM_EVIDENCE_DIR并拒绝越界/链接。后续全链必须明确M2证据根，不能绕过拒绝或调用旧身份清理。
