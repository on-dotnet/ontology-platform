/** 验收只读查询客户端；生产并发保护和写命令不在此修改。 */
export async function postSemanticRead(api, url, options, observe = () => {}) {
  const readOnlyQuery = new URL(url).pathname === "/api/v1/semantic/queries";
  for (let attempt = 1; attempt <= 5; attempt++) {
    const started = performance.now();
    const response = await api.post(url, options);
    const elapsedMs = performance.now() - started;
    let busy = false;
    if (readOnlyQuery && response.status() === 429) {
      try { busy = (await response.json()).code === "semantic_busy"; } catch { /* 非标准正文失败关闭。 */ }
    }
    const waitMs = busy && attempt < 5 ? 250 * 2 ** (attempt - 1) : 0;
    const fact = { attempt, status: response.status(), code: busy ? "semantic_busy" : null,
      waitMs, observedWaitMs: waitMs ? null : 0, elapsedMs };
    if (!waitMs) {
      observe(fact);
      return response;
    }
    const waiting = performance.now();
    await new Promise(resolve => setTimeout(resolve, waitMs));
    fact.observedWaitMs = performance.now() - waiting;
    observe(fact);
  }
  throw new Error("unreachable_bounded_read_loop");
}
