# R4 64KiB代码独立审查

Reviewer /root/recovery_reviewer；R4_CODE_SECURITY_REVIEW_PASS。仅限安全修复和HTTP回归，不代R3镜像/完整运行准入。

非作者核对原基线18项10PASS/8FAIL（无Content-Length超限200）及修复后18PASS/0FAIL/0skip，950ms。真实Kestrel HTTP1 fixed/chunked和HTTP2无Length，65536/65537/131072字节，两条intake/create路由。真实Cookie/CSRF与服务器Synthetic身份；handler哨兵在拒绝时零调用，因此没有凭据签发/命令/持久化路径。本测试不是PG/OIDC验收。

G4Endpoints在身份/策略/CSRF之后、JSON与应用handler之前最多读65537字节，短读循环，>65536安全413；严格JSON不变，G2/G3路径不变。C#新增局部用途注释准确。SecurityTests锁仅已有Connections项目节点；monitor只追加准确本TaskId，无系统电源更改。
