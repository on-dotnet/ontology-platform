# 风险登记与事实纠正

所有结论限已审Git输入的静态分析；本任务不重跑产品。风险等级P0阻断、P1需另批修正/授权、P2文档或监控。Owner默认后续集成Master，Reviewer须独立复核。

|ID|级别/状态|事实依据与影响|解除门槛|
|---|---|---|---|
|R01|P1 / MAIN_INTEGRATION_NOT_AUTHORIZED|45提交原实施授权可映射；此前各任务明确禁止main。逐项见commit-inventory.json，不将fast-forward当批准|人类批准准确main parent、45项提交清单与目标Head及回归预算|
|R02|PREVIOUS_REVIEW_FINDING_CORRECTED / CLOSED|G4Composition.cs第18–19行在Enabled时拒绝非Development；54–55行限制自动迁移，40行才读取public例外。精确blob见static-source-bindings.json|撤销“没有Development校验”孤立P1；不改变旧审查字节|
|R03|P2 / DEPLOYMENT_NOT_VERIFIED|Enabled/AllowEmptyPublicSchema缺省bool=false；PlatformApiHost调用AddG4Module，Program再Initialize。明确开启public只见final-gates实验运行器；实验compose设置Development。真实部署外部环境未读取，不能证明生产配置正确|未来集成在隔离进程验证G4开关×Production/Staging/Development矩阵；部署owner确认环境不可误标。当前无实证生产扩权，不设虚假MAIN_INTEGRATION_BLOCKED|
|R04|P2 / REGRESSION_REQUIRED|PostgresTicketStore新增内部G4SessionReference；审计追加11项；workspace添加导航；两测试锁修补项目依赖，G2/G3协议文件未变|真实G2/G3身份/发布/回滚/查询/MCP及G4关闭模式回归；测试规划见main申请|
|R05|P1 / SUPPLY_CHAIN_NOT_VERIFIED|旧RustFS/Fuseki及其他精确镜像只批准内部合成非分发AMBER-A1；许可证/CVE/签名不完整，源码纳入main不等于镜像可发布|将源码集成与运行/商业发布分别审批；不得继承旧任务的风险接受为新任务运行授权|
|R06|P2 / HISTORY_PRESERVED|链内有EOF与原证据封装变更：G4-00 input-original-bytes、恢复evidence-byte-preservation、final evidence-format-originals/sbom-format-receipt；原对象与失败可恢复|逐提交保留前后blob；不重写历史、不把47/2改成包内49/0；旧VerifyOnly通过不是产品复跑|
|R07|P1 / M2_ADMISSION_PENDING|三个驱动候选元数据可查，精确二进制/传递依赖/许可证及平台实测未执行；TD文档3.2.2和NuGet3.2.1存在版本展示差异|逐Adapter独立版本/许可/环境/网络/预算批准；不假设最新文档全部适用于旧候选|
|R08|P2 / PACKAGE_PENDING|新任务只能修改owned_paths，host工具位于evidence可被LOCAL输入排除|工具单独hash绑定及负例重验；最终两层diff-check、路径核验、独立重开|
|R09|P1 / MAIN_INTEGRATION_BLOCKED / BLOCKED_WITH_WITNESS|d40e6ab新增旧host-monitor.json为76条JSONL，44070字节、SHA256=6e425cb7ad191dd6a6fa8a2261a55d8599c2686ff4cb11d5c6d8bdd93a712122；verify.ps1:64–66按单JSON拒绝，171–172在SelfTest套件前退出。该文件不在旧Tested48be53e中|另批精确历史JSONL兼容修复及坏行/截断负例，保全原字节/原ZIP/原49事实；修复后真实完整SelfTest及新Tested/Head绑定|
|R10|P2 / ENVIRONMENT_GAP_IDENTIFIED|新树.tools/pythonlibs不存在；verify会覆写PYTHONPATH。直接只读复用已登记PyYAML后21文件PASS，但未恢复原SelfTest入口|另批/登记只读工具复用入口；不安装、不宽泛跳过。与R09独立，不能用解析器通过抵消JSON失败|


## 配置及部署范围

AddG4Module的Development守卫不是判断业务网络所在地的证明。若运维把生产进程标记Development，该守卫可通过；这是待验证部署条件，当前没有生产读写证据。G4ContractExport建立仅元数据的临时回环Host，未注册连接服务，不是可用生产连接器；未来集成需验证其不提供认证业务成功替身。

main→Head对infra、CI、AppHost无变更，实验运行器未见由正式CI/部署引用；连接源仍固定pg-source/fixture/fixture_reader与VerifyFull，AllowEmptyPublicSchema受精确schema集约束。P1供应链门禁限制未来运行/发布，不宣称现有main已安全生产。Windows原生AMD64、完整许可/CVE/签名、生产配置均NOT_RUN/NOT_VERIFIED。
