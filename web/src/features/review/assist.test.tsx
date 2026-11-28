import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { changeSetFixture, elementFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import { jsonResponse, mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import { changeSetKeys, highConfidencePending, type AssistRisk, type ChangeItem, type ItemPatch, type ReviewAssist } from './api';

const item = itemFixture();
const other = itemFixture({ id: 'other', seq: 2, tempRef: 'new:Other', proposed: { localName: 'Other', labelZh: '其他' } });
const ruleRisk: AssistRisk = { code: 'naming', source: 'rule', detail: 'local_name_style',
  reason: null, relatedItemIds: [], relatedElementIds: [], memoryEntryId: null };
const assist: ReviewAssist = {
  id: 'assist-1', changeSetId: 'cs-converter', status: 'done', errorCode: null,
  aiUsed: true, truncated: false, locale: 'zh-CN', requestedBy: null, requestedByName: null,
  createdAt: '2026-11-27T00:00:00Z', finishedAt: '2026-11-27T00:00:01Z', summary: '请逐项确认。',
  groups: [{ title: '类型', itemIds: [item.id] }],
  items: [{ itemId: item.id, stale: false, risks: [], suggestion: 'reject', reason: '名称不合适', rename: null }],
  counts: { total: 1, aiReviewed: 1, withRisks: 0, suggestReject: 1, suggestEdit: 0, stale: 0, dropped: 0 },
};
const groupedAssist: ReviewAssist = {
  ...assist,
  groups: [...assist.groups, { title: '其他组', itemIds: [other.id] }],
  items: [...assist.items, { ...assist.items[0]!, itemId: other.id, suggestion: 'accept', reason: null }],
  counts: { ...assist.counts, total: 2, aiReviewed: 2 },
};

function server(role: 'viewer' | 'editor' | 'reviewer' = 'editor', result: ReviewAssist | null = assist,
  entries: ChangeItem[] = [item], extra: Record<string, RouteHandler> = {}, status: 'open' | 'merged' = 'open') {
  return mockApi({
    'GET /api/ontologies': () => [ontologyFixture()],
    'GET /api/change-sets/:id': () => changeSetFixture(entries, { status }),
    'GET /api/change-sets/:id/review-assist': () => result,
    'POST /api/change-sets/:id/review-assist': () => assist,
    'GET /api/ontologies/:id/elements': () => [elementFixture()],
    ...extra,
  }, { user: userWithRole(role) });
}

describe('review assist', () => {
  it('excludes a suggested rejection from high-confidence bulk acceptance', () => {
    expect(highConfidencePending([item], assist)).toEqual([]);
    expect(highConfidencePending([item])).toEqual([item]);
  });

  it('excludes live risks and suggested edits, but ignores stale and failed results', () => {
    const others = [itemFixture({ id: 'risk', seq: 2 }), itemFixture({ id: 'edit', seq: 3 }), itemFixture({ id: 'stale', seq: 4 })];
    const result: ReviewAssist = { ...assist, items: [
      assist.items[0]!,
      { itemId: 'risk', stale: false, risks: [ruleRisk], suggestion: null, reason: null, rename: null },
      { itemId: 'edit', stale: false, risks: [], suggestion: 'edit', reason: null, rename: { labelZh: '新名称' } },
      { itemId: 'stale', stale: true, risks: [ruleRisk], suggestion: 'reject', reason: null, rename: null },
    ] };
    expect(highConfidencePending([item, ...others], result).map((entry) => entry.id)).toEqual(['stale']);
    expect(highConfidencePending([item, ...others], { ...result, status: 'failed' })).toHaveLength(4);
  });

  it('shows request only for an open editor and changes its label when a result exists', async () => {
    let finishRead!: (result: ReviewAssist) => void;
    const reading = new Promise<ReviewAssist>((resolve) => { finishRead = resolve; });
    server('editor', null, [item], { 'GET /api/change-sets/:id/review-assist': () => reading });
    renderApp('/review/cs-converter');
    await screen.findByRole('article');
    expect(screen.getByRole('button', { name: '✦ AI 预审' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('正在加载…')).not.toBeInTheDocument();
    finishRead(assist);
    expect(await screen.findByRole('button', { name: '重新预审' })).toBeEnabled();
  });

  it('hides request for a closed change set', async () => {
    server('editor', assist, [item], {}, 'merged');
    renderApp('/review/cs-converter');
    await screen.findByRole('article');
    expect(screen.queryByRole('button', { name: /预审/ })).not.toBeInTheDocument();
  });

  it('shows the summary, counts, fallback notes, and exclusion count', async () => {
    server('reviewer', { ...assist, status: 'partial', aiUsed: false, truncated: true,
      counts: { ...assist.counts, stale: 1 } });
    renderApp('/review/cs-converter');
    expect(await screen.findByText('请逐项确认。')).toBeInTheDocument();
    expect(screen.getByText('有风险 0 · 建议拒绝 1 · 建议修改 0')).toBeInTheDocument();
    expect(screen.getByText('只做了规则检查')).toBeInTheDocument();
    expect(screen.getByText('AI 只看了前 400 项，其余只做了规则检查')).toBeInTheDocument();
    expect(screen.getByText('部分项没有完成 AI 检查')).toBeInTheDocument();
    expect(screen.getByText('预审之后有 1 项已修改')).toBeInTheDocument();
    expect(screen.getByText('已排除 AI 预审标出风险的 1 项')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新预审' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /接受全部.*建议/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /拒绝全部.*建议/ })).not.toBeInTheDocument();
  });

  it('sends only eligible high-confidence item IDs for bulk acceptance', async () => {
    const user = userEvent.setup();
    const entries = [item, ...['risk', 'edit', 'stale', 'clean'].map((id, index) => itemFixture({ id, seq: index + 2 }))];
    const result: ReviewAssist = { ...assist, items: [
      assist.items[0]!,
      { ...assist.items[0]!, itemId: 'risk', risks: [ruleRisk], suggestion: null, reason: null },
      { ...assist.items[0]!, itemId: 'edit', suggestion: 'edit', rename: { labelZh: '钢包车' } },
      { ...assist.items[0]!, itemId: 'stale', stale: true, risks: [ruleRisk] },
      { ...assist.items[0]!, itemId: 'clean', suggestion: 'accept', reason: null },
    ], counts: { ...assist.counts, total: 5, aiReviewed: 5, withRisks: 1, suggestEdit: 1, stale: 1 } };
    const api = server('reviewer', result, entries, { 'POST /api/change-sets/:id/decisions': () => changeSetFixture(entries) });
    renderApp('/review/cs-converter');
    await screen.findByText('已排除 AI 预审标出风险的 3 项');
    await user.click(screen.getByRole('button', { name: '接受全部高置信度项（2）' }));
    const calls = () => api.calls('POST', '/api/change-sets/cs-converter/decisions');
    await waitFor(() => expect(calls()).toHaveLength(1));
    expect(calls()[0]?.body).toEqual({ itemIds: ['stale', 'clean'], decision: 'accepted' });
  });

  it('retries a failed pre-review by POST', async () => {
    const user = userEvent.setup();
    const api = server('reviewer', { ...assist, status: 'failed' });
    renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '重试' }));
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/review-assist')).toHaveLength(1));
  });

  it('refreshes the latest result immediately after a request', async () => {
    const user = userEvent.setup();
    let latest: ReviewAssist | null = null;
    const api = server('editor', null, [item], {
      'GET /api/change-sets/:id/review-assist': () => latest,
      'POST /api/change-sets/:id/review-assist': () => { latest = assist; return assist; },
    });
    renderApp('/review/cs-converter');
    const request = await screen.findByRole('button', { name: '✦ AI 预审' });
    await waitFor(() => expect(request).toBeEnabled());
    await user.click(request);
    expect(await screen.findByText('请逐项确认。')).toBeInTheDocument();
    expect(api.calls('GET', '/api/change-sets/cs-converter/review-assist')).toHaveLength(2);
  });

  it('shows the permission state when reading returns 403', async () => {
    server('editor', null, [item], { 'GET /api/change-sets/:id/review-assist': () => problemResponse(403, 'auth.forbidden') });
    renderApp('/review/cs-converter');
    expect(await screen.findByText('没有访问权限')).toBeInTheDocument();
  });

  it('shows a retryable error when reading fails', async () => {
    server('editor', null, [item], { 'GET /api/change-sets/:id/review-assist': () => problemResponse(503, 'service.unavailable') });
    renderApp('/review/cs-converter');
    expect(await screen.findByText('无法读取预审结果')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });

  it('shows Retry-After in the rate limit toast', async () => {
    const user = userEvent.setup();
    const response = problemResponse(429, 'review_assist.rate_limited');
    response.headers.set('Retry-After', '37');
    const api = server('editor', null, [item], { 'POST /api/change-sets/:id/review-assist': () => response });
    renderApp('/review/cs-converter');
    const request = await screen.findByRole('button', { name: '✦ AI 预审' });
    await waitFor(() => expect(request).toBeEnabled());
    await user.click(request);
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/review-assist')).toHaveLength(1));
    await waitFor(() => expect(document.body.textContent?.slice(-500)).toContain('请在 37 秒后再试'));
  });

  it('disables a running request, polls after two seconds and counts from creation on reopen', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: Date.parse(assist.createdAt) + 5000 });
    try {
      const api = server('editor', { ...assist, status: 'running' });
      renderApp('/review/cs-converter');
      const button = await screen.findByRole('button', { name: '重新预审' });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('aria-busy', 'true');
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(api.calls('GET', '/api/change-sets/cs-converter/review-assist').length).toBeGreaterThan(1);
      await act(() => vi.advanceTimersByTimeAsync(2000));
      expect(screen.queryByText('仍在处理')).not.toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(1000));
      expect(screen.getByText('仍在处理')).toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });

  it('stops polling after the result is done', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: Date.parse(assist.createdAt) + 12_000 });
    try {
      let reads = 0;
      const api = server('editor', assist, [item], {
        'GET /api/change-sets/:id/review-assist': () => ({ ...assist, status: ++reads === 1 ? 'running' : 'done' }),
      });
      renderApp('/review/cs-converter');
      await screen.findByRole('button', { name: '重新预审' });
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(screen.getByText('仍在处理')).toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      await waitFor(() => expect(api.calls('GET', '/api/change-sets/cs-converter/review-assist')).toHaveLength(2));
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(api.calls('GET', '/api/change-sets/cs-converter/review-assist')).toHaveLength(2);
      expect(screen.queryByText('仍在处理')).not.toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });

  it('filters risk, rejection, editing, and groups together', async () => {
    const user = userEvent.setup();
    const entries = [item, other,
      itemFixture({ id: 'third', seq: 3, tempRef: 'new:Third', proposed: { localName: 'Third', labelZh: '第三' } }),
      itemFixture({ id: 'stale', seq: 4, tempRef: 'new:Stale', proposed: { localName: 'Stale', labelZh: '旧项' } })];
    const risk = { code: 'weak_evidence' as const, source: 'rule' as const, detail: 'no_evidence' as const,
      reason: null, relatedItemIds: [], relatedElementIds: [], memoryEntryId: null };
    const result: ReviewAssist = { ...assist, groups: [{ title: '第一组', itemIds: [item.id, 'other'] }, { title: '第二组', itemIds: ['third'] }],
      items: [
        { ...assist.items[0]!, risks: [risk] },
        { itemId: 'other', stale: false, risks: [], suggestion: 'edit', reason: '改名称', rename: { labelZh: '修改后' } },
        { itemId: 'third', stale: false, risks: [risk], suggestion: 'reject', reason: '不需要', rename: null },
        { itemId: 'stale', stale: true, risks: [risk], suggestion: 'reject', reason: null, rename: null },
      ] };
    server('reviewer', result, entries);
    renderApp('/review/cs-converter');
    const filters = await screen.findByRole('group', { name: '预审筛选' });
    expect(screen.getByRole('article', { name: /旧项/ })).toBeInTheDocument();
    await user.click(within(filters).getByRole('button', { name: '有风险' }));
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(screen.queryByRole('article', { name: /旧项/ })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: '预审分组' }), '1');
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByRole('article', { name: /第三/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '建议拒绝' }));
    expect(screen.getAllByRole('article')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: '建议修改' }));
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    await user.selectOptions(screen.getByRole('combobox', { name: '预审分组' }), '0');
    expect(screen.getByRole('article', { name: /其他/ })).toBeInTheDocument();
  });

  it('resets the filter and group when polling returns a new pre-review', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      let latest = groupedAssist;
      server('reviewer', groupedAssist, [item, other], {
        'GET /api/change-sets/:id/review-assist': () => latest,
        'POST /api/change-sets/:id/review-assist': () => {
          latest = { ...groupedAssist, id: 'assist-2', status: 'queued', createdAt: new Date().toISOString(),
            finishedAt: null, summary: null, groups: [], items: [] };
          return jsonResponse(latest, 202);
        },
      });
      renderApp('/review/cs-converter');
      const group = await screen.findByRole('combobox', { name: '预审分组' });
      await user.selectOptions(group, '0');
      const rejectFilter = screen.getByRole('button', { name: '建议拒绝' });
      await user.click(rejectFilter);
      expect(rejectFilter).toHaveAttribute('aria-pressed', 'true');
      expect(group).toHaveDisplayValue('类型（1 项）');
      expect(screen.getAllByRole('article')).toHaveLength(1);
      expect(screen.getByRole('article', { name: /钢包/ })).toBeInTheDocument();

      const rerun = screen.getByRole('button', { name: '重新预审' });
      await user.click(rerun);
      await waitFor(() => expect(screen.queryByRole('combobox', { name: '预审分组' })).not.toBeInTheDocument());
      expect(rerun).toBeDisabled();
      latest = { ...latest, status: 'done', finishedAt: new Date().toISOString(), summary: '新的预审结果',
        groups: [{ title: '新分组', itemIds: [other.id] }], items: groupedAssist.items };
      await act(() => vi.advanceTimersByTimeAsync(2000));
      await screen.findByText('新的预审结果');
      expect(screen.queryAllByRole('article')).toHaveLength(2);
      expect(screen.getByRole('combobox', { name: '预审分组' })).toHaveDisplayValue('全部分组');
      expect(screen.getByRole('button', { name: '建议拒绝' })).toHaveAttribute('aria-pressed', 'false');
    } finally { vi.useRealTimers(); }
  });

  it('falls back to all groups when the selected index disappears within the same result', async () => {
    const user = userEvent.setup();
    let latest = groupedAssist;
    server('reviewer', latest, [item, other], { 'GET /api/change-sets/:id/review-assist': () => latest });
    const { queryClient } = renderApp('/review/cs-converter');
    const group = await screen.findByRole('combobox', { name: '预审分组' });
    await user.selectOptions(group, '1');
    expect(group).toHaveDisplayValue('其他组（1 项）');
    expect(screen.getAllByRole('article')).toHaveLength(1);

    latest = { ...groupedAssist, groups: assist.groups };
    await act(() => queryClient.refetchQueries({ queryKey: changeSetKeys.assist(assist.changeSetId) }));
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2));
    expect(group).toHaveDisplayValue('全部分组');

    latest = groupedAssist;
    await act(() => queryClient.refetchQueries({ queryKey: changeSetKeys.assist(assist.changeSetId) }));
    await within(group).findByRole('option', { name: '其他组（1 项）' });
    expect(group).toHaveDisplayValue('全部分组');
    expect(screen.getAllByRole('article')).toHaveLength(2);
  });

  it('distinguishes rule and AI risks, explains details, and dims stale advice', async () => {
    const user = userEvent.setup();
    const ai = { ...ruleRisk, source: 'ai' as const, detail: null, reason: '名称与资料不符' };
    const unknown = { ...ruleRisk, detail: 'future_detail' as AssistRisk['detail'] };
    server('reviewer', { ...assist, items: [{ ...assist.items[0]!, stale: true, risks: [ruleRisk, ai, unknown] }] });
    renderApp('/review/cs-converter');
    const card = await screen.findByRole('article');
    await within(card).findByText(/建议拒绝/);
    expect(within(card).getByText(/建议拒绝/)).toHaveClass('text-muted-foreground');
    expect(within(card).getByText('预审之后已修改')).toBeInTheDocument();
    const ruleBadge = within(card).getByRole('button', { name: '命名不一致：局部名格式需要核对' });
    const aiBadge = within(card).getByRole('button', { name: 'AI 判断：命名不一致。名称与资料不符' });
    expect(ruleBadge).toHaveTextContent(/^命名不一致$/);
    expect(aiBadge).toHaveTextContent(/^✦ 命名不一致$/);
    expect(within(card).getByRole('button', { name: '命名不一致：请核对这一项' })).toBeInTheDocument();
    await user.hover(ruleBadge);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('局部名格式需要核对');
  });

  it.each([
    ['zh-CN', '✦ AI 拿不准', '✦ 建议拒绝'],
    ['en', '✦ AI is unsure', '✦ Suggest rejecting'],
  ])('shows suggestions without a trailing colon when there is no reason (%s)', async (locale, unsure, reject) => {
    await i18n.changeLanguage(locale);
    server('reviewer', { ...groupedAssist, items: [
      { ...assist.items[0]!, suggestion: 'unsure', reason: null },
      { ...assist.items[0]!, itemId: other.id, reason: null },
    ] }, [item, other]);
    renderApp('/review/cs-converter');
    expect(await screen.findByText(unsure)).toBeInTheDocument();
    expect(screen.getByText(reject)).toBeInTheDocument();
  });

  it('hides the request button from viewers', async () => {
    server('viewer');
    renderApp('/review/cs-converter');
    await screen.findByRole('article');
    expect(screen.queryByRole('button', { name: /预审/ })).not.toBeInTheDocument();
  });

  it('refreshes stale advice after saving an item edit', async () => {
    const user = userEvent.setup();
    let savedItem = item;
    const api = server('reviewer', assist, [item], {
      'GET /api/change-sets/:id': () => changeSetFixture([savedItem]),
      'PATCH /api/change-sets/:id/items/:itemId': ({ body }) => {
        savedItem = { ...item, edited: (body as ItemPatch).edited ?? null };
        return savedItem;
      },
      'GET /api/change-sets/:id/review-assist': () => savedItem.edited ? {
        ...assist, items: [{ ...assist.items[0]!, stale: true }], counts: { ...assist.counts, stale: 1, suggestReject: 0 },
      } : assist,
    });
    renderApp('/review/cs-converter');
    await screen.findByText('✦ 建议拒绝：名称不合适');
    expect(screen.queryByText('预审之后已修改')).not.toBeInTheDocument();
    const reads = () => api.calls('GET', '/api/change-sets/cs-converter/review-assist').length;
    const beforeEdit = reads();

    await user.click(screen.getByRole('button', { name: '修改“钢包”' }));
    const dialog = await screen.findByRole('dialog');
    const label = within(dialog).getByRole('textbox', { name: '中文名称' });
    await user.clear(label);
    await user.type(label, '钢包车');
    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(1));
    await waitFor(() => expect(reads()).toBeGreaterThan(beforeEdit));
    const card = await screen.findByRole('article', { name: /钢包车/ });
    expect(await within(card).findByText('预审之后已修改')).toBeInTheDocument();
  });

  it('opens the suggested rename without saving, and saves only on confirmation', async () => {
    const user = userEvent.setup();
    const suggestion: ReviewAssist = { ...assist, items: [{ ...assist.items[0]!, suggestion: 'edit', rename: { labelZh: '新钢包' } }] };
    const api = server('reviewer', suggestion);
    renderApp('/review/cs-converter');
    const card = await screen.findByRole('article');
    await user.click(await within(card).findByRole('button', { name: '按建议修改' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByDisplayValue('新钢包')).toBeInTheDocument();
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(0);
    await user.click(within(dialog).getByRole('button', { name: '关闭' }));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(0);
    await user.click(within(card).getByRole('button', { name: '按建议修改' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /保存/ }));
    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(1));
  });
});
