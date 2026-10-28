# E0 独立审查及整改记录

Reviewer=/root/e0_independent_review，只读。冻结组合快照 /private/tmp/g3-m3-e0-review-20261028.patch，210709 bytes，SHA256 cfd58f2dfe95e36b7a910bf27eb09943bae8c559155452c6c4184b9ba0ddde57。绑定 Base c8f1040829b2bfe1e9f7e36223092286975643f0、Master 2f426f7及当时未提交E0差异；不是最终已提交Head。

结论NEEDS_REVISION / PARTIAL。确定P1：M3上游三模式向full-g2-e2e.py传入未支持参数，exit2且未启动Smoke。已加入实际argparse与命令构造回归，首次RED exit1，修复GREEN 13/13；新增JS分支及M3子模块仍须准确差异复审与真实运行。

其余已检查缓存信任/内容与平台验证、失败短复现、删除白名单/backend/严格no-record、证据schema/JSONL边界未发现第二个确定P1/P2。AppHost及g2-integration后补failure-state调用、命令文档EvidenceFile纠正属于追加差异，待复审。

真实export/load、两个独立runner cold→restore、输入变化miss、Smoke故障/恢复、精确Docker fixture与项目Apply、自然代际history后验、最终同Head CI均待运行；单元正反例不能替代。

## 后续审查（真实Linux归档及scope分流）

Reviewer e0_independent_review发现并确认两个P2：官方Moby导出V1 metadata未被允许；GitHub表达式忽略字符串大小写使首版精确ref guard测试语义不成立。前者由独立worker严格修复中（Run40700463473真实UNREFERENCED_MEMBERS证明），后者已改readonly scope job+真实Python比较，追加大写ref/marker正反例，Reviewer定向复核确认P2闭合且无新确定P1/P2。所有诊断运行仍fullCI NOT_VERIFIED。LayerSources内容/DiffID/size/platform绑定本身未发现新增安全绕过；仅58cache+20canonical fixture通过不等于产品cache完成。
