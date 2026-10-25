# M0 独立审查记录

本文件由Master按独立Agent实际回报归档，不冒充Reviewer自行写入；Reviewer只读，无源码/证据写权限。

## 接管发现与隔离 · explorer

独立explorer实际加载匹配仓库TOML的开发者指令并完成只读委派。执行 git worktree list --porcelain、各树git status --short --branch及git rev-parse --show-toplevel --git-dir --git-common-dir，exit0。Master/A/B独立树均e3f0b9694412f7a91b6075be9d7e8d4fac4b890b，原始main25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1；路径互不嵌套、独立Git管理目录、共享对象库符合Git机制。该时点三树干净，仅任务卡和授权增量45行。角色发现/委派和Git隔离为OBSERVED，不能外推为独立OS只读沙箱、CI或运行产品能力；产品MAF本轮未实现。

## A 脚本 · quality_reviewer

审查固定范围e3f0b9694412f7a91b6075be9d7e8d4fac4b890b至a24edf72ab4ea2732af9f4bb507fda7160a3de2a。diff SHA256：483b052854ab5dc61f931c3b6c7e1f3bc8af9429cfc154c3230a69723a23122d。结论：允许集成Master；Critical0/Important0/Minor0。

Reviewer独立 exact-head 执行 pwsh -NoProfile -File scripts/verify.ps1 -SelfTest exit0，共49项（checker8、doctor2、structured4、ReviewPackage35）；无效YAML/TOML的FAIL文本为正确拒绝的负例。基线doctor配新版夹具稳定RED（隐藏PATH且带空格darwin-arm64目录中的真实Node未发现），新版GREEN。Windows/Linux x64候选目录字面值保留；M0原生运行仍NOT_RUN。独立doctor -CheckDocker在沙箱exit2，工具版本通过但Docker不可达，未把该次当容器PASS；Owner已正常权限流程单独验daemon通过。源码只读、最终树干净、diff --check exit0。

风险低、容易回退；平台回归保护部分，信心中等。无新增依赖、CI修改、越权路径、命中秘密或新安装/环境修改/服务启动。审核仅A，不批准整体M0或main；Master按此结论合入3ca9c9713409d5217024afec6216a281a8ea5f3e。

## Master 进行中审查

固定范围25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1至3ca9c9713409d5217024afec6216a281a8ea5f3e。已发现Minor：baseline-selftest.txt多余末尾空行造成git diff --check exit2；Master仅去掉多余日志空行，保留实际输出语义，并对完整Base至工作树diff复验exit0。原Windows/Linux及三工程锁文件diff空。最终Master/B和ZIP结论待补记，不提前称完成。

## Master 阶段审查回报

Reviewer在3ca9c971固定提交的独立临时Git快照执行locked restore/build/MTP4项/format，均exit0，ASPIRE010保留。六份锁恢复后逐字节与快照一致，既有五锁与阶段Base完全相等；Mac/Linux共同依赖条目完全相等，只替换两项Aspire平台工具。新增Mac工具13.6.3的本地公开nuspec为MIT，NuGet官方源/contentHash匹配。Reviewer通过正常宿主网络权限下载官方发行物到内存，pnpm11.28.8 SHA512与registry/文档全等，PyYAML6.0.3 cp313 Mac ARM64 SHA256与PyPI/requirements全等，均MIT。静态verify149文件exit0。

Important：组合执行 pwsh -NoProfile -File scripts/verify.ps1 -SelfTest -RunNative -RunTests 时49项SelfTest通过，但随后NuGet SDK配置路径错误派生到.csproj/.nuget，AppHost/MSTest SDK解析失败exit1。Reviewer查阅了master/verify-integrated.txt实际失败输出，不认可分开运行通过替代组合入口。Master已交A Owner修复并明确暂停main集成。根因调查为PowerShell/.NET10将未设置的环境值通过普通null恢复成空字符串；需保留unset/empty/nonempty语义。最终修复和独立复核结果随后增量归档，不隐藏失败。

## 环境恢复 focused 复核与组合入口

A修复固定范围a24edf72ab4ea2732af9f4bb507fda7160a3de2a至88e6f7a38a97b71c81a57d9c578994cb0ed17865，diff SHA256：926b808bebd11f0bdbaba4f0948047b381ff00865e7777e3ff704a70c3df4d76。Reviewer独立运行新版Environment.Tests exit0、完整临时布局旧verify RED exit1明确PYTHONPATH(unset)改变；第一次临时布局缺parser/依赖的夹具失败没有计作RED。三处仅null使用NullString，空值/普通值保持，finally仍有效。diff --check exit0，树干净，无新增依赖/秘密/权限/越界，允许合入Master；真实组合命令仍为main前置门禁。

Master已合入修复并执行 pwsh -NoProfile -File scripts/verify.ps1 -SelfTest -RunNative -RunTests，exit0。checker8、doctor2、structured4、环境五变量三状态及结构化清理、ReviewPackage35/0失败，随后真实build0错误、format exit0、MTP4/4/0跳过，详见master/verify-final.txt。ASPIRE010原警告保留。此为Owner实际复验，最后由Reviewer核对提交证据后解除Important，不自批。

## 最终原始运行与B文档复核

Master固定9acab3fc5dbb5ff0f447c4c839f66766e71b69e4的独立临时快照在五相关变量初态unset时，受锁恢复后同一pwsh运行完整SelfTest/RunNative/RunTests exit0；build0错误、format0、MTP4/4且0跳过，ASPIRE010保留。该头全范围diff-check0，脚本与已审修复逐字节一致，原Important和Minor均解除；diff SHA256=52bc23c4892015b5d5397fe8cd5c41c639f7db9de8b6650ac0363d3995a0d021。

B初审发现运行材料只是转录，不能作为独立运行PASS，以及“秘密不落盘”过度表述；Master没有以此进main。B固定8d4c6e04c43f35d6f3dfa2d2cc4c10e53ac7c292已限定秘密主动写入边界并明确Owner转录来源，Reviewer允许以PARTIAL文档归档合入Master，原B Minor解除。

Master补原始运行证据固定182bc54bf418603b70c554ef33f636c74fb89a42。Reviewer独立核对实际执行源码、raw/records/HTTP JSON：平台/端口/卷/HTTP/Trace/子进程/cleanup均有真实失败判定，四资源原脚本持久化exit0原始输出一致；Trace JSON与raw全等，trace/parent/service/path15080/404匹配，401负例及认证200；四官方index摘要和ARM64输出匹配。没有Env dump；clean函数另用synthetic secret和URL token测试通过。首次DCP清理暂态FAIL保留，60秒有限等待不放宽退出0判定。

Reviewer独立只读docker ps-a exit0空、最终专用3卷精确匹配、定向lsof exit1空；静态verify172文件exit0，diff-check0。AppHost/版本锁无额外修改。结论：当前Critical0/Important0/Minor0，Master容器运行门禁解除；允许在最终集成头Linux CI成功和收尾差异核对后由Master进入main，最终ZIP仍须重开审查。没有第三次重启资源或读取Env秘密。源码/运行证据审核不是全面供应链/生产审计。
