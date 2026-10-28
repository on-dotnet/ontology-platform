# G3-M3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement each approved task.

**Goal:** 完成已批准M3术语/单位闭环和E0可测量效率治理。
**Architecture:** 四源RDF仍为唯一语义权威，复用现有草稿CAS、评估、发布、查询和历史兼容。工程先快速失败，再真实服务和跨CI证明。
**Tech Stack:** 已锁定.NET10/EF10、Jena6.2.0、PostgreSQL/RustFS/Keycloak、Next16/React19、Python标准库/PowerShell；无新增直接依赖。
**Spec:** ../evidence/G3-M3-001/authorization-v1.md

## Global Constraints

只M3+E0；禁止M4/M5/G4/G5、通用换算、收费LLM、自动批准、生产写入。QUDT未经批准只Synthetic fixture；新外部依赖/镜像发布权限/费用先审批。Master公共合同单写，独立写Agent独立托管树/分支，总并发3。历史失败、profile/hash、Release/Run/SSE字节不改。

## Review Focus

- 跨架构缓存不可误复用；cache hit不能跳过内容身份/锁定SHA验证。
- 旧失败指纹只止损重复候选，不能让最终真实门禁被跳过或判PASS。
- UI默认源码、窄屏、保存取消必须与真实浏览器断言一致。
- 多语言SKOS及量纲未知不能当有效，历史Release按注册策略读回。
- Docker删除只能精确归属白名单，保留G2卷与可用开发环境；history持久删除严格后验。

### Task 1: E0公共合同与基线

- [x] fetch/保护用户文件，原生Master树及任务分支。
- [x] 阅读批准附件、规范、M2交接与资源/失败记录。
- [x] doctor提权exit0；完整SelfTest基线exit0（ReviewPackage96/0）；M2最终CI40545746924双job真实success。原权限/缺库/TLS失败保留。
- [x] 冻结cache/platform/failure、浏览器状态、证据Schema和timeline接口并独立审查。

### Task 2: E0-A canonical远程复用与止损

Files: scripts/maintenance/canonical_fuseki.py、infra/development/fuseki/**、scripts/tests/CanonicalFuseki*.py、.github/**（Master单写）。
- [x] 先新增失败测试并确认FAIL；实现平台/输入键/校验回退、阶段计时与重复失败短复现。
- [x] 官方缓存与受控GHCR比较，选不新增权限/依赖方案，必要具体审批。
- [x] 单测/负例PASS后两个独立新runner CI冷/miss及hit、输入改变失效，记录实际run/key/id/耗时。

### Task 3: E0-B状态合同和快速浏览器前置

Files: apps/web/src/features/ontology/workspace-state*（待WEB owner接管）、scripts/acceptance/workspace-smoke.mjs、scripts/tests及CI。
- [x] 为默认source/显式graph/canvas/source、选中实体/编辑/权限/窄屏写失败用例。
- [x] 真实Smoke包含保存取消及历史流程，完整浏览器前必跑；故障注入短FAIL/修复PASS。

### Task 4: E0-C证据、计时和资源生命周期

Files: scripts/maintenance/task_run_timeline.py、scripts/maintenance/evidence_preflight.py、scripts/tests、正式构包器入口、资源执行器与规范。
- [x] 历史validation和当前fixture早跑正式V3 Schema，缺多字段/Head/status/EOF/截图/ignored负例先FAIL再修。
- [x] JSONL记录UTC区间/运行/输入/结果/失败/依赖并发，自动墙钟、累计、重验及可观察关键路径，Agent活跃UNKNOWN。
- [x] 创建即登记；真实Docker按精确ID/后端/白名单DryRun、独立Review、Apply和持久后验；不全局prune。

### Task 5: M3合同及独立实现

- [x] Master冻结精确RDF/错误码/版本/API/生成TS接口、owned_paths和合法非法测试，独立Review。
- [x] SEM独立树：SKOS/单位/量纲/版本引用、真实PG/Jena和历史支持注册。
- [x] WEB独立树：中文术语/单位UI、三栏接入/真实API及状态契约，不写公共Tokens/生成TS。
- [x] 实际完成main集成a655642和929bfd3；首集成晚于原定最早窗口，偏差如实保留，API47/UI149增量实测及独立Review通过；CI规则被2026-10-29本地优先授权覆盖。

### Task 6: 完整验证和唯一交付

- [x] E0真实远程缓存与本地独立门禁通过；400业务+兼容/G1/观测/trace，以及受影响故障/性能续跑均实际通过，绑定源码和原FAIL。
- [x] 规范、证据、自动55区间计时、实际15阶段资源回收和独立后验；SelfTest/受影响增量及真实产品检查通过，最终diff-check在冻结提交时执行。
- [x] 冻结源码与本地验证绑定、独立Review及V3准备完成；唯一ZIP/独立重开/精确Head与hash取冻结提交后真实封包回执，Git内不预填未来结果。云CI按最新授权可选，交付后停止。

Current checkpoint: LOCAL_READY_FOR_PACKAGING / PARTIAL. 七项真实本地门禁按受影响层组合闭合，原失败保留；两次main集成已实测，15阶段资源实际回收且history自然代际后验闭合。物理字节未知及native active-task guards精确KEEP。冻结Head后只做唯一V3及独立重开、main最终集成和回执，不启动M4/M5。
