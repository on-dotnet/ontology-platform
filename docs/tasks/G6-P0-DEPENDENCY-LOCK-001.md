# G6-P0-DEPENDENCY-LOCK-001

状态：PARTIAL / BLOCKED_WITH_WITNESS。G3 main=d1a61daffe844475b07705797e3ad325cc3f2945；G6 PREP=851fa7eb2153c660b7989c0a7a6dd0e1c8e1b63c，未合并；G4仍未启动。

用户2026-11-01明确批准附件唯一合同，不修改仓库历史授权索引。ZIP SHA256=5ef82ae56fb5227f8221d1659eb88b62a4f776616d0e1e937b14e080f584f94e。权威原字节见本任务 evidence/input 的03合同source.json；01/02是路线背景，不增加授权。

BaseSha：851fa7eb2153c660b7989c0a7a6dd0e1c8e1b63c。分支 codex/g6-p0-dependency-lock-001；托管Worktree g6-p0-dependency-lock-001/ontology-platform。交付Head由外置构包Manifest权威记录，避免自引用。

Master唯一实施；非作者 Reviewer GPT-6 Astra / High，只读，无Worker。owned_paths：experiments/g6-p0/locks/**、本任务卡、docs/evidence/G6-P0-DEPENDENCY-LOCK-001/**。其它全部只读，包括scripts、历史metadata、G3、后端/前端/infra和公共规则。无产品DI/审计/长整栈消费者变化。

先冻结四extras、两平台与拒绝规则；仅复用元数据与既有PEP解析器，不实现版本搜索器。负例覆盖URL/路径/重复/异常metadata、平台ABI、Requires-Python、pin、yanked与伪READY。验证入口：python3 -B -m unittest discover -s experiments/g6-p0/locks/tests -v；python3 -B experiments/g6-p0/locks/observe.py；verify -SelfTest一次；test-review-evidence；独立Review与唯一LOCAL V3重开。

历史失败→最早门禁：pip dry-run可下载→源码能力检查；PREP extras过宽→新根重新传播；宿主污染→显式目标marker；未知patch/glibc→条件状态；metadata伪lock→拒绝READY；预检只支持M1–M5→记录G6不适用，不误跑M5。PREP72测试按输入blob复用，不重跑无关整栈。

未授权：新工具安装、wheel/sdist/模型/镜像下载、真实解析/Docker/API/key/生产数据、main合并。下一单项授权草案见locks/install-authorization-draft.md。提交push仅本分支；唯一V3交付后等待ChatGPT独立复审，不进入后续阶段。
