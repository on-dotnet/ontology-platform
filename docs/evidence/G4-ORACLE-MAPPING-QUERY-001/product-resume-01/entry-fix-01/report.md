# Oracle 单表执行入口修正与 S1 实测记录

任务为 G4-ORACLE-MAPPING-QUERY-001，产品 Run 为 product-resume-01。Base 为 `326c7e1fd97f2327a25fa510071115d9eee7c5bb`。持久替代资源仍归 implementation-01。

## 修复前的实测原件

| 边界 | 运行见证 | 证据 |
| --- | --- | --- |
| R1 | 三个实际模式的 JS ready 传入当前产品 Run，Python 在首次外部读前错误拒绝 | 独立树原始命令 `c0e987b7863741e8aed067bc63a9e3bd` |
| R2 | 旧 Python 传入的 ready.json 路径不符合已编译 C# 要求的 session-ready.json 路径 | 同一命令，修前记录 SHA-256 `513136708f9b3bf09ea02816fbf7aad4320dff7821811b84c082e16f9d4d4723` |
| 读取完成后的取消结算 | 旧实现第 1001 ms 仍调用 CAS，当时原总期限余 3999 ms。测试驱动核验了实际旧程序集，未使用真实 PG 行锁 | 独立旧见证命令 `f0695c47eb2943e8adac224e3b9a8001` |
| R3 | 已审冻结替代卷的两次全读为默认图 0、命名图 1372、发布图 46 和 1326 条。历史关闭钩子 UNKNOWN | 6.2.0 上游提交 `d0676a2c402ead68a133596f4ac5977be64dd251`，新停止/重开入口初次离线回归 `f0dc642b5662496a995121fa85aacb8f`，14/14 |

以上为早期精测使用的代表材料。Oracle S0 的 AC03-B 仍为 BLOCKED，cleanup250ms 为 NOT_QUALIFIED，G4 为 PARTIAL。
