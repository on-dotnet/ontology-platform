# 独立源码复核

2026-11-13，原非作者 Reviewer `/root/p0_reviewer` 对同一工作树复核：**Source Review PASS**。最终包尚需独立重开，此结论不代替完整交付。

- 严格TLS实际握手验证、主/取消连接同工厂、固定目标与权限、取消及目录预算未发现剩余P1。
- 原driver输入绑定P1由实际执行receipt的compound SHA与运行前输入见证闭合；TLS叶证书/恢复原件、测试stdout SHA及输入交叉绑定齐全。
- auditor脱敏遗漏P2已修复，实际投影先红后绿；真实OIDC auditor GET/list脱敏及operator原值、陈旧revision409由`doris-5ad6838eec71`验证。
- 历史自然TTL与共享probe审计事务回滚仅窄复用：原件及相关方法逐字节相同，不声称Doris故障注入、Worker lease/fence或全量回滚重新验收。
- 所有供应链/在线撤销未知、CI/其他宿主架构/生产未运行继续单列。

复核结束后补齐的公开证据与最终提交绑定、工程门禁及V3由最终重开另行确认。

最终格式/using排序经原Reviewer复核无语义变化，format verify exit0，Source Review PASS维持。最终格式构建由`doris-210dd06860f3`重新执行8组生命周期，`tls-expired-f39164d081c7`真实过期证书拒绝/恢复通过。`ece86dae`门禁映射和两项用户DS_Store的单次进程准确排除亦经窄审通过；文件位置/字节保持，未修改全局Git配置。

后续policy失败仅为六份锁缺末尾LF及控制器File.ReadAllText行首启发式误报；均已修复，扫描规则未放宽。原Reviewer确认内容/行为等价并维持Source Review PASS。最新输入的真实生命周期为`doris-d36fe5954843`，最终TLS负例为`tls-expired-64c7c6371966`，以正式原件索引为准。
