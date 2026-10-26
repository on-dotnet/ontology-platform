# C2 精确归属链与可恢复性

原阶段已经本轮人类明确按关闭处理，以下使用已提交创建/验收记录和实际CLI身份联合证明，不仅用前缀。

- `docs/handoffs/2026-10-25-g1-wave2-master.md:7`明确新开发前缀wave2-a5431c01414a、7容器/6卷、验收后唯一AppHost停止；对应`Wave2Infrastructure`与OBS固定6种数据卷；实际CreatedAt/Driver/容器依赖见docker-before。原177MB Keycloak停止层经docker diff只有Quarkus/JVM/tmp，真实身份PG单独卷；PG停止层只有运行目录。无挂载敏感主机私有文件，rm不带-v。
- `docs/handoffs/2026-10-26-g1-closeout-master.md:10`及`docs/tasks/G1-CLOSE-001.md:69`明确wave2-a19529d4edb4新runtime与专用6卷/Realm，core引导及完整验收后受控停止。该组fixture可重新prepare/bootstrap；无G2 Master私有恢复绑定。
- M0四组来自M0 portability固定合成PG/Jena/RustFS创建及重启持久化验收，准确命名/创建时间与runtime-resource-snapshot、observed实验归档交叉核对。四组三种资源共12卷均无容器引用。
- 13个Fuseki重复镜像由实际Buildx七字段+仅OCI index附件digest映射证明归属，详image-history-mapping.json；Master18条全exit0，独立Docker调查13条重复验证全exit0。当前保留镜像另列准确ID，不相加503MB共享层宣称回收。
- 18条旧Build history准确Ref、VCS、Context、Revision/Status归档；失败1条缺g2-log4j2.properties COPY已单独摘要归档。只删除记录，不prune共享cache；Docker Desktop全局13cache记录约500.1MB保留。
- G2三组24卷各有G2 Master实际私有runtime/realm/PFX，全部保留；选定ef979组通过原可信启动器恢复，PG/Jena/RustFS/Keycloak健康探针实际通过，准确环境和恢复入口见reuse-probe-before/after。

检查未读取卷内容、私有runtime值或原始环境/BuildArgs，不复制凭证。新恢复探针创建的9容器/1镜像/1history均不在原白名单，执行前后独立标注，不算历史清理成功数。
