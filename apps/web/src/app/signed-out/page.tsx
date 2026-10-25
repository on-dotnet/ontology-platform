/** 公开注销完成页，不包含身份或认证材料。 */
export default function SignedOut() {
  return <main id="main" className="auth-page">
    <section className="auth-visual">
      <div className="brand">
        <span className="brand-mark">O</span> Ontology<span className="brand-suffix">Platform</span>
      </div>
      <div className="orbital">
        <span />
        <span />
        <span />
        <i />
        <i />
        <i />
      </div>
      <div>
        <p className="eyebrow">CONNECTED KNOWLEDGE. TRUSTED ACTION.</p>
        <h1>让知识有序连接<br />让每次访问有据可循。</h1>
        <p>统一语义 · 可信身份 · 可追溯治理</p>
      </div>
      <small>平台开发环境 / G1 WAVE 2</small>
    </section>
    <section className="auth-panel">
      <span className="tag teal">安全会话</span>
      <h2>已安全退出</h2>
      <p>当前平台会话已结束。使用组织身份重新登录，继续访问授权范围内的资源。</p>
      <a className="button primary" href="/auth/login?returnUrl=/">使用组织身份登录 <span aria-hidden="true">↗</span>
      </a>
      <div className="auth-note">
        <span className="status-dot" /> 由 Keycloak 提供身份验证<br />
        <small>权限由平台服务端验证，浏览器不保存身份令牌。</small>
      </div>
    </section>
  </main>;
}
