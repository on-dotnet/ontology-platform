# 266操作实际白名单独立资源审查

cleanup_review对草案完整实际资源只读审查 C0/I0/M0，范围/证据/保护PASS；Apply需同HeadCI/main一致和fresh全量DryRun成功后放行，不把草案审查当实际删除。

- 175 cache：实际fingerprint、类别/私人名称拦截、3个归档小文件原始bytes、全部ignored覆盖、共享链接顺序通过。9根symlink仅unlink，不递归目标；保护树工具link无指入候选。
- 10 worktree：实际干净、commonRepo、HEAD/branch、locked/保护均通过。当前16树=10候选+6保护。g2-ai外部absent，31操作撤回不计回收。
- 11 local/13 remote：拟main b9322e5祖先检查；13真实远端tip吻合，gh开放PR=[]，effective fetch/push均官方URL。
- 57 Docker：2停止container、24准确volume、13准确image、18history逐项实际身份/引用preflight通过。live11容器=旧2+恢复探针新9；新增项不在白名单。
- 13 image→18 history有限OCI投影独立重跑18CLI，13IDs全覆盖。Wave2两组原handoff与任务前de2 blob逐字节相等，加上随机合成fixture和6卷生成器证明归属，不仅名称前缀。

草案SHA256 9b87b44802ca584c0b22016963558414698ac578832539be31af18f1c9bb0a4e；资源/保护冻结规范hash a93aa9b012b86e7faa899eb2f87d326b2b34851b555a363fa9408e1e8c2cca40。仅删除可刷新顶层expectedMainSha/createdAt/expiresAt及各ownershipEvidence.commit后，按json.dumps sort_keys=True,ensure_ascii=False,separators=(',',':') UTF8 SHA256。正式Apply只允许刷新这几项；任何ID/tip/fingerprint变化须重新审查，不能静默替换。

cache逻辑2530247461 bytes不等于物理回收。Reviewer无资源/refs/文件变更。正式精确计划、DryRun、实际执行和after须另归档并独立验收。

正式门禁闭环：实际main/HEAD/origin-main及live main均b9322e599aabac6fac8ed8a6f4ceeae767d1323b；CI40355496041 completed/success，engineering121687568150和governance121687567605均success。正式plan SHA2561ee60b336c3eb823bd2d8b5db0f41845b08f99d6432805e4d7162a59c22cc0d4，frozenHash未变；created16:17:07Z至次日00:17:07Z，8小时有效。fresh默认DryRun实际exit0、validated266/completed0，独立Reviewer读取原文件及再次plan hash核对后放行C0/I0/M0。最初入口漏Root由PowerShell强制参数校验exit1、未进engine/无资源副作用；补精确Root后完成。正式Apply仍须以实际日志/after结论为准。
