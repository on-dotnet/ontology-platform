# 第一轮独立Review修复的实际RED

固定Review Base：575b41f91844d543662c2423be91fd35e8675888。以下M1/CAS输出为会话实际输出摘录转录，SSE完整进程输出另见review-round1-sse-red.txt。

- I1/I2：17个SSE用例中8 FAIL / 9 PASS。七个缺字段/冲突snapshot/未知或非互斥SemanticDatum的Promise错误resolved；70条message.delta（各4096 ASCII、seq1..70）同chunk在旧全chunk262144限制触发event_budget_exceeded。没有以类型错误或改断言伪造RED。
- M1浏览器3/3 FAIL：BOM源下载缺少239/187/191三个UTF8字节；非法UTF8没有alert且替换了缓冲；absent术语仍允许导出伪空文件。BOM/CRLF源由16B变13B。
- CAS浏览器1 FAIL：在新事件已展示而后续Run快照请求仍挂起时，取消请求expectedRevision实际0，预期1。
- M2：git diff --check 69e2ed746e376a36cf3a32d3ee39992b85007c36 HEAD退出2：verify-selftest-logformat-red.txt:6 new blank line at EOF。只删除额外EOF空行，保留原红内容。
- UTF8单元测试初次出现4个测试参数展开错误：it.each数组使回调收到数字、构造全零Uint8Array；改为具名bytes字段后真实非法字节检查通过。该错误不计产品RED。

GREEN覆盖：完整SSE17正反例、9种合法载荷/三种SemanticDatum分支、8个UTF8字节用例；浏览器验证拒绝后的回读、BOM/CRLF/no-op、非法UTF8不改缓冲、absent与取消CAS。最终计数以review-round1-*实际命令输出为准。
