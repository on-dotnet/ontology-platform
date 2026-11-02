# C08 精确策略增量（非作者审查 PASS_FOR_IMPLEMENTATION）

只允许合成 pg-source:5432/fixture/fixture_reader/VerifyFull，A=[production]，B=[production,public]。应用层及适配器两层同一精确有序数组判定；第三schema、反序、空、重复、注入均拒绝，不开放通用多schema配置。服务器默认策略保持原 A；仅本次产品允许上述两组固定请求。源端SQL仍只查询系统目录，不读业务行，不授新权限。

每次Probe/Discover先复制数组再校验，异步操作只消费快照；真实ACL和目录SQL用快照参数。B必须验证public存在且有USAGE、无CREATE与角色写能力，且public下无关系/函数/自定义类型；有对象则拒绝，不清空或改ACL凑通过。只读角色原全库安全检查保留。空public不增加任何业务读权限，production目录可正常返回。

真实测试：A Probe五阶段成功→PATCH B正确ETag/CAS→hash变化/revision递增/旧Probe stale/不能enable→显示名修改不复活→B新Probe绑定当前hash/SecretVersion→回A仍不能复用历史Probe。旧ETag/跨scope/第三schema/旧Probe启用拒绝；幂等重放不重复审计。数据库只读见证持久revision/hash/probe及Governance审计；结束disable并准确删除任务资源。原47项按源码影响重新评估；新增策略影响C03/P源安全和E目录，定向重测而非机械重跑全栈。

此增量仅覆盖 g4-m1-connections.md 原production-only条款的精确合成例外。G2/G3发布和数据协议保持。

Reviewer /root/final_gates_reviewer：服务器上限默认A只接A，本任务显式B才允许A/B；Host新增默认false的 G4:AllowEmptyPublicSchema，仅Development模块适用。public存在且USAGE、无CREATE与全库写权限、关系/函数/类型皆空才可读目录。PASS仅实现准入，不是运行PASS。
