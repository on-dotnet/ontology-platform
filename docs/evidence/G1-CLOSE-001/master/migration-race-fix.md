# 并发降级不丢审计范围

Master独占迁移路径。真实临时PG新库，写事务插入首条[a,b]范围但未提交；实际IMigrator降级，观察pg_locks确认其对目标表AccessExclusive等待，再提交写事务。旧实现Down成功并删除范围列，race-red明确失败，不用sleep猜测竞争。首次测试OID参数未显式声明导致设置失败，已区分保留，不将其冒充红例。

修复：在EXISTS之前独立MigrationCommand执行LOCK TABLE governance.audit_records IN ACCESS EXCLUSIVE MODE；与检查/Drop共用EF迁移事务。锁等待写事务完成后，后续DO新语句取得Read Committed新快照，见新范围而P0001拒绝；表锁持到事务结束，防检查后新INSERT。真实新测试验证列/数组/最新迁移历史全保留并可前向重入；完整Release46/46无跳过，原45亦全部回归通过。

表锁可能阻断读写；这里只是受批准隔离迁移恢复测试，不执行生产降级或承诺在线零停机。官方依据：[PG表锁](https://www.postgresql.org/docs/current/explicit-locking.html)、[Read Committed快照](https://www.postgresql.org/docs/current/transaction-iso.html)。
