# SEM implementation report

状态：DRAFT/PARTIAL，最早API/runtime + SKOS真实子闭环。Base=67332cace3d134e31b723226071f1d630453cd59；branch=codex/g3-m3-sem。

四源RIOT投影、source-aware原子1..64 batch、全hash/CAS/幂等/审计复用ontology.edit、正式Catalog+原对象+Jena ReadVerified消费路径、profile v1/v2保留及v3、SKOS S13/S14/S46和域政策已实现。M3精确诊断直接进入GOVERNANCE；OWL_REASONING=NOT_RUN；新deploy/verify/read v3同政策，历史不追加。单位语义下一切片待完成，当前任何P元数据保守warning阻断，不宣称单位完成。

实际限定模块测试：first-pg-jena.json/log，20测试通过/0失败/0skip，真实临时PG/Jena，全部暂存图清零、脚本自身随机容器已删除。first-slice 3/3；green-skos 18/18；green-profile 2/2。RED保留：原接口/profile行为2失败；SKOS缺失14失败/1pass；assessment与新audit动作2失败，修复时复用既有ontology.edit。初始sealed cast编译失败、错误过滤零测试exit8也保留，不作为PASS。

未运行：M3正式整栈、最终同HeadCI/Review/ZIP（由Master在E0门禁后组织）；Synthetic单位完整性、历史v2发布负例和全SEM回归仍待下一切片。无新增依赖/词表下载，无迁移/Contracts/Host/scripts/Web写入。资源使用canonical共享context-1e45镜像，只创建脚本临时容器且全部回收；未动旧资源。

## 第二切片：Synthetic单位治理

继续既有d9f7631，不重做前成果。新增samples/g3-m3/units.ttl明确Synthetic K/℃/MPa/t、三类七维量纲、量种、版本化标准来源和属性绑定；没有QUDT资产、转换因子、新依赖或新表。单位/来源各字段恰一、多值失败、七维xsd:integer -32..32、精确量种/量纲IRI和属性三字段绑定完整检查；仅绑定元数据出现时要求完整，不对旧普通属性强加单位。未知precision保留warning，由GOVERNANCE=INDETERMINATE阻断。

RED red-units.json实际19用例18失败/1通过/0skip；GREEN green-units.json真实隔离Jena 19/19通过、0skip，暂存图清零并删除脚本自身容器。初次测试转义编译失败red-units-compile.json保留。格式使用backend/OntologyPlatform.slnx exit0（workspace加载warning），diff-check exit0；首次误用根solution路径的失败仅记本地日志。新切片尚未完成全SEM/PG/publishing真实回归与独立Review；正式M3整栈须等待E0门禁，由Master组织，当前仍DRAFT/PARTIAL。
