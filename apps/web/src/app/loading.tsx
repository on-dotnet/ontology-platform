/** 路由等待期间保留明确的可访问加载状态。 */
export default function Loading() {
  return <main id="main" className="standalone" role="status">
    <div className="brand-mark">O</div>
    <h1>正在连接工作台</h1>
    <p>正在验证当前会话与授权范围…</p>
    <div className="skeleton" />
  </main>;
}
