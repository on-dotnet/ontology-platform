# BuildKit history后验回现：根因与受限纠偏

最终审查发现原18 history在原532条日志success/即时absent、两个独立after核对后重新可见。原原始日志与时点快照不改写；但撤回18项持久完成结论。其余248操作的Git/Docker精确差集持续生效。后验快照docker-postreview-drift.json实际0containers/24volumes/11images/19history，bridge又变化；没有额外执行删除、强制清理、daemon restart或配置变更。

## 已证实的官方固定版本机制

本机Buildx v0.38.1 commit0dbe87f36ed472fe36b6796c3f70b4210a731fc5；BuildKit v0.34.0，desktop-linux单docker节点。同socket与Engine ID7a8785bb-6b6e-4ae4-8065-996f4bf83016。只读进程metadata显示com.docker.virtualization新PID45130在2026-10-27 00:38:32+08启动；bridge Created=2026-10-26T16:38:33.525169041Z，ID0c59496530c0d24e621a6aa825c4427b849ab3b171c78e53bd77b571df9d954a。backend/UI仍从10月25日存活。

Docker调查和独立cleanup_review均核验官方tag源码：[BuildKit v0.34.0 history queue](https://github.com/moby/buildkit/blob/v0.34.0/solver/llbsolver/history/buildhistory.go)、[Buildx v0.38.1查询](https://github.com/docker/buildx/blob/v0.38.1/commands/history/utils.go)、[删除](https://github.com/docker/buildx/blob/v0.38.1/commands/history/rm.go)、[inspect](https://github.com/docker/buildx/blob/v0.38.1/commands/history/inspect.go)。原raw buildhistory.go21608 bytes SHA256a0b141c717fa35061680e3ebcb24fc97baa5b141bd18b5090b56017b03e00599。

单Ref Listen结束减计数到0而留下map键；随后Delete只判断键存在，写内存deleted并返回成功，不触及DB。列表过滤deleted，rm后新单Ref请求又在注册defer前被deleted拒绝，不能补做DB删除。NewQueue重建内存map后DB旧记录重新可见。本次先逐Ref inspect再rm、即时absence、自然VM更新后原18回现，与这条已确定存在的机制高度吻合；未直接读取内存/私有DB，不能冒称观察过内部状态。

[官方Resource Saver说明](https://docs.docker.com/desktop/use-desktop/resource-saver/)空闲时可停Linux VM，默认五分钟；本次零容器到新VM的时序吻合，但未读本机全局设置，触发原因为推断/NOT_VERIFIED，不能直接定论。无events回传不代表未重启。

## 修复合同

1. 只用ref-only ls定位^offset；官方Buildx将offset转空server Ref，不产生单Ref零键。offset读取只投影原7允许字段，强制返回Ref==target和全fingerprint；列表位移/越界/其他记录拒绝，不凭offset执行rm。
2. history计划新增精确historyBackend：context、EngineID、bridge generation、完整Buildx版本、BuildKit版本、driver、单node身份。当前仅审核Buildx0.38.1/BuildKit0.34.0/docker desktop-linux单节点；变化fail closed。仅只读network metadata，不提供网络删除。
3. rm后列表缺席不足以PASS。固定CLI精确无DB记录诊断必须为stderr单条`ERROR: no record found for ref "<准确ID>"`、stdout空、exit1；deleted、错误Ref、transport/权限/其它文本一律failed/NOT_VERIFIED，raw stderr不打印。诊断前后重验同backend generation。原CLI rm exit0仍准确记录，不能改写。
4. 当前已污染内存无普通安全CLI清键入口。不造RPC/流时序竞态、不碰内部DB、不主动全局restart/update/prune/配置。代码/CI期间暂停本地Docker读取/streams以保留已有自然idle机制；之后只有实际观察新的VM generation才能按仅原18子计划重验。时间经过不是成功。最后还需自然generation变化后的只读持久检查。

新增mock实现在内存deleted过滤与持久DB分离，精确复现原工具CLI0/list absent却重启后回现。真实tmp/mock全40 tests，旧工具RED9处失败；GREEN及独立Review/实际二次18计划结果随后补充，不预填完成。
