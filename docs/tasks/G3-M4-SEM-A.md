# G3-M4-SEM-A

状态：AUTHORIZED / WAITING_FOR_DISPATCH。公共合同A已独立Review FROZEN。公共合同基准af5ae2f；实际派工头取本卡同提交，主阶段Base3992582e03df1a103fac36e7e82b8c81f85f622e。

Owner：/root/sem_a；Reviewer：非作者只读Agent（实现完成后实际登记）；Master唯一main集成者。实际托管Worktree：`/Users/chasen/.codex/worktrees/g3-m4-sem-a/ontology-platform`；任务分支`codex/g3-m4-sem-a`。仅Slice A，不启动B/M5/G4/G5。

owned_paths：backend/src/Modules/Ontology/**（排除Migrations）; backend/tests/OntologyPlatform.SemanticTests/G3M4*.cs及直接受Current v4影响的既有测试; backend/tests/OntologyPlatform.PublishingTests/G3M4*.cs及直接受Current v4影响的既有测试; samples/g3-m4/**; docs/evidence/G3-M4-001/SEM/**。read_only_dependencies：公共合同/Contracts/Host/g2-client/生成物/锁/CI/AppHost/Tokens/迁移/其他worker路径。公共Owner Master。你不是唯一Agent，不回退他人更改，跨路径先提议Master。公共文件不在本任务写入范围。

验收命令：dotnet build; affected Semantic/Publishing tests with genuine PG/Jena/RustFS via existing acceptance fixtures; format changed files。负例：范围/跨厂同号/重叠/未知/历史删除与扩张/陈旧CAS/幂等冲突/取消/旧profile回滚。所有实际命令/exit/测试数/输入fingerprint与timeline放自身证据；日志先ignored再归一LF，禁止把未运行标PASS。先最小可运行API或UI子闭环及时commit/push DRAFT，再由Master组织独立Review和真实集成，不等全部功能完成才联调。新资源登记TaskId/RunId/准确ID/用途/TTL；禁止全局清理或重启。

停止条件：共享合同歧义回报Master、未批准依赖/费用/权限/不可逆只停对应项；受影响失败先廉价短复现，禁止同指纹重复整栈。不得借本卡覆盖附件非目标。
