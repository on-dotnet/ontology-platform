"use client";
/** 路由异常边界仅显示通用信息，不向页面暴露异常内容。 */
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main id="main" className="standalone" role="alert">
    <h1>工作台暂时不可用</h1>
    <p>请求未能完成，请重新尝试。</p>
    <button className="button primary" onClick={reset}>重试</button>
  </main>;
}
