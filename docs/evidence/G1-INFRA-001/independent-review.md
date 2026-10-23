# G1-INFRA-001 独立审查记录

日期：2026-10-23。只读Reviewer与实现Owner分离；短期Agent消息在此固化，不将静态审查当运行测试。

## Master 工具链与验证接线

Reviewer：infra_rules_review。工具隔离、精确版本、根CPM和doctor先经审查；缺Node却有pnpm脚本的处理经真实RED→GREEN回归修复。

解析器审查发现缺失脚本时普通verify可静默跳过的Important，现明确structured-syntax FAIL并加入required-files。新增回归先失败、修复后4项正反例通过；README限定批准wheel组合。安全YAML解析、TOML标准库、隔离pip和脱敏错误无其他阻断。已提交2547e6d41ae633ede70efec96696433b4bd021ae，远程Actions [39977972503](https://github.com/on-dotnet/ontology-platform/actions/runs/39977972503) completed/success。

原生接线静态复核无阻断：RunTests必须显式RunNative，拒绝零项目，项目隔离工具优先、进程环境finally还原。Reviewer实际验证单独RunTests退出1；真实solution/build/test/format及最终CI由Master另行执行并记录。

## A 审查包

Reviewer：infra_rules_review。初次审查8ddeb4f发现Important：color.ui=always污染完整patch，旧重开验证会同样污染而误通过。A统一Git color.ui=false并对diff/log显式no-color，加入真实回归。RED显示ANSI及git apply解析exit128；GREEN无ANSI、git apply --numstat exit0、VerifyOnly exit0。

最终复核d96f1f5b226c750d7beda270b36b8de7a091da78：Critical 0 / Important 0 / Minor 0，可集成。凭证过滤、路径、源码blob比较、完整成员/散列复检和证据状态未见其他阻断。Reviewer独立只读复现彩色配置的patch解析通过；A完整35项真实Git/ZIP测试通过。

Master主工作树重新执行verify -SelfTest，历史8项、doctor回归、结构化4项和ReviewPackage 35项均通过，exit0。A通过no-ff merge集成为7d1da772d1694c43572af6962cc3454e6d7e5534，普通push成功。测试/有限模式不等于全面秘密或安全审计。

## B 与最终集成

Reviewer：infra_implementation_review。最终头c120b5ff5128346b7709191589f6e5889d671ccd与远端任务分支相同，树干净，diff-check exit0。Critical 0 / Important 0 / 未解决Minor 0，可集成。全部5个手写C#文件含测试私有方法/局部用途已逐行检查；未扩入SEC/FE/OBS/G2。

Master发现AppHost隐式平台包使单一Windows锁不能用于Linux锁定恢复的Important，B改为按SDK RID选独立win/linux锁，删除默认旧锁，分别真实恢复。Reviewer核验选择路径与包身份正确；Windows上生成Linux图不冒称Linux运行。

中文异常XML说明、Keycloak重启前后非秘密身份ID比对、运行摘要的遥测边界三项Minor均已落实。证据中的4/4宿主测试、五项HTTP200、四资源重启持久化和真实404 TraceId日志关联已复核；Reviewer没有重复启动容器或读取真实凭证。B发生的临时S3访问标识/签名回显已立即停实例、轮换、修改异常脱敏并复验，未持久化原值；B对四个实际秘密逐值内存核对，提交证据0命中。

Master根solution已接四真实工程，项目隔离SDK实际执行`dotnet restore backend/OntologyPlatform.slnx --locked-mode`exit0。主线完整构建/格式/测试和最终远程CI记录见总交付证据；初轮静态审查不是这些测试的替代。

Master共享接线/最终交付记录由infra_rules_review另行只读复核：四工程路径、五锁与110包许可清单一一对应，CI锁定恢复/原生开关一致，所有相对链接及暂存/未暂存diff-check通过。主线完整运行exit0后，Reviewer核对35构包案例、4MTP测试/0失败/0跳过及诊断格式日志四工程21文件/0改动。最终Critical0/Important0，健康检查JSON命令摘要措辞Minor已明确标注；不将只读核对视为重新运行。CI保持NOT_VERIFIED直到实际提交后查询，并通过构包四个Ci参数绑定同一HeadSha。

ASPIRE010保持可见，DCP在本机回退控制台日志；OTLP/Dashboard ingest全链、镜像CVE/OS层SBOM仍NOT_VERIFIED，完整LGTM不在本轮授权。测试宿主和四测试容器已停止，隔离卷保留，未碰其他项目资源。
