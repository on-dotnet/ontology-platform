# SEM implementation report

本报告按切片保留原时点事实；最新本地验证见末节，早期PARTIAL/失败不作改写。

状态：DRAFT/PARTIAL，最早API/runtime + SKOS真实子闭环。Base=67332cace3d134e31b723226071f1d630453cd59；branch=codex/g3-m3-sem。

四源RIOT投影、source-aware原子1..64 batch、全hash/CAS/幂等/审计复用ontology.edit、正式Catalog+原对象+Jena ReadVerified消费路径、profile v1/v2保留及v3、SKOS S13/S14/S46和域政策已实现。M3精确诊断直接进入GOVERNANCE；OWL_REASONING=NOT_RUN；新deploy/verify/read v3同政策，历史不追加。单位语义下一切片待完成，当前任何P元数据保守warning阻断，不宣称单位完成。

实际限定模块测试：first-pg-jena.json/log，20测试通过/0失败/0skip，真实临时PG/Jena，全部暂存图清零、脚本自身随机容器已删除。first-slice 3/3；green-skos 18/18；green-profile 2/2。RED保留：原接口/profile行为2失败；SKOS缺失14失败/1pass；assessment与新audit动作2失败，修复时复用既有ontology.edit。初始sealed cast编译失败、错误过滤零测试exit8也保留，不作为PASS。

未运行：M3正式整栈、最终同HeadCI/Review/ZIP（由Master在E0门禁后组织）；Synthetic单位完整性、历史v2发布负例和全SEM回归仍待下一切片。无新增依赖/词表下载，无迁移/Contracts/Host/scripts/Web写入。资源使用canonical共享context-1e45镜像，只创建脚本临时容器且全部回收；未动旧资源。

## 第二切片：Synthetic单位治理

继续既有d9f7631，不重做前成果。新增samples/g3-m3/units.ttl明确Synthetic K/℃/MPa/t、三类七维量纲、量种、版本化标准来源和属性绑定；没有QUDT资产、转换因子、新依赖或新表。单位/来源各字段恰一、多值失败、七维xsd:integer -32..32、精确量种/量纲IRI和属性三字段绑定完整检查；仅绑定元数据出现时要求完整，不对旧普通属性强加单位。未知precision保留warning，由GOVERNANCE=INDETERMINATE阻断。

RED red-units.json实际19用例18失败/1通过/0skip；GREEN green-units.json真实隔离Jena 19/19通过、0skip，暂存图清零并删除脚本自身容器。初次测试转义编译失败red-units-compile.json保留。格式使用backend/OntologyPlatform.slnx exit0（workspace加载warning），diff-check exit0；首次误用根solution路径的失败仅记本地日志。新切片尚未完成全SEM/PG/publishing真实回归与独立Review；正式M3整栈须等待E0门禁，由Master组织，当前仍DRAFT/PARTIAL。

## 第三切片：真实评估、发布防绕过与历史v2

complete-m3-sem.json：真实隔离PG/Jena，M3专项46/46通过、0skip。新增单位治理三态与SHACL/SUPPORT/OWL_REASONING独立阶段验证；v3 Deploy/Verify/ReadVerified直接调用同样阻断精度未知、量纲错配与SKOS缺陷；精确LegacyM2不追溯套v3政策。Master授权消费a1b719d公共API及g2样例scheme（本树cherry-pick=19df148）后，full-sem.json完整159/159通过、0skip，34.759秒。

m3-publishing.json：真实临时PG/Jena/RustFS，4/4通过、0skip。覆盖完整Synthetic单位异人审批发布、原始对象及Jena正式消费、固定Release词汇读取与后续草稿隔离、缺厂授权零外调、SHACL成功但治理拒绝提案、精确旧v2 Catalog/原始manifest字节读回和异人审批CAS回滚、旧v2 assessment拒用于新发布。Master额外批准旧PublishingTests/G3LegacyTests唯一当前profile断言2→3，旧fixtures及旧profile/hash不变。SEM G3BoundaryTests当前服务profile断言同样升级3，独立1/1通过。

发布入口首次因缺project.assets未运行，m3-publishing-prerequisite.json保留。标准locked restore在网络审计等待后主动中断exit130；随后--locked-mode --ignore-failed-sources -p:NuGetAudit=false用已有依赖恢复exit0（本地NuGet审计NOT_RUN，不能冒称安全审核PASS），真实编译0warning/0error。无新依赖/lock变化。格式及diff-check exit0。SelfTest首次仅受ignored过程日志CRLF与缺隔离YAML库阻断，Master批准复用其.tools/pythonlibs后重跑；原日志散列和规范化类别保留process-log-normalization.json，失败事实不改。最终SelfTest状态待本轮实际结束回执。

所有脚本自身随机容器均实际删除，临时验证图计数清零，不清理旧G2资源。当前仍DRAFT/PARTIAL：独立Review、Master集成、正式整栈/E0门禁、同HeadCI与唯一ZIP由Master组织；未push/merge，未启动下阶段。

## 最终本地验证与交接

StandardSource的Synthetic/PROV缺陷先用red-source-path.json真实2/2失败复现；修正后分别定位p:synthetic及prov:wasDerivedFrom，不再指向version。final-sem.json完整真实PG/Jena **161/161通过，0失败，0skip，32.851秒**；full-publishing.json完整真实PG/Jena/RustFS **60/60通过，0失败，0skip，27.821秒**，包括原G2/M1/M2发布故障/审批/回滚及新增M3。全部脚本自身随机容器实际rm成功，SEM临时验证图清零；保留原基线full-sem.json的159测试事实。

最终本地format --verify-no-changes exit0（workspace加载warning），git diff --check exit0。verify -SelfTest第二次exit0，ReviewPackage96/0；工程测试不能替代前述真实产品测试。selftest-initial.txt保留首次失败，selftest-final.txt为第二次实际完整输出，统一LF/最终单LF；verification-commands.json记录命令/退出码及原日志散列。SelfTest未替代Master最终提交Head同CI；普通restore网络等待的exit130及本地NuGetAudit=NOT_RUN事实保持。

本地交付范围完成，状态仍DRAFT/PARTIAL等待Master独立Review及集成关口。任务分支codex/g3-m3-sem，工作树保持；未push、未merge、未创建ZIP。已消费Master公共提交a1b719d（本树19df148），Master无需重复集成该副本。Master后续仅按明确授权组织E0后正式整栈、同HeadCI、V3唯一包与独立重开。没有QUDT正式资产/新依赖/换算功能、没有运行下阶段。
