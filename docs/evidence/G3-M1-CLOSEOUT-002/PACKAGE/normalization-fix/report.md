# 原始validation metadata与规范化状态边界修复

Owner=PACKAGE，独立托管树g3-m1-closeout-package；Base=77b8ff08bba143c3ae1e8f897865ccfafcb8d8b0。修复前fetch确认origin/main=c520f4dbc236f6f8e8e427addc0a649f36de72b3。仅正式构包器、其回归、Review合同和本目录证据；不修改Master原始validation、不删除note/历史失败、不改CI或业务/资源。

## 真实触发与根因

Master在已提交Head c520f4d、真实同HeadCI run40491424804双job成功后调用正式默认V3构包器。内部重开返回 `EVIDENCE_MISMATCH: recorded statuses differ from evidence input`，未发布ZIP且自身.partial已删除。原始输出按字节归档production-failure.txt；本修复不把该次失败改写成功，旧HeadCI也不能用于之后修复Head交付。

原始master/validation.json除了权威checks/ci还有顶层note。Get-ReviewEvidence已验证checks/ci，却把包含非权威note的整个原对象返回；manifest只记录checks/ci，重开DeepEquals两侧字段集合必然不同。最小修复仅将函数返回值投影为checks/ci；所有原状态/CI/安全检查在返回前照常执行。

原始EvidencePath完整字节仍由Git snapshot处理，note及嵌套context不删除、不规范化改写。V2/V3原始payload单份映射并保留OID/hash/size恢复；V1保留历史source/证据便捷副本合同，另生成的normalized validation只有checks/ci。附加metadata中的PASS文字没有状态权限，FAIL检查与exit1/输出保留，DeclaredStatus PASS仍拒绝。

## TDD与回归

先在旧实现新增6项真实临时Git/ZIP回归（各V1/V2/V3分别覆盖raw note/context可恢复、FAIL不可掩盖/总体PASS拒绝），全部因准确EVIDENCE_MISMATCH失败，red.txt保留输出。仅改一行返回投影和中文边界说明后，针对性6项全部通过，green.txt保留输出。

完整回归实际exit0、96 tests / 0 failures，完整输出见full-regression.txt；包括原90项和新增6项。最终源码SHA256=c442424cc35e2f718b9b207993df1186ec2c21e7636855fca1e72da2a04fc2be，所有回归对应此源码；提交前git diff --check exit0。测试只证明构包器边界，所有fake gh仅限临时fixture，不代表本轮真实CI或Docker清理。Master仍须非作者限定复审、提交后新Head双jobCI、正式唯一V3构包和独立重开，不能回用c520f4d的旧CI成功。

命令：`pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1 -CaseFilter 'validation metadata*'`（RED 6失败；GREEN exit0、6通过），随后完整 `pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1`。diff-check另以提交前实际命令核验。

本次未测实现/等待/测试细分活跃工时，UNKNOWN；未重跑无关业务、Docker或UI完整验收。
