# M2公开历史有限复核

实际只读命令 `python3 scripts/maintenance/audit-public-history.py`，exit2（REVIEW_REQUIRED，不能冒称扫描器exit0）。389提交、3188唯一blob、102124714扫描字节，六项路径/类别/blob与PRE-G3-CLEANUP-FIX-002/public-history-c3.json逐项集合完全相同，遗漏0；没有新增命中。不输出原值、不读取ignored凭证、不改历史。

既有独立逐blob审查结论保留：bootstrap-keycloak.py三个blob为环境引用/运行时随机生成表达式，无字面真实凭证；verify-alloy-boundary.py三个blob为Docker标准宿主别名与本地合成Sink测试。准确OID和类别在public-history.json，历史独立依据见docs/evidence/PRE-G3-CLEANUP-FIX-002/public-history-triage.md。

限定有限模式+准确既有triage匹配PASS；任意混淆、语义隐私、未获取远端/不可达对象NOT_VERIFIED。本地refs/codex辅助快照不能等同已公开对象。此次没有读取卷/私有runtime内容，也未触碰远端历史。
