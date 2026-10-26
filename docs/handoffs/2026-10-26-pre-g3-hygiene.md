# G3 前工程治理交接

PRE-G3-HYGIENE-001 READY_FOR_REVIEW / PARTIAL；只交一个V2轻量包，交付后等待复审。本轮不实施G3、不执行G3 Plan。当前授权及历史边界见[授权索引](../tasks/current-authorization.md)、[本任务合同](../tasks/PRE-G3-HYGIENE-001.md)、[交付报告](../evidence/PRE-G3-HYGIENE-001/delivery-report.md)。

G2已审基线46c7a6de70b1b97c032b12a19bc27c1c54e70f4c / CI40283523824双job成功。本轮H2=3b51ef70888da6367c1f9b77a8b18124ff0fdce9在独立Review与同HeadLinux双job通过后Master快进main并push；最终H4当前Head/主线CI以包manifest的显式40位SHA与runtimeCi及外部末次交付回执为准。新G3 Master开工必须git status/fetch后读取动态最新origin/main，不再机械使用旧46c7a6…；保留旧main/历史失败事实，不reset覆盖。

四旧ZIP与三个M0本地收据在先归档不可再生事实、核对Git恢复、产生H2有效包及独立重开后准确删除，共回收逻辑字节见cleanup-execution.json；原ZIP SHA保留，原压缩包逐字节重造不承诺。全部历史树/枝/持久卷/私有缓存保留DEFERRED；旧聊天g2-readiness-test、g2-master私有runtime/PFX/共享parser不能删。17树和Docker2容器/48卷/23镜像/3默认网络，准确ID、容量、保留原因和复查条件见before/after清单。七个G1记录外部变化NOT_VERIFIED不归为本轮清理。主checkout六个DS_Store和reviews/.DS_Store为既存文件元数据保留。

恢复用同一g2-master checkout原私有runtime运行既有g2-runtime.py full --runtime-file（参数指向该树原文件，不读取展示凭证，不跨树复制），固定PG18.6/Keycloak26.8.1/Jena6.2/RustFS1.0.3与卷保留；Keycloak身份在PG keycloak库。M0随机卷不能直接当稳定日常配置。已有真实G2完整冷起/业务/LGTM证据未改，本轮只抽查保留资源元数据，未重启AppHost/浏览器。

Monaco继续PAUSED_BY_USER/BLOCKED，内嵌DOMPurify问题未修，不能只override；真实LLM NOT_RUN/BLOCKED，不收费。Windows/Intel/生产HA/五真实源/正式SLO保持未验。下一步先单独Plan并获新授权，不能由本轮Git权限扩展成G3功能开发。

```powershell
pwsh -NoProfile -File scripts/doctor.ps1
pwsh -NoProfile -File scripts/maintenance/inspect-resources.ps1 -IncludeDocker
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/create-review-package.ps1 -BaseSha <本阶段明确40位Base> -HeadSha <已提交40位Head> -TaskId <当前TaskId> -Status PARTIAL -EvidencePath docs/evidence/<当前TaskId>/validation.json -CiRunId <真实run> -CiRunUrl <真实URL> -CiCommit <同Head> -CiConclusion success
pwsh -NoProfile -File scripts/create-review-package.ps1 -VerifyOnly -PackagePath <实际ZIP>
```

Review ZIP默认V2；V1只读兼容、旧SHA不改。长期制度见[生命周期规范](../development/resource-lifecycle.md)和[Review合同](../development/review-package-spec.md)。独立写Agent继续独立托管树和任务分支、公共文件Single Writer、Master唯一集成main，不恢复共用main串行开发。

默认Docker bridge ID在本轮before/after发生变化（9f14564aa5e1→abc425df5858），网络数量仍3；本轮无Docker修改，原因NOT_VERIFIED，保留DEFERRED，不归为清理。
