"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type * as G4 from "../../lib/api/g4-generated";
import { command } from "../../lib/api/g2-client";
import { PlatformApiError } from "../../lib/api/client";
import { createMappingsClient, MappingApiError } from "./api";
import { useMappingWork } from "./model";
import { MappingError, MappingNavigation, MappingJobPanel } from "./assessment";
import "./mappings.css";
const client = createMappingsClient();

/** 历史发布有原件和当前投影两部分，刷新只读取，不自动回滚。 */
export function MappingReleaseHistory({ mappingId, onDenied }: { mappingId: string; onDenied?: () => void }) {
  const [page, setPage] = useState<G4.MappingPageOfMappingReleaseView | null>(null);
  const [active, setActive] = useState<G4.MappingActiveView | null>(null);
  const work = useMappingWork(() => { setPage(null); setActive(null); onDenied?.(); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    void Promise.all([client.releases(mappingId, undefined, controller.signal), client.active(mappingId, controller.signal).catch(cause => {
      if (cause instanceof PlatformApiError && cause.status === 404) return null;
      throw cause;
    })]).then(([history, pointer]) => { if (!controller.signal.aborted && work.current(generation)) { setPage(history.data); setActive(pointer?.data ?? null); } })
      .catch(cause => { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); });
    return () => controller.abort();
    // 同mapping历史仅GET恢复，不能触发发布。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappingId]);
  return <section className="mapping-card"><h2>当前指针与正式历史</h2><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {active && <p>激活版本 {active.activationRevision} · {active.usable ? "当前可用" : `需要重新验证：${active.reasonCodes.join("、")}`}</p>}
    {!page && !work.error && <p role="status">正在读取发布历史…</p>}{page && !page.items.length && <p>尚无正式映射发布。</p>}
    <ul>{page?.items.map(item => <li key={item.manifest.mappingReleaseId}><Link href={`/data/mapping-releases/${encodeURIComponent(item.manifest.mappingReleaseId)}`}>{item.manifest.mappingReleaseId}</Link> · {item.projection.active ? "当前指针" : "历史原件"} · {item.manifest.createdAtUtc}</li>)}</ul>
    {page?.nextCursor && <button disabled={work.busy} onClick={() => void work.run(() => client.releases(mappingId, page.nextCursor!), result => setPage(result.data))}>下一页发布</button>}
  </section>;
}

/** U11回滚先验证固定旧Release，仍须新提案和异人审核，不直接切指针。 */
export function MappingReleasePage({ id, canEdit }: { id: string; canEdit: boolean }) {
  const router = useRouter();
  const search = useSearchParams();
  const jobId = search.get("job");
  const [release, setRelease] = useState<G4.MappingReleaseView | null>(null);
  const [active, setActive] = useState<G4.MappingActiveView | null>(null);
  const [diff, setDiff] = useState<G4.MappingDiffView | null>(null);
  const work = useMappingWork(() => { setRelease(null); setActive(null); setDiff(null); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    async function read() {
      try {
        const result = await client.release(id, controller.signal); const mappingId = result.data.manifest.mappingId;
        const pointer = await client.active(mappingId, controller.signal);
        if (controller.signal.aborted || !work.current(generation)) return;
        setRelease(result.data); setActive(pointer.data);
      } catch (cause) { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); }
    }
    void read(); return () => controller.abort();
    // 历史发布始终使用URL固定ID，不加载最近发布替代它。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  function rollback() {
    if (!release) return;
    const body: G4.MappingValidateRequest = { target: { kind: "ROLLBACK", targetReleaseId: id, manifestHash: release.manifestHash },
      command: command(release.projection.currentDraftRevision, "验证固定历史映射的当前兼容性") };
    void work.run(() => client.validate(release.manifest.mappingId, body, `"mapping:${release.projection.currentDraftRevision}"`), result => router.push(`/data/mapping-releases/${encodeURIComponent(id)}?job=${encodeURIComponent(result.data.jobId)}`));
  }
  return <div className="mapping-workspace"><MappingNavigation /><h1>不可变映射发布</h1><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!release && !work.error && <p role="status">正在校验历史原件与当前读取权限…</p>}{release && <>
      <section className="mapping-card"><h2>{release.projection.active ? "当前发布" : "历史发布"}</h2><p className="mapping-hash">原制品散列：{release.manifestHash}</p><p>当前使用状态：{release.projection.usable ? "可用" : release.projection.reasonCodes.join("、")}</p><p>原提交者：{release.manifest.reviewReceipt.submittedBy}；原独立审核者：{release.manifest.reviewReceipt.decidedBy}</p><p>历史来源修订 {release.manifest.originDraftRevision}；当前编辑修订 {release.projection.currentDraftRevision}。两者不同不会自动禁止回滚。</p><details><summary>原始固定版本</summary><pre>{JSON.stringify(release.manifest.binding, null, 2)}</pre></details><details><summary>完整原始映射定义</summary><pre>{JSON.stringify(release.manifest.mapping, null, 2)}</pre></details></section>
      {active && active.mappingReleaseId !== id && <section className="mapping-card"><h2>与当前指针比较及回滚</h2><p>回滚前需要当前七项兼容验证、新提案和异人审核。历史Manifest不会重写。</p><div className="mapping-actions"><button disabled={work.busy} onClick={() => void work.run(() => client.releaseDiff(release.manifest.mappingId, active.mappingReleaseId, id), result => setDiff(result.data))}>比较当前发布与此原件</button>{canEdit && <button disabled={work.busy} onClick={rollback}>开始固定目标的回滚验证</button>}</div>{diff && <><p>比较原件：{diff.fromHash} → {diff.toHash}</p>{!diff.changes.length ? <p>没有结构差异。</p> : diff.changes.map(change => <details key={change.path}><summary>{change.path || "/"}</summary><pre>{change.beforeExists ? JSON.stringify(change.before, null, 2) : "字段缺席"}</pre><pre>{change.afterExists ? JSON.stringify(change.after, null, 2) : "字段缺席"}</pre></details>)}</>}</section>}
      {jobId && <MappingJobPanel jobId={jobId} mappingId={release.manifest.mappingId} canEdit={canEdit} onDenied={() => work.fail(new MappingApiError(403, "mapping_forbidden"))} />}
      <Link href={`/data/mappings/${encodeURIComponent(release.manifest.mappingId)}`}>返回永久映射</Link>
    </>}
  </div>;
}
