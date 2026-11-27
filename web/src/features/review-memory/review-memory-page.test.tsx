import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ontologyFixture, ONTOLOGY_ID } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole } from '@/test/utils';

import type { MemoryEntry, MemoryPage } from './api';

function entry(kind: MemoryEntry['kind'], id: string): MemoryEntry {
  return {
    id, ontologyId: ONTOLOGY_ID, kind, elementKind: 'entity_type', label: `${kind}-old`,
    detail: kind === 'rejected' ? { kind, reason: 'incorrect', labelEn: null, domain: null, range: null }
      : kind === 'renamed' ? { kind, toLabelZh: '新名', toLabelEn: null, elementId: 'element-1' }
      : { kind, otherLabel: '另一项', otherElementId: null },
    sourceChangeSetId: 'cs-source', sourceItemId: null, decidedBy: null, decidedByName: '王工',
    createdAt: '2026-11-20T08:00:00Z', hits: 2, lastHitAt: null,
  };
}

const entries = [entry('rejected', 'memory-1'), entry('renamed', 'memory-2'), entry('kept_apart', 'memory-3')];

function server(items: MemoryEntry[] = entries, role: 'viewer' | 'reviewer' = 'reviewer') {
  let current = [...items];
  const api = mockApi({
    'GET /api/ontologies': () => [ontologyFixture()],
    'GET /api/ontologies/:id/review-memory': ({ query }): MemoryPage => ({
      items: current.filter((item) => (!query.get('kind') || item.kind === query.get('kind')) && (!query.get('q') || item.label.includes(query.get('q') ?? ''))),
      nextCursor: null, total: current.length, max: 500,
    }),
    'DELETE /api/ontologies/:id/review-memory/:entryId': ({ params }) => { current = current.filter((item) => item.id !== params.entryId); },
    'POST /api/ontologies/:id/review-memory/:entryId/restore': ({ params }) => {
      const restored = entries.find((item) => item.id === params.entryId);
      if (!restored) return problemResponse(409, 'review_memory.not_restorable');
      current.push(restored);
      return restored;
    },
    'POST /api/ontologies/:id/review-memory/clear': () => { const cleared = current.length; current = []; return { cleared }; },
  }, { user: userWithRole(role) });
  return api;
}

describe('review memory page', () => {
  it('renders all three kinds and highlights the linked entry', async () => {
    server();
    renderApp('/review/memory?ontology=onto-steel&entry=memory-2');
    const table = await screen.findByRole('table', { name: '审核记忆列表' });
    expect(within(table).getByText('rejected-old')).toBeInTheDocument();
    expect(within(table).getByText('renamed-old → 新名')).toBeInTheDocument();
    expect(within(table).getByText('kept_apart-old ↔ 另一项')).toBeInTheDocument();
    expect(within(table).getByText('不正确')).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: /renamed-old/ })).toHaveAttribute('aria-current', 'true');
  });

  it('sends category and debounced search through the URL', async () => {
    const api = server();
    const user = userEvent.setup();
    const { router } = renderApp('/review/memory?ontology=onto-steel');
    await screen.findByRole('table', { name: '审核记忆列表' });
    await user.selectOptions(screen.getByLabelText('类别'), 'renamed');
    await waitFor(() => expect(router.state.location.search).toMatchObject({ kind: 'renamed' }));
    await user.type(screen.getByLabelText('搜索'), 'renamed');
    await waitFor(() => expect(router.state.location.search).toMatchObject({ q: 'renamed' }), { timeout: 2000 });
    await waitFor(() => expect(api.calls('GET', `/api/ontologies/${ONTOLOGY_ID}/review-memory`).at(-1)?.query.get('q')).toBe('renamed'));
  });

  it('shows an empty next step and hides management for viewers', async () => {
    server([], 'viewer');
    renderApp('/review/memory?ontology=onto-steel');
    expect(await screen.findByText('还没有审核记忆')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review?ontology=onto-steel');
    expect(screen.queryByRole('button', { name: '清空' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '删除' })).not.toBeInTheDocument();
  });

  it('shows a no-results state for filters', async () => {
    server([]);
    renderApp('/review/memory?ontology=onto-steel&kind=rejected');
    expect(await screen.findByText('无结果')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '清除筛选' })).toBeInTheDocument();
  });

  it('shows forbidden for a 403 response', async () => {
    mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/review-memory': () => problemResponse(403, 'auth.forbidden'),
    });
    renderApp('/review/memory?ontology=onto-steel');
    expect(await screen.findByText('没有访问权限')).toBeInTheDocument();
  });

  it('loads the next cursor', async () => {
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/review-memory': ({ query }): MemoryPage => ({
        items: query.get('cursor') ? [entries[1]!] : [entries[0]!], nextCursor: query.get('cursor') ? null : 'next', total: 2, max: 500,
      }),
    });
    const user = userEvent.setup();
    renderApp('/review/memory?ontology=onto-steel');
    await user.click(await screen.findByRole('button', { name: '加载更多' }));
    expect(await screen.findByText('renamed-old → 新名')).toBeInTheDocument();
    expect(api.calls('GET', `/api/ontologies/${ONTOLOGY_ID}/review-memory`)[1]?.query.get('cursor')).toBe('next');
  });

  it('retries a failed list request', async () => {
    let failed = true;
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/review-memory': () => {
        if (failed) return problemResponse(500, 'test.failure');
        return { items: entries, nextCursor: null, total: 3, max: 500 };
      },
    });
    const user = userEvent.setup();
    renderApp('/review/memory?ontology=onto-steel');
    await screen.findByRole('button', { name: '重试' });
    failed = false;
    await user.click(await screen.findByRole('button', { name: '重试' }));
    expect(await screen.findByRole('table', { name: '审核记忆列表' })).toBeInTheDocument();
    expect(api.calls('GET', `/api/ontologies/${ONTOLOGY_ID}/review-memory`).length).toBeGreaterThan(1);
  });

  it('deletes with undo and confirms clearing with the count', async () => {
    const api = server();
    const user = userEvent.setup();
    renderApp('/review/memory?ontology=onto-steel');
    await screen.findByRole('table', { name: '审核记忆列表' });
    await user.click(screen.getAllByRole('button', { name: '删除' })[0]!);
    expect(await screen.findByText('已删除')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '撤销' }));
    await waitFor(() => expect(api.calls('POST', `/api/ontologies/${ONTOLOGY_ID}/review-memory/memory-1/restore`)).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: '清空' }));
    expect(screen.getByText(/清空 3 条。清空后 AI 不再参考这些决定/)).toBeInTheDocument();
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '清空' }));
    await waitFor(() => expect(api.calls('POST', `/api/ontologies/${ONTOLOGY_ID}/review-memory/clear`)).toHaveLength(1));
  });

  it('reports when undo is no longer possible', async () => {
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/review-memory': (): MemoryPage => ({ items: entries, nextCursor: null, total: 3, max: 500 }),
      'DELETE /api/ontologies/:id/review-memory/:entryId': () => undefined,
      'POST /api/ontologies/:id/review-memory/:entryId/restore': () => problemResponse(409, 'review_memory.not_restorable'),
    });
    const user = userEvent.setup();
    renderApp('/review/memory?ontology=onto-steel');
    await user.click((await screen.findAllByRole('button', { name: '删除' }))[0]!);
    await user.click(await screen.findByRole('button', { name: '撤销' }));
    await waitFor(() => expect(api.calls('POST', `/api/ontologies/${ONTOLOGY_ID}/review-memory/memory-1/restore`)).toHaveLength(1));
    await waitFor(() => expect(Array.from(document.querySelectorAll('h2')).map((heading) => heading.textContent)).toContain('这条记忆已不能撤销'));
    expect(api.calls('POST', `/api/ontologies/${ONTOLOGY_ID}/review-memory/memory-1/restore`)).toHaveLength(1);
  });
});
