# G4-M1-RECOVERY-001 交付入口

结论：G4_M1_RECOVERY_BLOCKED_WITH_WITNESS。源码分支codex/g4-m1-recovery-001，Base59edb405dfb4acf4d4a259cffdc3551bafa90d2c，TestedCommit4efbeca1cbf33d52c2bd950e1968db20abe322d5。准确DeliveryHead见本包Manifest及包外重开回执；不在内容内伪造自引用Head。

先读acceptance-matrix.json（原49条要求完整保留）、validation.json、r5-independent-review.md、resource-closeout.md及r3-review.md。冻结时45PASS/4NOT_RUN：C08有效SourceConfig变更、R04真实G3发布/查询是授权阻断；P08本包自身秘密扫描及R05唯一包重开只能由包外实际回执闭合，不能在构包前宣称已执行。所有历史真实失败、修复与输入哈希保留；不以组件绿替代产品运行。

源码包括无Content-Length/chunked/HTTP2的64KiB实际读取上限、PG类型权限守卫、快照STALE、超时/客户端取消区分、授权诊断展示、父子UI互锁与相对OpenAPI。18真实Kestrel安全、120合同通过/1G3环境跳过、109UI组件、完整真实HTTP/UI及专项故障证据各有边界。四镜像均逐项AMBER-A1/LICENSE_PARTIAL，仅内部合成非分发，不是商业部署许可证确认。Windows原生/远程CI=NOT_RUN。

C08最小解除条件：明确批准第二个准确受控合成profile，或ChatGPT复审裁定固定profile阶段此子项不适用。R04最小解除条件：明确批准准确附加G3镜像/预算/隔离合成输入，或提供已准入可复用且不涉及正式数据的准确现成环境。不得自行扩范围。

资源已按白名单真实收尾，原资源/数据/活动树保留；默认bridge历史ID漂移原因UNKNOWN单列，不掩盖。最终唯一V3、ZIP SHA256/Manifest及独立重开/敏感扫描在包外回执绑定。完成后停等ChatGPT独立复审，不合main，不改G6，不进入G4-M2。
