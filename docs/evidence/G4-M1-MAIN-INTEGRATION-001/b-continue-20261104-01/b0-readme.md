# B0 消费者边界与恢复证据

本轮只修改原19项白名单任务工具、任务说明和新证据；产品及共享扫描器未改。完整原SelfTest和原生产品门禁仍须在新T上运行。

- 最终边界测试：b0-final-tests-final2.log，17 tests / 0 failures，exit 0。含真实隔离bare的正常推送、通告前/后竞态；假Docker fixture仅用于守护终止测试，不代表产品容器验收。
- 依赖：Web391包26176文件按锁→store索引→实际SHA512核验；109个shim目标按package bin声明绑定，新私有副本仅写确定性exec，不执行旧shim。pnpm已审archive454成员逐项匹配。NuGet采用SDK签名包GetContentHash和首次archiveSHA绑定，只复制归档并离线恢复。
- source IO：准确非Unix connection received覆盖TCP/坏TLS前置访问，健康检查正常保留；真实baseline缺失或日志截断即拒绝。原始reader-only实现审查中被否决，最终负例覆盖。
- 资源：实际展开四组Compose的任务身份、目录、标签、镜像、隔离网络、内存、卷和能力限制；真实容器仍NOT_RUN。已启动的唯一长进程是本任务有界host monitor，PID和释放入口在ignored归属记录。
- 原样静态verify首次exit1保留：两个动态password变量被有限模式匹配，以及私有PyYAML尚未重建。前者已改为语义明确的局部变量名，准确原正则复查通过；后者由获批离线PREFLIGHT重建26文件副本解决。没有共享扫描器豁免，不将本次静态结果标PASS。
- 原execution_preflight仅验证G4-M1历史合同路径，可发现性PASS不代表新消费者或产品完整准入。

新manifest冻结19项driver SHA、本地工具、六镜像、风险接受、精确Run/路径与预算。任何源码输入改变都需新T。B0范围的Review不得当作I01–I08产品PASS。历史包和证据未改，不生成新的中间ZIP。
