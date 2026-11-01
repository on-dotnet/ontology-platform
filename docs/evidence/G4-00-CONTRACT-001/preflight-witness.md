# Preflight 原始失败与边界

输入ZIP CRC、24路径无重复/越界/symlink、Manifest22载荷size/hash、SHA256SUMS22同集合通过。初次自写校验错误假定SHA256SUMS包含Manifest，assert退出1；准确集合对照证明两清单覆盖22载荷、不含彼此，输入无缺载荷。原包verify_input后续exit0。

fetch origin exit0，origin/main/HEAD=d1a61daffe844475b07705797e3ad325cc3f2945；无漂移。原main六个未跟踪.DS_Store保留。托管create_worktree成功；git switch普通沙箱因.git refs lock权限拒绝，按已授权申请命令提升后exit0，未强制重置。

host_continuity.py preflight：2026-11-01T07:16:22.169067+00:00，AC=true、sleep=0、displaysleep=10、POLICY_READY；lockDisplayTrial/sessionContinuity=NOT_VERIFIED，externalDisplayCount=0。未改系统电源。命令内历史taskId=G3-M5-001，不当本任务连续性证据。

execution_preflight.py check --milestone G4-00：exit2，支持M1/M2/M3/M4/M5，无G4-00。按本任务LL-015不改公共工具；G4产品preflight支持留M1审批。本轮无audit/DI/Host/阶段消费者源码改动。

初次python3 verify_schema.py：exit3，NOT_RUN: jsonschema is unavailable; no auto-install。/usr/bin/python3 import jsonschema亦ModuleNotFoundError；随后用户明确批准任务隔离安装。最终真实结果另见static-results，不抹除原失败。

初次源码定位误用Contracts/.../Generated与Host单数，rg明确不存在；按实际rg路径纠正为Contracts/.../G2Models.g.cs和Hosts/.../SemanticEndpoints.cs，实际绑定见source-binding。

CI/.NET/浏览器/五源/Docker/模型/生产访问NOT_RUN；未运行不是失败或PASS。活跃Agent工时UNKNOWN。

Reviewer新增定向反例首次exit1：jsonschema FormatChecker未注册uri，原prefix允许https://、urn:及带空白的伪URI。保留此失败；补rfc3986-validator精确任务依赖、assert uri注册及非空authority/URN限制，添加三个负例定向复验；不是产品SQL执行漏洞。

最终diff-check首次返回2（input-v1.1/docs/05原文多余EOF空行、worktrees日志EOF空行）。同批shell未短路，生成7132c51但未push，不能称当时门禁通过。追加修正不改历史：input-v1.1是EOF规范化归档视图，05只移除一个末尾LF并更新派生Manifest/SHA；三个原文件逐字base64保存在input-original-bytes.json，其余21文件原样。restore-input.py恢复原24文件并验证原Manifest及原输入脚本，再运行Schema；原正式输入ZIP的hash不变。规范化不是输入合同内容变更。worktrees日志仅去EOF空行。最终全Base..Head必须diff-check0才构包。
