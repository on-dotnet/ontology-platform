# 只读盘点器独立审查

package_review在真实临时Git仓库独立复现并要求修复：保护祖先路径/后代keep及关联refs、未知ignored/private路径、Root符号链接别名、cache中的.runtime/.ssh/.aws。另用Git命令故障注入证明ignored ls-files exit13必须阻断，不能把读取失败视为空清单；Master纳入ignoredExitCode==0资格判断，失败AMBIGUOUS传播关联refs KEEP。所有检查仅metadata、不写Git索引。

Master真实回归8/8 PASS；独立Reviewer最新实际8/8 PASS（9.444s），自建exit13故障也正确AMBIGUOUS→关联refs KEEP，I1/I2/I3全部关闭，C0/I0/M0。IncludeDocker独立exit0/OBSERVED，7查询全0；SAFE容器2/卷24/镜像13/history18，KEEP卷24/镜像10。精确RED原始失败见inspector-review-red.txt；exit13额外RED来自Reviewer自建故障fixture。公开private-use.json仅路径分类例外，Apply仍要求精确public22bytes/hash及全部metadata指纹，检查器推荐分类不能替代Apply。

Minor分类纠偏：官方caniuse credential-management.js及pnpm-store index.db被过宽regex误报。现按Apply相同PRIVATE路径segment规则分类，保留.tools/security额外保护；新增公开包名正例后Master实际9/9 PASS。执行前必须fresh状态与完整Apply guards，不能只用名称判断。

最终package_review独立9/9 PASS、exit0，C0/I0/M0。真实默认16树=6KEEP+10SAFE，ignored全部exit0；mutations=[]；精确Inspector SHA25699fdfefc078a7849d1e9fab29b50174685598dd0c3866092b06ca51068fd0a08。
