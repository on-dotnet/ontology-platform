import type { SemanticSupportProfile } from "../../lib/api/g2-generated";

/** 服务端版本化能力档案；四个维度逐项展示，不把源码保留解释成编辑或推理支持。 */
export function SupportProfile({ profile, loading, failed, onRefresh }: {
  profile: SemanticSupportProfile | null;
  loading: boolean;
  failed: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="g2-stack" aria-label="语义支持档案">
      <div className="g2-row">
        <h2>M1 语义支持档案</h2>
        <button className="button" disabled={loading} onClick={onRefresh}>刷新支持档案</button>
      </div>
      {!profile ? (
        <p className="g2-notice" role="status">
          {loading ? "正在读取服务端支持档案…" : "UNKNOWN · 支持档案未取得，不能确认发布资格。"}
          {failed && " 服务请求失败，可刷新重试。"}
        </p>
      ) : (
        <>
          <p>{profile.profileId} · v{profile.version} · {profile.reasoningMode}</p>
          <p className="g2-hash">profile hash {profile.hash}</p>
          <p className="muted">只使用已断言事实；OWL 推理 NOT_RUN，不联网加载 imports。SHACL 约束与 OWL 公理分开。</p>
          <p className="muted">BASIC 为现有结构编辑；SOURCE 为专家源码编辑；EXACT 为原文保留；BLOCKED 为禁止发布。</p>
          <p className="muted">rdfs:domain/range 不代表必填或任选其一；allValuesFrom 不保证存在关系；Functional 不等于数据库唯一键。</p>
          {profile.capabilities.length !== 20 && <p className="g2-notice">UNKNOWN · 预期20项，服务端返回{profile.capabilities.length}项。</p>}
          <div className="g3-profile-table" tabIndex={0} role="region" aria-label="20项能力矩阵，可横向滚动">
            <table>
              <caption>编辑、保留、发布和验证分别说明能力边界</caption>
              <thead><tr><th scope="col">能力</th><th scope="col">编辑</th><th scope="col">保留</th><th scope="col">发布</th><th scope="col">验证</th></tr></thead>
              <tbody>
                {profile.capabilities.map(item => (
                  <tr key={item.id}>
                    <th scope="row">{item.id} · {item.name}<p className="muted">{item.reason}</p></th>
                    <td>{item.edit}</td><td>{item.preserve}</td><td>{item.publish}</td><td>{item.validation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            四源比较共享预算：每图 {profile.comparisonBudget.maxBlankNodes} blank nodes；
            {profile.comparisonBudget.maxSearchNodes} 搜索节点；{profile.comparisonBudget.timeoutMilliseconds} ms。
            耗尽或取消为 INDETERMINATE，不能认定无差异。
          </p>
        </>
      )}
    </section>
  );
}
