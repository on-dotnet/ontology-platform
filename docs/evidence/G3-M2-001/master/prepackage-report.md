# 非最终生产构包预检

稳定候选3d57255eb617bbd35b4472de767dc5226cf17c49；Base=f0712e9174d1bff82b5f6959e0a61e723585be88。在完整g3-governance M2业务门禁启动前，正式V3工具已生成并独立VerifyOnly重开。此包是过程证据，不是交付包；字节保留于ignored artifacts/g3-m2/preflight/NonFinal-OntologyPlatform-Review-G3-M2-001-3d57255eb617.zip。

实际命令：`pwsh -NoProfile -File scripts/create-review-package.ps1 -BaseSha f0712e9174d1bff82b5f6959e0a61e723585be88 -HeadSha 3d57255eb617bbd35b4472de767dc5226cf17c49 -TaskId G3-M2-001 -Status PARTIAL -CiRunId 40529681102 -CiRunUrl https://github.com/on-dotnet/ontology-platform/actions/runs/40529681102 -CiCommit 3d57255eb617bbd35b4472de767dc5226cf17c49 -CiConclusion success`，exit0。未指定EvidencePath时本地检查明确NOT_RUN，只用于非最终Schema预检；最终包必须指定标准validation.json并附完整实际测试。

预期大小1945551字节；SHA256=d614844fba76667d869c14923ea74427a55f6b60d9228b780c64af3cde214241。648成员、655源码映射、1927证据索引、184变化项。没有代表截图清单，未复制PNG，仍索引精确Git恢复信息。移动前后大小/hash相同。

首次使用非标准preflight-checks.json被EVIDENCE_REQUIRED拒绝（checks/ci必须同时存在），随后实时GitHub查询遇网络错误；均无发布ZIP，原失败见同目录文件。直接只读查询实际双job成功后重试才成功，未放宽任何门禁。

为保持候选树干净，14个本任务未提交回放文件临时移动至ignored过程归档；不是排除Git扫描。预构包后已按staging-index的逐文件size/SHA256校验并准确恢复ci-point1/ci-point2，纳入最终Git证据。独立Reviewer已检查该索引。
