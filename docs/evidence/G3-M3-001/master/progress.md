# G3-M3 implementation ledger

Plan: docs/tasks/G3-M3-001-plan.md
Base: c8f1040829b2bfe1e9f7e36223092286975643f0

- BASE observed/fetch/doctor/locked restore/SelfTest complete; evidence files preserve original failures.
- E0/M3 text contracts independently reviewed by /root/contract_review, spec PASS after enumerated fixes; no runtime completion implied.
- New wire contracts 14 tests PASS 0skip; full old/new contract suite running.
- Human approval: official cache restore/save v6.1.0@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 only; no new billing/publish permissions.
- E0-A worker to own canonical code/tests/infra only; Master owns CI/verify/AppHost.
- M3 SEM to own Ontology module excluding migrations, semantic tests, new M3 publishing tests and samples; no shared DTO/Host/CI edits.
- Next: immutable baseline commit, independent E0-A and SEM trees; Master implements E0-C/HTTP and browser orchestration; WEB starts once slot released, must overlap SEM.
- Ruling: explicit approved user spec/execution method supplies implementation authorization; routine contract corrections do not reopen generic brainstorming approval.
- Ruling: no QUDT formal assets required for Synthetic M3; no third-party vocabulary downloaded.
- Timing before timeline tool: command durations observed in tool results; exact total step start/Agent active time UNKNOWN, do not invent.

## Resume checkpoint 2026-10-28

- Frozen public contracts 67332ca; guarded API/client/sample a1b719d. Master integrates only task branch until independent Review and CI.
- E0-A worker 28df96b (base67332ca), integrated e8b9b53/c713636/5755362. 57 tests PASS; real cold networkFAIL306582ms, no newimage, cross-run still NOT_RUN. No repeat coldbuild.
- SEM independent d9f7631/0412e17/fe0f5dd/ada0ef0 integrated 4fcdae0/ea472b2/256e31b/2f426f7. Actual finalSEM161/0skip and Publishing60/0skip. Whole-solutionformat found one test initializer missed by include-directory check; exactfile fix and fullformat verify in progress.
- WEB active independent g3-m3-web; state red-green8c7ea41 integrated fb34955. M3 UI in progress, overlapping SEM. No user files overwritten.
- Master timeline9 tests PASS including real concurrentwriters and actualCI failure exits; evidencepreflight15 checks PASS and ReviewPackage96/0 PASS (full integrated SelfTest before E0-A join, repeat required after shared changes). M3cleanup5 tests PASS; legacy+new49 tests earlier one positivefixture diagnosis failure corrected, complete rerun in finalSelfTest.
- Web frozen offline restore391 succeeded after complete approvedstore copy. lint/typecheck/Vitest139 PASS; first wrapper builds portFAIL retained, directNode Next build then isolatedpnpm build PASS. State/newM3UI checks remain to run after integration.
- Public cache usageAPI no-auth200, zeroentries/bytes; removed proposedextraactions:read beforeactivation. Only originalcontents:read and approvedrestore/saveSHA; conservative1GiBproject/512MiBarchive budgetfailclosed. Save/restore samepath and serializedproducerjob.
- No mainintegration or CIpush yet, no realSmoke or actualDockerApply yet; finalREADY/ZIP NOT_RUN.

## First CI candidate checkpoint

WEB已接174f48d/867f8ce/c660318/6cfffb0，独立只读Review无确定P1/P2，真实整栈待运行。E0完整SelfTest已结束exit0，ReviewPackage96/0；当前静态2745文件及diff-check通过。SEM初审两P2：重复集合与deprecated canonicalUnit；真实RED25/4fail，第一修正真实PG/Jena53/0skip；等价语言/字符串补充分区再RED2/2，按现有EditNoOpTriple逐步判等后真实Jena12/0skip，冻结差异定向复审中。真实参数解析13PASS，E0追加修复待独立复核。

新canonical本机真实final-source cold尝试369.176秒FAIL，两固定源各180秒NETWORK_TIMEOUT，无镜像/缓存；原始sanitized receipt保存canonical-final-source-failure.json，不重复昂贵构建。此前宿主HEAD成功不能证明容器下载恢复，后续须分析容器探测和Linux实际证据。首推仅DRAFT/PARTIAL任务分支，禁止据此READY或main集成。跨Run缓存、真实Smoke/完整M3和精确DockerApply仍待执行。
