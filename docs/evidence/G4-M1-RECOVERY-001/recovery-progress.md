# 恢复实施进展（非最终交付）

当前唯一授权仍为G4-M1-RECOVERY-001；未合main，未动G3/G6，不进入M2。非作者Reviewer为`/root/recovery_reviewer`；模型身份NOT_VERIFIED。全部当前资源、输入及失败原始记录保存在本任务ignored artifacts，最终提交输入绑定/49项矩阵/V3尚未完成，不将本页视作交付回执。

## 已完成增量与独立复核

- 64KiB真实Kestrel固定长度、chunked无Content-Length和HTTP2：18项通过；原8项失败证据保留。
- 四个固定ARM64镜像均逐镜像独立AMBER-A1，仍为LICENSE_PARTIAL；不代表商业合规。详见r3-review。
- 真实PG TLS、只读拒绝、错误CA/SAN及权限核验通过，PG catalog sequence类型守卫实际负例通过。
- HTTP baseline 135请求：13完整矩阵项通过，其余不自动提升；报告http-d46c95ce-fc2c-4ece-9e05-a5d215d13ea6。
- 实际UI发现canonical平台角色误判，修复后三文件流程U01–U04通过（browser-23b091a6-2814-4b0a-989d-b2d9baf87997）。U06原窄屏截图被独立审查撤回FAIL：拍在0.2秒sidebar过渡中。保留原图；严格稳定布局/点击命中检查后新四图独立视觉通过（browser-8e65806d-971f-4735-8153-62d3fd0f5288，共334209字节）。
- 实际schema ADD/DROP发现旧快照未标STALE，修复CanonicalCatalog共享排序与fingerprint判定。新字段出现/删除后历史快照字节保持不变、公开投影及STALE变化实测；尚未提交源码。
- E07审计start与complete分别精确触发器故障：503不产生成功状态；start事务完全回滚后同命令成功；complete保留RUNNING后恢复同Probe为TEST_FAILED、同命令无重复审计/实体。非作者独立PASS，两个触发器/函数实际count0。start SHA 3a90642b4fba0ccee36077aad10630e7db10a04c23b2722f9c6a093a721bbb5e；complete SHA e045e5e6aaec9e365adb6b4750f8d0143b36c31d57c3b5d7ab275525b43cf03a。
- 真实10秒TLS超时原错误归为CANCELLED：browser-200826c2-53cd-478d-9ccc-28832d066dfe。修复只在应用deadline到期且原请求未取消时重分类诊断，保留时限与真实阶段。相同真实超时复验TEST_FAILED/source_unavailable；1.5秒浏览器Abort负例对应CommandKey的持久Probe仍CANCELLED/connection_cancelled。非作者双向审查PASS。source-timeout-fixed SHA 001a3e12d523878c4b6aec7a568c553dca7c7dd19f5ea37db6fc5a7cd4501afc；client-cancel-fault SHA 9560f58cf6884d168b35f70bfcd370b8451da159e72bfe477f4f0b147ad6cda9。源最终Paused=false。
- 权限不足HTTP实测PARTIAL，但页面在目录GET403后清掉已授权Job诊断，原真实FAIL保留。Worker最小修复CatalogPanel：目录拒绝清空历史/快照，重验connection/job授权再仅显示诊断，真正401/范围拒绝保持全清；迟到结果有代际保护。101组件测试通过，tsc/ESLint/diff通过，非作者审查PASS；真实页面待重建复验。

## 租约故障实验的廉价失败与纠正

1. create不支持--no-deps，实测exit1，未创建资源。改实际支持的--no-build --no-recreate --pull never，service无depends_on；原Review漏项明确保留。
2. pg_attribute准确锁也阻塞临时新监测查询：运行短失败。改预先建立PREPARE/generic plan，独立短测试同锁下EXECUTE成功，锁与observer退出0。
3. 任务RUNNING提交后立即pause导致源IO尚未开始，严格source wait断言失败。改≤2秒等待实际源reader Lock后pause，55秒源锁/100秒API绝对守卫保持。每轮失败均实际恢复API、锁0、observer退出0、精确副本删除，原证据未覆盖。

会话中断使宿主入口与监测进程退出；原容器仍运行。重新只读能源preflight为AC sleep=0/POLICY_READY，锁屏连续性NOT_VERIFIED；恢复独立有界入口和监测。未改变全局能源策略。

## 已确认的授权边界 witness

非作者完整附件审查确认：C08 SourceConfig有效变更目前没有第二个合法安全profile，`Pg()`与Adapter/G4Rules只允许固定pg-source:5432/fixture/fixture_reader/VerifyFull/单production。displayName及SecretVersion变化只闭合各自子项；SourceConfig子项保持NOT_RUN。最小解除条件：人类明确授权第二个准确受控合成profile，或ChatGPT独立复审明确裁定此子项本固定profile阶段不适用。本轮不自改验收要求。

R04真实G3发布/查询主要服务启动保持NOT_RUN：恢复合同R1明确仅四候选、不添加Fuseki/RustFS/额外镜像；没有已准入正在运行的G3主要栈可直接验收。不启动额外服务或读取共享持久数据来凑PASS。真实认证/CSRF及G3合同/生成兼容分项仍需实测/核对后分别记录。最小解除条件：额外明确批准准确镜像/资源/隔离与合成输入，或提供已准入可复用且不触及正式数据的准确现成环境。

以上授权缺口决定本轮最终只能BLOCKED_WITH_WITNESS；其余授权内修复、验收、准确资源回收、已提交输入绑定与唯一V3交付继续。
