# SEM-B 首个固定版本Diff子闭环

状态PARTIAL，Base c69a2b4297133e64ea82c869701b1c41881bf82a；Slice A main前置已完成。独立树g3-m4-sem-a，新分支codex/g3-m4-sem-b。公共合同B/存储/迁移只读。

已实现IG3VersionDiffRuntime和IG3ImpactService.DiffAsync：现有M1 Compare与新Diff复用同一次RIOT解析、图比较与5s总预算，完整四源原文/hash、真实统计、地面三元组delta同步生成；blank同构图delta为空，变化blank仅保确定地面项及两侧原文、INDETERMINATE；预算/取消全四源撤回未知，不把未解析统计写0。历史PG Revisions.SourcesJson必须与实际重算HashesJson一致；正式源沿原Catalog/RustFS/Jena读回核验并另重算bundle。

真实命令：现有semantic-roundtrip.py --postgres --filter FullyQualifiedName~G3M4VersionDiffTests --label first-version-diff，在G3-M4-001 Task标签、SEM-B证据及精确已验证canonical镜像下执行。exit0，6PASS/0FAIL/0skip。覆盖四源/BOM换行/语言/datatype、真实统计/ground delta、blank同构/差异、null词汇与空文档、取消/129blank预算、PG两个固定修订/no-op/跨asset/scope/篡改历史source拒绝。当前Master迁移G3M4ImpactReports已在真实临时PG向前应用成功。临时Jena/PG均finally准确ID回收，强no-such后验见JSON，不声明物理磁盘字节。

当前GenerateImpactAsync/ReadImpactAsync明确503 impact_implementation_pending，不返回假空报告；IImpactPublicationReader/审批四点/发布基线锁及报告幂等尚未接入。本提交仅供Master早期Diff独立Review与实际联调，不代表全B通过。下一子切片完成报告与发布，未启动M5/G4/G5。

模块Debug build0warning/0error；格式仅变更C#，最终diff-check须0。自动命令时间/输入指纹见timeline，未记录实现思考/活跃时间UNKNOWN。云CI/Windows/Intel NOT_RUN。没有新增依赖、缓存构建或全局资源操作。
