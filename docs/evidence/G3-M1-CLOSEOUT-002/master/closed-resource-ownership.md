# G3-M1-CLOSEOUT-002 精确关闭资源归属

本归属声明由本轮正式授权H3及非作者inventory_review独立核对形成。CLOSED synthetic：原G2与M1合成验收阶段已关闭，本次只清理过期工程资源，不删除业务实现/历史Git/私有runtime/PFX。

## 可再生与引用证明

原可信scripts/acceptance/wave2-runtime.py:prepare使用随机开发身份/新PFX，bootstrap-keycloak生成合成Realm。原G2 cold新realm/新卷验收及停启持久化实际记录见docs/evidence/G2-THIN-SLICE-001/master/delivery-report.md及g1-regression.json。恢复入口为fresh prepare(g2)、core、bootstrap(profile=g2)、full；此恢复语义是重新生成合成验收资料，无需恢复旧随机身份字节。未读取卷内容。

当前docker-preapply.json为0容器、所有候选无mount引用；docs/tasks、docs/handoffs、scripts、backend按两旧前缀检索无活跃依赖（rg -l exit1，无匹配）；既有证据/旧keep合同为历史，不形成新任务绑定。未发现生产/用户唯一资料的具体引用。保留ef979实际PG/Jena/RustFS/Keycloak四健康通过，不重新prepare/bootstrap。其它两组不再承担日常或恢复职责。

## SAFE_CANDIDATE：准确16卷

- `g2-712190660deb-alloy-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-fuseki-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-grafana-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-loki-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-postgres-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T02:01:32Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-prometheus-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-rustfs-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-712190660deb-tempo-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T02:05:13Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-alloy-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-fuseki-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-grafana-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-loki-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T05:33:22Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-postgres-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T05:32:57Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-prometheus-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-rustfs-data`：CLOSED synthetic，可再生；合成验收数据库/语义图/制品，可由固定fixture和可信入口fresh再生；无额外恢复引用；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。
- `g2-b59e68191ca0-tempo-data`：CLOSED synthetic，可再生；过期合成验收遥测/仪表板；关键验收已提交，运行日志不需字节恢复；Driver=local，CreatedAt=2026-10-26T05:33:21Z，当前references=[]；Apply仍精确重验。

## UNREFERENCED_IMAGE：准确重复Fuseki

所有镜像以完整ID及全部RepoTags校验，无容器引用；OCI归属见image-provenance.json（筛选Attachments的OCI index digest）及历史已提交image-history-mapping.json。不能凭fuseki名称判定；共享层不按每行503MB累加。
- `sha256:24b640093c5fc240b2b4b93573ad0cc5b2a4237c7a3997957ebed7c41321adc4`：CLOSED synthetic，本项目重复构建；tags=['fuseki:0abac99e7c3d755e0b3ce01d70479b62af9ba1f0']，references=[]，正式canonical复用镜像另保护。
- `sha256:24d5809ca76fae4bca1484d7a914eb0786bd124f0aa5d246b4bc8aea26c711da`：CLOSED synthetic，本项目重复构建；tags=['fuseki:2ceba08b9ba775d9d3d4c110c5b63b13faecbe63']，references=[]，正式canonical复用镜像另保护。
- `sha256:2f786d9e8fdeebd5b36f8a70c77131f073ade597106b016a281f44fbdc95d955`：CLOSED synthetic，本项目重复构建；tags=['fuseki:ba230101bb9080e2b78215c713b5dbb7b2a55243']，references=[]，正式canonical复用镜像另保护。
- `sha256:3f46ed2c2a7edbc2497e8830478582ecfd2747dd9baff8b3759fdb744d86382a`：CLOSED synthetic，本项目重复构建；tags=['fuseki:31fbd43bc559bfdabc82d8e21853c3de804d6598']，references=[]，正式canonical复用镜像另保护。
- `sha256:87bc6e0550c64cad9265c867e8926777cca68c2d996f243982c4e9f00d5d0590`：CLOSED synthetic，本项目重复构建；tags=['fuseki:3bd73d575e3045367f86c6192c361a43feb672d9']，references=[]，正式canonical复用镜像另保护。
- `sha256:8e28b3a01e16230451343afcfd3997c625b04806b9f3b1960de5915ecf3d01fa`：CLOSED synthetic，本项目重复构建；tags=['fuseki:ce0f9d44ff3f59b2083f5a9179df41fa9b64b942']，references=[]，正式canonical复用镜像另保护。
- `sha256:a807095b91ef054c4ad772ac9d70a5268f8f48616fca197e3de2e618a2f5c837`：CLOSED synthetic，本项目重复构建；tags=['fuseki:76af01fbdc917cf3952d1cae0db6d497accb2c65']，references=[]，正式canonical复用镜像另保护。
- `sha256:ba4babd073e3a44bcfe6b3a92b00299d2fe37130ab9642e0c9a04ebee2793aad`：CLOSED synthetic，本项目重复构建；tags=['fuseki:a331244c76c8c5fd27cec3da702733fddeb9b3bd']，references=[]，正式canonical复用镜像另保护。

## EXPIRED_BUILD_HISTORY：准确Ref

当前history全部completed，Context/VCSRepository精确归属本项目，各原验收/新canonical构建已结束。移除metadata不声称释放cache；严格冻结Buildx0.38.1/BuildKit0.34.0及Engine/bridge generation，offset读取，准确no-record诊断。自然代际未发生时持久跨代际为NOT_VERIFIED，不主动重启。
- `67640w3xkq2m9d34grtxvh3h0`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g2-master/ontology-platform/infra/development/fuseki，VCSRevision=46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `ezgaz081sj0glsz63lwrladex`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-closeout-resources/ontology-platform/infra/development/fuseki，VCSRevision=47935fb2eda3d708e628a1b23ccd897e2250ff33，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `nkanrr4x3dno77mfigejmo9ap`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=dc5a5c3240464ab0692052707e933e35ae9d93af，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `rbknq2eyl3ze0p4ssiz3f7k4z`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=59c7875430c92443ffd8ab7463d11012e4461f68，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `jycu16bu1tx4tkl41e3v0ep2f`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=24f6379bdfdb012a296d88e15c4beb9f1d8d5061，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `gro8fj6y8t0t394ulylmtrvpb`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=24f6379bdfdb012a296d88e15c4beb9f1d8d5061，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `1pf0ezzhu4o3ftzu5wb58r5h5`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=02763a1144f25d30cdac42c907859a8784226f49，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `3t2h2x1svpe4z48xhmrc4mkm7`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=6a1c76cd41e2b926f82ccd4ddd9b750dce5b7c44，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `npkohc639rmrlcdeh1bngkggk`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=6a1c76cd41e2b926f82ccd4ddd9b750dce5b7c44，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `5fbah5gxqpe91txf3onpjy1v8`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g3-m1-master/ontology-platform/infra/development/fuseki，VCSRevision=5df0765775ad9a91c07ae05835057c0eaa4cb49c，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。
- `k6dmkqgacrtu4qh46qhy5x12n`：CLOSED synthetic，completed，Context=/Users/chasen/.codex/worktrees/g2-master/ontology-platform/infra/development/fuseki，VCSRevision=46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，VCSRepository=https://github.com/on-dotnet/ontology-platform.git。

## 保护对象与解除条件

- `g2-ef979bd04cc0-alloy-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-fuseki-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-grafana-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-loki-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-postgres-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-prometheus-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-rustfs-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `g2-ef979bd04cc0-tempo-data`：KEEP_PRIMARY_DEV，与既有g2-master/.tools/security/g2-ef979bd04cc0/runtime.json恢复组绑定，实际四服务健康成功；解除条件为选择并实测替代日常环境后再审。
- `sha256:05040926259ace989082fac0fb2f52d33f4a8122a9a85cb617eb76965b484a39`，tags=['ontology-platform-fuseki:context-6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018']：KEEP_PRIMARY_DEV；canonical内容寻址共享结果，AppHost/验收共同使用；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:0db216b630ae1f348a1584c67f3cead8b4c1fc839169a39501db664744158e28`，tags=['grafana/loki@sha256:0db216b630ae1f348a1584c67f3cead8b4c1fc839169a39501db664744158e28']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:401e1fbc58c27b08c3103e00c86b22bd175a1cdd8f8a7d61965133f27a24437f`，tags=['ontology-platform-g2-fuseki:6.2.0']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:64e2fbd56d9c2b3412a4b430a58ea59e91a670b1e75f920a0c702213ad145044`，tags=['grafana/tempo@sha256:64e2fbd56d9c2b3412a4b430a58ea59e91a670b1e75f920a0c702213ad145044']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18`，tags=['grafana/alloy@sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b`，tags=['rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b`，tags=['quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f`，tags=['grafana/grafana@sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6`，tags=['postgres@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。
- `sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2`，tags=['prom/prometheus@sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2']：KEEP_PRIMARY_DEV；已批准固定依赖或旧可信恢复入口使用的legacy Jena镜像；解除条件为对应锁定依赖/可信恢复入口被已验替代并无引用。

所有3默认网络保留；禁止本轮network/global cache prune。旧私有runtime/PFX/realm与旧Master树及未集成refs均不在删除计划；保留原因是凭证/独特源码/恢复入口，解除需独立后续授权和替代验证。Mac APFS/VM物理释放NOT_VERIFIED。
