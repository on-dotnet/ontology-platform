# PACKAGE：Review ZIP V3 实施与验证

状态：实现与回归PASS，待非作者独立审查与Master集成；不是本轮最终CI/ZIP交付。

Base：47935fb2eda3d708e628a1b23ccd897e2250ff33。源码提交：0a873be（完整SHA由Git解析）；独立托管树g3-m1-closeout-package，分支codex/g3-m1-closeout-package。Owner仅改正式构包器、其测试、正式Review合同及本目录证据，没有业务/CI/根verify改动。

## 实现

默认schemaVersion=3，保留显式V1/V2创建及VerifyOnly兼容。现行源码/当前任务非PNG证据单份payload；全部历史和省略PNG证据保留精确commit/blob/hash/size恢复索引。截图只有Head中review-screenshots.json声明的stable代表可进入ZIP，页面/主题/视口唯一，最多12张且Deflate payload合计≤3MiB；未新增UI时可不选图，Git证据不删除。完整文本diff和二进制双侧元数据仍由Git重算。

ignored只读长度元数据，不读内容、不跟随链接；有限目录/类别聚合、总计/估计字节/unknown、两个示例、清单SHA256/扫描时间进入manifest，全量清单只写本地artifact。严格限定聚合字段/类型/内部总和/分组唯一/样例/时间，拒绝重算ZIP散列后的结构篡改；不把后续可能变化的ignored快照强行与当前扫描比较。

创建和VerifyOnly均使用gh实际查询固定仓库run和engineering/governance-integration两个job，并比较Head/ID/URL/状态/结论；测试只在系统临时目录进程PATH放fake gh，生产没有接受fixture CI的参数。已只读查询真实旧M1 run 40462137827确认gh结构，但旧run不代表本轮HeadCI成功。本轮最终CI由Master冻结Head后取得。

软目标10MiB以上CLI输出实际分类压缩/原始字节与ZIP开销；默认15MiB以上创建及V3VerifyOnly拒绝，没有绕过开关。失败清除自身partial/本地临时清单，保留最后有效ZIP。V3完整Base..Head diff-check失败也拒绝。

## 实测

- `pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1`：exit0，90 tests / 0 failures，日志full-regression.txt。包括V1/V2独立重开、完整文本/二进制增改删rename、V3CI伪造、缺失/伪造索引、重算hash篡改、脏树/未跟踪/非祖先/路径/大小写/链接/秘密、截图/体积及原子失败保护。
- 完整套运行时随后仅替换PNG夹具构造，使53文件为标准库生成真实像素/IDAT/CRC的可解码PNG，生产实现未变；按增量规则再跑 `pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1 -CaseFilter 'V3 53*'`：exit0，1 / 0，日志png-regression.txt。
- 最终真实53PNG+55,256实际ignored文件夹具：V3=2,482,853 bytes，同Head V2=32,803,202 bytes；约92.4%缩小。4张明确稳定代表入包、49张省略且53项OID/hash/size/路径全部实校恢复；ignored count=55,256、estimatedBytes=165,768、聚合组=1、本地完整NUL清单SHA一致。无双份payload。
- `git diff --check`：exit0。应用/容器产品测试不属于PACKAGE线，NOT_RUN；不能以90工具测试表示M1业务或本机Docker清理PASS。

## 失败和效率事实

默认V3测试先RED（旧默认schema2）再GREEN。开发中严格模式暴露PowerShell自动Matches变量、空集合求和、字典count键遮蔽、JSON日期自动DateTime转换，均已修复并复验。独立审查提出ignored结构可伪造缺口，已加入8个真实ZIP重算SHA256SUMS负例并全部PASS。

首版provider逐ignored路径Get-Item扫描的大夹具未完成验证，未记PASS；停止其本PACKAGE进程并准确删除自身临时fixture。改为.NET FileInfo和目录安全缓存后完整大夹具实际通过。实现/等待/环境/测试/封包细分活跃耗时未测，UNKNOWN；不以墙钟推算工时。

未自行生成本任务最终Review ZIP、未宣称本轮同Head真实CI、未触碰历史ZIP原始字节；最终冻结/独立重开和实际Docker资源收尾由Master统一执行。
