# I1 真实浏览器延迟读取验收交接

状态：NOT_RUN，本Worker未启动主栈或浏览器。以下交Master在本轮真实已授权OIDC组合栈执行；不替代本轮API、RIOT或发布验收，不修改生产代码或预算。

每组使用独立页面，打开真实草稿并记录原始名称、revision和四源字节。所选Turtle使用仓库公开Synthetic源加注释，保持语法有效；不读取认证材料。用页面测试钩子延迟File.arrayBuffer，继续调用原生方法取得真实所选文件字节，期间不阻断其它UI交互：

```js
await page.evaluate(() => {
  const original = File.prototype.arrayBuffer;
  const held = new Map();
  window.__g3ImportRace = {
    pending: () => [...held.keys()],
    release: name => held.get(name)?.(),
    restore: () => { File.prototype.arrayBuffer = original; },
  };
  File.prototype.arrayBuffer = function () {
    const bytes = original.call(this);
    if (!this.name.startsWith("g3-race-")) return bytes;
    return bytes.then(value => new Promise(resolve => {
      held.set(this.name, () => { held.delete(this.name); resolve(value); });
    }));
  };
});
```

1. 名称/其它源：在本体源上传`g3-race-a.ttl`，等待pending含该文件；改名称，并切换事实源修改一条注释；release A。断言名称与事实源修改保留，本体源仅接收A内容。切回本体源导出，按原File字节逐字节比较BOM/CRLF/非BMP，不能用textarea的LF显示值替代字节验收。
2. 同源键入：挂起A，在同一本体源码框添加不同注释；release A。断言后发键入仍在，旧文件未覆盖。
3. 同源乱序：连续挂起A、B（文件名不同），先release B后release A。最终源必须为B。
4. 跨源乱序：本体源挂起A、事实源挂起B，先B后A。两个源均保留各自导入内容，名称不回退。
5. 草稿切换：干净草稿甲挂起A，此时尚未产生dirty；打开另一个真实授权草稿乙；release A。乙的名称、revision与源不变，不跳回甲。
6. 丢弃：先改名称制造dirty，再挂起A，点击显式丢弃；release A。原始名称/源保持，不能重新出现dirty。
7. 修订：先填变更理由及名称，挂起A，再保存成下一revision；release A。页面保持新revision，已保存源不被旧读取改成dirty。该步骤只执行已有授权真实草稿保存，不重试写请求。
8. 新建缓冲：干净草稿挂起A，点击新建/导入，输入新名称；release A，新建源应为空。反方向在空新建缓冲挂起A、打开乙、release A，再进入新建，源也不能残留隐藏的旧导入。

文件input在开始读取时已清空，files.length为0不能证明异步读取结束；须等待目标textarea实际值及dirty/导出断言完成。

每组记录实际sourceHead/runId/输入、操作、断言和异常，finally恢复File原型或关闭页面。`textarea.value`的CRLF规范化是浏览器行为，展示断言按LF比较；导出文件必须保持权威字节。任一步失败保留日志，不把Node hook单测或其它历史浏览器记录当真实GREEN。
