# G4-M1 恢复时测试、主线与下游门禁

## 主线位置

已审 **G3 main `d1a61da…`** → 已审 **G4-00 合同 Head `8afc5d4…`** → G4-M1 `59edb405…`**PARTIAL** → 本任务只修许可准入并恢复 M1 的真实产品 P3–P5。

之后仍是 **G4-M2 Oracle/Doris/TDengine/WebAPI → G4-M3 MappingRelease 审核回滚 → G4-M4 受控语义查询 + 完整Datum → G4-M5 集成验收 → G5 指标规则 → G7 根因分析Agent ← G6 AI文档支线 → G8 正式交付**。禁止因 M1 开发通过合并/提早开始下游。G6 依赖问题不阻断 G4。

## 本任务原有 49 项用例的真实闭环

16 项严格合同（实体/权限/OpenAPI/版本/Secret/审计），14 项 PG/TLS/只读与重复提交，19 项 Catalog/Job/Next UI/真实权限/资源。

真实运行顺序：源PG/TLS合成fixture → API+合成PG的持久记录/审计 → Keycloak真实OIDC与CSRF/403 → Next/Playwright完整用户路径 → 探测失效/重启/租约/fencing/错误恢复 → 版本指纹/源ACL撤销 → 资源 Before/After/KEEP 和精确回收。

**不可代替的验收**：未保存草稿试连、保存后复测、独立启用、Catalog刷新/快照、禁用后拒绝源IO、同key不同payload冲突、无CA/错证书/错密码、源端只读角色与跨组织重号、审计失败回滚、取消/lease、UI凭证不缓存及刷新恢复。任何实测缺失记 NOT_RUN/BLOCKED/NOT_VERIFIED，不准标 PASS。

## 额外应先修正的 P2 静态审查问题

`G4Endpoints.cs` 仅根据 `Request.ContentLength` 检查64 KiB。必须增加对 **HTTP/2/Transfer-Encoding:chunked/无Content-Length** 的真实读入字节硬限，防止JSON反序列化分配内存后才拒绝。正反测试在本任务合成 HTTP fixture，检查超界时不触发秘密签发或业务命令。不要因为ASP.NET默认30MiB全局限制就声称等于64KiB合同。

## Exit/DoD

- 本任务镜像取证阶段：基于官方 digest 的 A/B 门禁及逐镜像风险表、独立 Reviewer PASS，保留 G8 未决。AMBER-A1 仅研发/不分发。
- 产品阶段：真实49项全部有原始输出，适用项PASS方可描述完整M1；平台不具备可运行Windows时 Windows原生明确NOT_RUN。
- 交付阶段：真实Base/Head/TestedCommit、输入SHA、Git路径、实际Docker容器/卷/镜像准确ID、审计Trace、证书与许可记录（不含密钥）、失败日志、唯一V3 Review ZIP及独立重开。产品源变更后重跑影响层；说明/证据-only提交按原准许可复用。
- 不符合任何运行前门禁，交 PARTIAL/BLOCKED_WITH_WITNESS，不夸大、不启动后续M2。
