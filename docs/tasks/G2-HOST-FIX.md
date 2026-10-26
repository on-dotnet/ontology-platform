# G2-HOST-FIX — Master 宿主集成修复任务卡

本卡持久化本会话先前 `/tmp/g2-host-fix-brief.md` 与限定复审分派，权限来自G2全部授权；不扩大业务/依赖。Base `c1e4dd0af6af4258f39c3c8a360c60e0709b8915`，分支 `codex/G2-HOST-FIX`，独立托管树 `/Users/chasen/.codex/worktrees/g2-host-fix/ontology-platform`。Owner `g2_host_fix`，独立Reviewer `g2_root_host_review`，main集成仅Master。

临时single-writer：`Api/G2/ExecutionEndpoints.cs`、`G2Readiness.cs`、`PlatformEndpoints.cs`；`wave2-runtime.py`/`Wave2Runtime.Tests.py`；SecurityTests的G2宿主测试；Master/host/fix1-*与报告。其余Host/AppHost/合同/项目/锁/CI只读。Master停止写这些路径，Owner结束并交回后才cherry-pick；只读Reviewer不写。完整路径均以backend/src/Hosts/OntologyPlatform.Api、scripts/acceptance、scripts/tests及对应测试/证据根解析。其他人在工作，不覆盖其修改。

轮1 `c1e4dd0..72fff701`：实际MapExecutionEndpoints OpenAPI DTO/原生SSE/errors；同一两秒预算含Governance；accesskey脱敏。有效红绿、预算重置变异、50/50及格式/受锁构建/SelfTest；独立复审三项ADDRESSED C0I0M0。

轮2 `72fff701..732589744`：Master真实PG pause使原实现八秒仍无返回，禁止以EF拦截夹具冒充真实取消。健康副本配置、取消握手预留与真实PG三项，53/53。独立复审确认超时ADDRESSED，但发现连接串缺省时PGGSSENCMODE=require被覆盖的新Important，进入轮3；不入main。

轮3：最小保留Npgsql官方有效连接串/环境优先级与GSS Require，TLS与业务配置保持；补环境/显式配置控制、真实PG预算及异常清理验证，独立限定复审后由Master再实测完整八项与全链。未闭环前状态PARTIAL。禁止放弃后台EF任务、降低业务认证、系统安装、收费、生产或新依赖。所有实际证据见master/host/fix1-report.md；独立回执见master/independent-integration-reviews.md及后续追加。
