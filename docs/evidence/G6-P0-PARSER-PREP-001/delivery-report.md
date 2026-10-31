# G6-P0-PARSER-PREP-001 交付报告

PREP源码、合成实验、设计及已授权验证完成，提交等待独立复审。安装闭包BLOCKED；运行时全部NOT_RUN。正式V3状态使用PARTIAL以保留这些边界，不把本次准备完成解释为真实解析/部署成功。

## Base、源码与输入绑定

BaseSha：d1a61daffe844475b07705797e3ad325cc3f2945。
TestedCommit：df38f36134c1dedf90341324ddb2fca329ac6250。最终Head由唯一ZIP manifest.headSha及外置重开回执给出；之后仅增任务/证据文档，V3重算全部源码/构建/合同输入相同。
Master：codex/g6-p0-parser-prep-master；Parser：codex/g6-p0-parser-prep-parser，已push的Worker提交ffa3499812debd89f2e7fe4138e2ddfca2e7ac68，经非作者Review后cherry-pick为1022a9931636c89a0327c1a5ed474decebdf81e5。源码冻结提交已push。没有合main/强推/覆盖其他树。
输入ZIP 110879 bytes，SHA256 98f179f187c82ae9d095dfe69413c11bcc6b99d35d9416a0b940090c9ac44e83；26成员CRC/路径/大小/散列，24清单成员逐hash与归档重建通过。原ZIP保留，解压副本已精确回收。

## 本次实现与实际结果

Document IR / DocumentVersion / ParseArtifact / SourceAnchor / SourceMap在parser/core.py真实实现；raw UTF8 byte与Unicode codepoint两个坐标域、BOM/CRLF归一、CSV全局词法和cell局部map、canonical身份哈希、版本/scope/config防复用、多段证据/EXACT降级、secure openat/nofollow/FIFO/权限/race/预算/FD关闭负例。DOCUMENT_ONLY不产生图，不构造假page/bbox。
35解析+37辅助=72 unittest全部PASS、0skip；9 seed/18 spans全部回源。辅助测试包括六Provider、capability与auth分离、精确有理数预算、SecretRef/脱敏、默认关闭Compose、精确资源DryRun、元数据缺失/冲突、前置import与manifest拒绝。固定最终输入8条命令均exit0：preflight、两套unittest、seed、元数据audit、静态、SelfTest、diff-check。原始字节/命令/exit/时间/提交在*-final.source.json。
完整SelfTest含17个Python套件合计314测试、Node6测试、ReviewPackage103测试（另有PowerShell断言组）；没有以这些工程测试代替产品。未新增C#/Web产品实现，.NET/Web/浏览器与Windows/Linux实跑NOT_RUN；Actions NOT_RUN。

供应链：162节点、334已选声明、3493发布制品元数据；全license声明/URL/精确观察version/文件hash-size及4候选模型repo revision/LFS信息已存。明确发现固定pin和numpy范围不符，未求解平台/ABI/native NOTICE/所有模型闭包。prepared信息可审，安装许可未完成，不提供伪requirements锁。
跨平台Compose计划包含core与4显式profile、健康/依赖/网络/Secret/权限/资源边界和Windows WSL2要求；全部image为空且runnable=false，禁止直接启动。六Provider全部disabled，真实额度0；安全TTY/OS store/Docker Secret设计未执行。ADR01–06运行时DEFER；07–09政策/设计接受，真实验证待下一授权。

## 非作者审查与失败

独立Reviewer源/设计结论PASS_FOR_PREP_SOURCE_AND_DESIGN，增量资源无新阻断；独立35Parser与37Harness、24CSV/1137字符/4篡改、13平台攻击，原五平台缺陷和preflight缺陷已关闭。完整报告见independent-review.md。Reviewer不具Docker socket权限，未将其独立Docker现态写PASS。模型/安装/权重也未由Reviewer重跑。
所有失败保留：Worker红例与首实现失败、平台精度/URL/profile/type攻击、测试发现绕过、SelfTest计时参数exit2及缺工具路径exit1、metadata超限/网络错误、资源history字段不足/After比较TypeError。最终一次runner stdout数量因共享list在追加NOT_RUN后输出complete=false属摘要计数错误；实际8条退出码均0，validation逐条与原日志一致，未改写原失败。

## 资源与宿主

准确清理16临时对象/42文件/319571逻辑bytes（另外收尾脚本/cache的实测见resources-final-cleanup.json），物理空间不推断。最终测试每轮11Parser+2Preflight临时目录已真实清理并断言不存在。19工作树（17原有+2本任务）保留；两任务树未合main，待关口关闭及无活跃引用才回收。原main6个DS_Store未触碰。原工具目录只复用symlink，无安装，原目标保留。
Docker创建0/删除0；8旧卷、14映像行、3网络及history全部KEEP。default bridge ID前后变化，原因/行为者未知；events查询空不证明无变化。Before history5个空对象是采集缺口，After/Final准确refs不补造历史也不用于删除证明；没有宣称全资源不变。准确命令/exit/snapshot/KEEP理由及解除条件均登记。
宿主监控PID 94412有界32分53秒，132心跳、86锁屏、84锁屏且外屏熄灭，最大间隔15084ms，policy连续ready。电源日志窗口无确认Sleep区间；不推断未知窗口。沿用已有用户能源确认、未改全局策略、未用-d/-u；准确PID/cwd验证后SIGTERM，工具exit0，临时监控已结束。sessionContinuity按原工具保持NOT_VERIFIED。

## 正式包与停止

最终唯一Review ZIP V3从明确Base/Head生成；全部现行非证据源码和本任务证据各一个payload，完整diff/变化blob索引/历史恢复索引/LOCAL验证绑定。无.git/凭据/缓存/私有数据，ignored仅聚合。size/SHA256/manifest/独立VerifyOnly+CRC/hash/diff重开由最终外置回执给出，不制造自引用commit。
下一阶段申请在design/adr-status-and-next-authorization.md；精确闭包和预算尚未获授权。完成正式包独立重开后停止等待ChatGPT复审，不自动G4/G5/G6-01、安装、容器、API或main集成。
