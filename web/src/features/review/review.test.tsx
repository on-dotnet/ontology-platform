import { act, cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { changeSetFixture, documentFixture, elementFixture, elementRefFixture, impactFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import type { UserInfo } from '@/features/auth/api';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import { changeSetKeys, countDecisions, type ChangeItem, type ChangeSetDetail, type ItemPatch, type ItemResolution } from './api';

const CHUNK_TEXT = '第一章 总则\n钢包是盛装和运送钢水的容器，使用前应烘烤至规定温度。\n板坯由连铸机生产。';
const QUOTE = '钢包是盛装和运送钢水的容器';

function items(): ChangeItem[] {
  return [
    itemFixture({
      evidence: [
        {
          id: 'ev-ladle',
          kind: 'document',
          source: null,
          documentId: 'doc-converter',
          chunkId: 'chunk-1',
          quote: QUOTE,
          charStart: CHUNK_TEXT.indexOf(QUOTE),
          charEnd: CHUNK_TEXT.indexOf(QUOTE) + QUOTE.length,
        },
      ],
    }),
    itemFixture({
      id: 'item-slab',
      seq: 2,
      tempRef: 'new:Slab',
      proposed: { localName: 'Slab', labelZh: '板坯', labelEn: 'Slab', synonyms: [{ lang: 'zh', text: '连铸坯' }] },
      confidence: 0.85,
      flags: ['evidence_not_found'],
      evidence: [{ id: 'ev-slab', kind: 'document', source: null, documentId: 'doc-converter', chunkId: 'chunk-1', quote: '板坯是连铸的产品', charStart: null, charEnd: null }],
    }),
    itemFixture({
      id: 'item-holds',
      seq: 3,
      kind: 'relation_type',
      tempRef: 'new:holds',
      proposed: { localName: 'holds', labelZh: '盛装', domainRef: 'new:Ladle', rangeRef: 'el-molten-steel', required: false, multiple: true },
      confidence: 0.62,
    }),
    itemFixture({
      id: 'item-thickness',
      seq: 4,
      kind: 'property',
      tempRef: 'new:thickness',
      proposed: { localName: 'thickness', labelZh: '厚度', domainRef: 'new:Slab', datatype: 'decimal', unit: 'mm', required: true },
      confidence: 0.9,
    }),
  ];
}

/** A change set server that applies PATCH and bulk decisions to its state. */
interface ServerOptions {
  initial?: ChangeSetDetail;
  extra?: Record<string, RouteHandler>;
  user?: UserInfo;
}

function reviewServer({ initial = changeSetFixture(items()), extra = {}, user }: ServerOptions = {}) {
  let state = initial;
  const update = (next: ChangeItem[]) => {
    state = { ...state, items: next, counts: countDecisions(next) };
  };
  const api = mockApi({
    'GET /api/ontologies': () => [ontologyFixture({ openChangeSetCount: 1 })],
    'GET /api/change-sets': () => [state],
    'GET /api/change-sets/:id': () => state,
    'GET /api/change-sets/:id/review-assist': () => null,
    'GET /api/ontologies/:id/elements': () => [elementFixture()],
    'GET /api/documents/:id': () => documentFixture(),
    'GET /api/documents/:id/chunks/:chunkId': ({ params }) => ({
      id: params.chunkId,
      documentId: params.id,
      seq: 0,
      text: CHUNK_TEXT,
      page: 3,
      heading: '第一章 总则',
      charCount: CHUNK_TEXT.length,
    }),
    'PATCH /api/change-sets/:id/items/:itemId': ({ params, body }) => {
      const patch = body as ItemPatch;
      const next = state.items.map((item) =>
        item.id === params.itemId
          ? { ...item, ...(patch.decision ? { decision: patch.decision } : {}), ...(patch.rejectReason ? { rejectReason: patch.rejectReason } : {}), ...(patch.edited !== undefined ? { edited: patch.edited } : {}) }
          : item,
      );
      update(next);
      return next.find((item) => item.id === params.itemId);
    },
    'POST /api/change-sets/:id/decisions': ({ body }) => {
      const { itemIds, decision } = body as { itemIds: string[]; decision: ChangeItem['decision'] };
      update(state.items.map((item) => (itemIds.includes(item.id) ? { ...item, decision } : item)));
      return state;
    },
    ...extra,
  }, user ? { user } : {});
  return api;
}

function card(name: RegExp) {
  return screen.getByRole('article', { name });
}

describe('change set list', () => {
  it('lists change sets with their source document and decision counts', async () => {
    reviewServer();
    renderApp('/review');

    const table = await screen.findByRole('table', { name: '变更集列表' });
    const row = within(table).getByRole('link', { name: '识别：转炉炼钢工艺规程.docx' }).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('待审核')).toBeInTheDocument();
    expect(await within(row as HTMLElement).findByText('转炉炼钢工艺规程.docx')).toBeInTheDocument();
    expect(within(row as HTMLElement).getAllByRole('cell').map((cell) => cell.textContent)).toContain('4');
  });
});

describe('change set review', () => {
  it.each([
    ['out_of_scope', '超出范围'], ['incorrect', '不正确'], ['duplicate', '重复'], ['keep_open', '暂不决定'],
  ] as const)('sends the %s rejection reason and shows it on the item', async (reason, label) => {
    const user = userEvent.setup();
    const api = reviewServer();
    renderApp('/review/cs-converter');
    const ladle = await screen.findByRole('article', { name: /钢包/ });
    await user.click(within(ladle).getByRole('button', { name: '带理由拒绝钢包' }));
    await user.click(await screen.findByRole('menuitem', { name: label }));
    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')[0]?.body)
      .toEqual({ decision: 'rejected', rejectReason: reason }));
    expect(within(ladle).getByText(label)).toBeInTheDocument();
  });

  it('bulk rejects pending items with a reason', async () => {
    const user = userEvent.setup();
    const api = reviewServer({ initial: changeSetFixture(items().map((item) => item.id === 'item-slab' ? { ...item, decision: 'accepted' } : item)) });
    renderApp('/review/cs-converter');
    await screen.findByRole('article', { name: /钢包/ });
    const bulk = screen.getByRole('button', { name: '带理由拒绝' });
    await user.click(bulk);
    await user.click(await screen.findByRole('menuitem', { name: '超出范围' }));
    const dialog = await screen.findByRole('dialog', { name: '拒绝全部待定项' });
    expect(within(dialog).getByText(/3 项待定/)).toBeInTheDocument();
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(0);
    await user.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: '带理由拒绝' }));
    await user.click(await screen.findByRole('menuitem', { name: '超出范围' }));
    await user.click(within(await screen.findByRole('dialog', { name: '拒绝全部待定项' })).getByRole('button', { name: '拒绝这 3 项' }));
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body)
      .toEqual({ itemIds: ['item-ladle', 'item-holds', 'item-thickness'], decision: 'rejected', rejectReason: 'out_of_scope' });
    expect(await screen.findByText('已拒绝 3 项待定')).toBeInTheDocument();
  });
  it('bulk rejects from the main button without a reason', async () => {
    const api = reviewServer({ initial: changeSetFixture(items().map((item) => item.id === 'item-slab' ? { ...item, decision: 'accepted' } : item)) });
    const user = userEvent.setup();
    renderApp('/review/cs-converter');
    await screen.findByRole('article', { name: /钢包/ });
    await user.click(screen.getByRole('button', { name: '拒绝全部 3 项待定' }));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(0);
    const dialog = await screen.findByRole('dialog', { name: '拒绝全部待定项' });
    await user.click(within(dialog).getByRole('button', { name: '拒绝这 3 项' }));
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body)
      .toEqual({ itemIds: ['item-ladle', 'item-holds', 'item-thickness'], decision: 'rejected' });
    expect(await screen.findByText('已拒绝 3 项待定')).toBeInTheDocument();
  });

  it('disables bulk acceptance while bulk rejection is pending', async () => {
    const api = reviewServer({ extra: { 'POST /api/change-sets/:id/decisions': () => new Promise(() => {}) } });
    const user = userEvent.setup();
    renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '拒绝全部 4 项待定' }));
    await user.click(within(await screen.findByRole('dialog', { name: '拒绝全部待定项' })).getByRole('button', { name: '拒绝这 4 项' }));
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(screen.getByText('接受全部高置信度项（2）').closest('button')).toBeDisabled();
  });

  it('disables bulk rejection while bulk acceptance is pending', async () => {
    const api = reviewServer({ extra: { 'POST /api/change-sets/:id/decisions': () => new Promise(() => {}) } });
    const user = userEvent.setup();
    renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '接受全部高置信度项（2）' }));
    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(screen.getByRole('button', { name: '拒绝全部 4 项待定' })).toBeDisabled();
  });

  it('clears the bulk rejection dialog when no pending items remain', async () => {
    reviewServer();
    const user = userEvent.setup();
    const { queryClient } = renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '拒绝全部 4 项待定' }));
    expect(screen.getByRole('dialog', { name: '拒绝全部待定项' })).toBeInTheDocument();
    const key = changeSetKeys.detail('cs-converter');
    await act(() => queryClient.setQueryData(key, changeSetFixture(items().map((item) => ({ ...item, decision: 'accepted' })))));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '拒绝全部待定项' })).not.toBeInTheDocument());
    await act(() => new Promise<void>((resolve) => window.setTimeout(resolve, 10)));
    await act(() => queryClient.setQueryData(key, changeSetFixture(items())));
    expect(await screen.findByRole('button', { name: '拒绝全部 4 项待定' })).toBeEnabled();
    expect(screen.queryByRole('dialog', { name: '拒绝全部待定项' })).not.toBeInTheDocument();
  });

  it('shows suppressed suggestions and their memory links', async () => {
    reviewServer({ initial: changeSetFixture(items(), { suppressed: [
      { kind: 'entity_type', labelZh: '炉渣颜色', labelEn: null, cause: 'memory', memoryEntryId: 'mem-1', dependsOn: null },
      { kind: 'property', labelZh: '炉渣属性', labelEn: null, cause: 'depends_on_suppressed', memoryEntryId: 'mem-2', dependsOn: '炉渣' },
    ], suppressedTotal: 4 }) });
    const user = userEvent.setup();
    renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '展开' }));
    expect(screen.getByText('按审核记忆，有 4 项没有再提出')).toBeInTheDocument();
    expect(screen.getByText(/依赖被挡的类型 炉渣/)).toBeInTheDocument();
    expect(screen.getByText('另有 2 项未列出')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '炉渣颜色' })).toHaveAttribute('href', '/review/memory?ontology=onto-steel&q=%E7%82%89%E6%B8%A3%E9%A2%9C%E8%89%B2&entry=mem-1');
    expect(screen.getByRole('link', { name: '炉渣属性' })).toHaveAttribute('href', '/review/memory?ontology=onto-steel&q=%E7%82%89%E6%B8%A3&entry=mem-2');
  });
  it('does not show a suppressed notice for an empty list', async () => {
    reviewServer();
    renderApp('/review/cs-converter');
    await screen.findByRole('article', { name: /钢包/ });
    expect(screen.queryByText(/按审核记忆/)).not.toBeInTheDocument();
  });
  it('omits the search term when a suppressed dependency has no name', async () => {
    reviewServer({ initial: changeSetFixture(items(), { suppressed: [
      { kind: 'property', labelZh: '炉渣属性', labelEn: null, cause: 'depends_on_suppressed', memoryEntryId: 'mem-2', dependsOn: null },
    ], suppressedTotal: 1 }) });
    const user = userEvent.setup();
    renderApp('/review/cs-converter');
    await user.click(await screen.findByRole('button', { name: '展开' }));
    expect(screen.getByRole('link', { name: '炉渣属性' })).toHaveAttribute('href', '/review/memory?ontology=onto-steel&entry=mem-2');
  });
  it('labels QA gap proposals in the list and reviews their items as AI suggestions', async () => {
    const user = userEvent.setup();
    const changeSet = changeSetFixture([itemFixture({ rationale: '问题中缺少钢包类型。' })], {
      title: '问答缺口：钢包有多少个？', source: 'ai_qa', documentId: null,
    });
    reviewServer({ initial: changeSet, user: userWithRole('reviewer') });
    renderApp('/review');

    const row = within(await screen.findByRole('row', { name: /问答缺口：钢包有多少个/ }));
    expect(row.getByText('问答缺口')).toBeVisible();
    await user.click(row.getByRole('link', { name: changeSet.title }));
    const item = within(await screen.findByRole('article', { name: /钢包/ }));
    expect(screen.getByText('问答缺口')).toBeVisible();
    expect(item.getByText('AI 建议')).toBeVisible();
    expect(item.getByText('置信度高')).toBeVisible();
    expect(item.getByText('理由：问题中缺少钢包类型。')).toBeVisible();
    expect(item.getByRole('button', { name: '接受' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^接受全部（/ })).not.toBeInTheDocument();
  });

  it('accepts and rejects single items and keeps the AI label, confidence and flags visible', async () => {
    const user = userEvent.setup();
    const api = reviewServer();
    renderApp('/review/cs-converter');

    const ladle = await screen.findByRole('article', { name: /钢包/ });
    expect(within(ladle).getByText('AI 建议')).toBeInTheDocument();
    expect(within(ladle).getByText('置信度高')).toBeInTheDocument();
    expect(within(ladle).getByText('（92%）')).toBeInTheDocument();
    expect(within(card(/板坯/)).getByRole('button', { name: '未找到证据原文' })).toBeInTheDocument();
    expect(within(card(/盛装/)).getByText('置信度中')).toBeInTheDocument();
    expect(within(card(/盛装/)).getByText('钢包')).toBeInTheDocument();
    expect(within(card(/盛装/)).getByText('钢水')).toBeInTheDocument();

    await user.click(within(ladle).getByRole('button', { name: '接受' }));
    await waitFor(() => expect(within(card(/钢包/)).getByRole('button', { name: '接受' })).toHaveAttribute('aria-pressed', 'true'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')[0]?.body).toEqual({ decision: 'accepted' });

    await user.click(within(card(/板坯/)).getByRole('button', { name: '拒绝' }));
    await waitFor(() => expect(within(card(/板坯/)).getByRole('button', { name: '拒绝' })).toHaveAttribute('aria-pressed', 'true'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-slab')[0]?.body).toEqual({ decision: 'rejected' });

    // Pressing the active decision again undoes it.
    await user.click(within(card(/钢包/)).getByRole('button', { name: '接受' }));
    await waitFor(() => expect(within(card(/钢包/)).getByRole('button', { name: '接受' })).toHaveAttribute('aria-pressed', 'false'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')[1]?.body).toEqual({ decision: 'pending' });
  });

  it('accepts all high-confidence items without flags in one request', async () => {
    const user = userEvent.setup();
    const api = reviewServer();
    renderApp('/review/cs-converter');

    await user.click(await screen.findByRole('button', { name: '接受全部高置信度项（2）' }));

    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body).toEqual({
      itemIds: ['item-ladle', 'item-thickness'],
      decision: 'accepted',
    });
    await waitFor(() => expect(within(card(/厚度/)).getByRole('button', { name: '接受' })).toHaveAttribute('aria-pressed', 'true'));
    expect(within(card(/板坯/)).getByRole('button', { name: '接受' })).toHaveAttribute('aria-pressed', 'false');
    // No more pending high-confidence items: the shortcut disappears.
    expect(screen.queryByRole('button', { name: /接受全部高置信度项/ })).not.toBeInTheDocument();
    // AI proposals are never accepted wholesale.
    expect(screen.queryByRole('button', { name: /^接受全部（/ })).not.toBeInTheDocument();
  });

  it('enables merging only after every item is decided and lists skipped items with reasons', async () => {
    const user = userEvent.setup();
    const api = reviewServer({
      extra: {
        'POST /api/change-sets/:id/merge': () => ({ applied: 2, skipped: [{ itemId: 'item-holds', code: 'changeset.dependency_skipped' }] }),
      },
    });
    renderApp('/review/cs-converter');

    const merge = await screen.findByRole('button', { name: '合并到本体' });
    expect(merge).toBeDisabled();
    expect(screen.getByText('还有 4 项未决定')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '接受全部高置信度项（2）' }));
    await waitFor(() => expect(screen.getByText('还有 2 项未决定')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '合并到本体' })).toBeDisabled();

    await user.click(within(card(/板坯/)).getByRole('button', { name: '拒绝' }));
    await waitFor(() => expect(screen.getByText('还有 1 项未决定')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '合并到本体' })).toBeDisabled();

    await user.click(within(card(/盛装/)).getByRole('button', { name: '接受' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '合并到本体' })).toBeEnabled());
    expect(screen.queryByText(/项未决定/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '合并到本体' }));

    const notice = await screen.findByText('已合并，1 项被跳过');
    const banner = notice.closest('[role="status"]');
    expect(banner).toHaveTextContent('已应用 2 项，以下 1 项没有应用：');
    expect(banner).toHaveTextContent('盛装：它引用的项被拒绝或被跳过');
    expect(api.calls('POST', '/api/change-sets/cs-converter/merge')).toHaveLength(1);
  });

  it('explains a refused merge with the mapped error code', async () => {
    const user = userEvent.setup();
    const decided = changeSetFixture(items().map((item) => ({ ...item, decision: 'accepted' as const })));
    reviewServer({
      initial: decided,
      extra: { 'POST /api/change-sets/:id/merge': () => problemResponse(409, 'changeset.closed') },
    });
    renderApp('/review/cs-converter');

    await user.click(await screen.findByRole('button', { name: '合并到本体' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('没有合并到本体');
    expect(alert).toHaveTextContent('这个变更集已合并或已拒绝，不能再修改。');
    expect(alert).not.toHaveTextContent('Backend detail');
  });

  it('shows the evidence beside the list on wide screens and under the chosen item on narrow ones', async () => {
    const user = userEvent.setup();
    reviewServer();
    renderApp('/review/cs-converter');

    // Wide (jsdom defaults to 1024px): the first item's evidence sits after the whole list.
    await screen.findByRole('article', { name: /钢包/ });
    const aside = screen.getByRole('region', { name: '证据' });
    expect(card(/厚度/).compareDocumentPosition(aside) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(card(/钢包/)).getByRole('button', { name: '查看证据（1）' })).toHaveAttribute('aria-pressed', 'true');
    cleanup();

    vi.stubGlobal('innerWidth', 800);
    const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView');
    renderApp('/review/cs-converter');
    await screen.findByRole('article', { name: /板坯/ });
    expect(screen.queryByRole('region', { name: '证据' })).toBeNull();

    // Narrow: the button discloses the panel under the card and scrolls it into view.
    const toggle = within(card(/板坯/)).getByRole('button', { name: '查看证据（1）' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).not.toHaveAttribute('aria-pressed');
    await user.click(toggle);
    const inline = screen.getByRole('region', { name: '证据' });
    expect(card(/板坯/).nextElementSibling).toBe(inline);
    expect(within(inline).getByText('板坯')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAttribute('aria-controls', inline.id);
    expect(scrolled.mock.contexts).toContain(inline);

    await user.click(toggle);
    expect(screen.queryByRole('region', { name: '证据' })).toBeNull();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    scrolled.mockRestore();
  });

  it('validates edits on blur and on save, then sends the edited fields', async () => {
    const user = userEvent.setup();
    const api = reviewServer();
    renderApp('/review/cs-converter');

    await user.click(within(await screen.findByRole('article', { name: /钢包/ })).getByRole('button', { name: '修改“钢包”' }));
    const dialog = await screen.findByRole('dialog', { name: '修改“钢包”' });

    const label = within(dialog).getByRole('textbox', { name: '中文名称' });
    await user.clear(label);
    await user.tab();
    expect(within(dialog).getByText('请输入中文名称')).toBeInTheDocument();

    const localName = within(dialog).getByRole('textbox', { name: '局部名' });
    await user.clear(localName);
    await user.type(localName, 'ladle car');
    await user.tab();
    expect(within(dialog).getByText('局部名需以大写字母开头，只含字母和数字，例如 SteelSlab')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));
    expect(within(dialog).getByText('有 2 处需要修改，请按提示修正后再保存。')).toBeInTheDocument();
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(0);

    await user.type(label, '钢包车');
    await user.clear(localName);
    await user.type(localName, 'LadleCar');
    await user.type(within(dialog).getByRole('textbox', { name: '中文同义词' }), '盛钢桶、钢水包');
    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(1));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')[0]?.body).toEqual({
      edited: {
        localName: 'LadleCar',
        labelZh: '钢包车',
        labelEn: 'Ladle',
        definitionZh: '盛装和运送钢水的容器。',
        definitionEn: null,
        synonyms: [
          { lang: 'zh', text: '盛钢桶' },
          { lang: 'zh', text: '钢水包' },
        ],
        parentRef: null,
      },
    });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '修改“钢包”' })).not.toBeInTheDocument());
    expect(within(card(/钢包车/)).getByText('已修改')).toBeInTheDocument();
  });

  it('edits an update starting from the current values and sends only what differs from the proposal', async () => {
    const user = userEvent.setup();
    const update = itemFixture({
      id: 'item-molten',
      seq: 5,
      op: 'update',
      tempRef: null,
      targetElementId: 'el-molten-steel',
      proposed: { definitionEn: 'Liquid steel from the converter.' },
      // An earlier edit by the reviewer: it must survive the next one.
      edited: { definitionZh: '转炉冶炼得到的钢水。' },
      before: {
        localName: 'MoltenSteel',
        labelZh: '钢水',
        labelEn: 'Molten steel',
        definitionZh: '转炉冶炼得到的液态钢。',
        definitionEn: null,
        synonyms: [{ lang: 'zh', text: '液态钢' }],
        parentRef: null,
      },
    });
    const api = reviewServer({ initial: changeSetFixture([...items(), update]) });
    renderApp('/review/cs-converter');

    await user.click(within(await screen.findByRole('article', { name: /钢水/ })).getByRole('button', { name: '修改“钢水”' }));
    const dialog = await screen.findByRole('dialog', { name: '修改“钢水”' });
    expect(within(dialog).getByRole('textbox', { name: '中文名称' })).toHaveValue('钢水');
    expect(within(dialog).getByRole('textbox', { name: '中文定义' })).toHaveValue('转炉冶炼得到的钢水。');
    expect(within(dialog).getByRole('textbox', { name: '英文定义' })).toHaveValue('Liquid steel from the converter.');
    expect(within(dialog).getByRole('textbox', { name: '中文同义词' })).toHaveValue('液态钢');

    const english = within(dialog).getByRole('textbox', { name: '英文名称' });
    await user.clear(english);
    await user.type(english, 'Liquid steel');
    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-molten')).toHaveLength(1));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-molten')[0]?.body).toEqual({
      edited: { labelEn: 'Liquid steel', definitionZh: '转炉冶炼得到的钢水。' },
    });
  });

  it('offers existing and new object types as references when editing a relation', async () => {
    const user = userEvent.setup();
    const api = reviewServer();
    renderApp('/review/cs-converter');

    await user.click(within(await screen.findByRole('article', { name: /盛装/ })).getByRole('button', { name: '修改“盛装”' }));
    const dialog = await screen.findByRole('dialog', { name: '修改“盛装”' });
    const range = within(dialog).getByRole('combobox', { name: '值域（终点对象类型）' });
    expect(range).toHaveValue('el-molten-steel');
    expect(within(range).getAllByRole('option').map((option) => option.textContent)).toEqual([
      '请选择对象类型',
      '钢水',
      '钢包（本变更集新建）',
      '板坯（本变更集新建）',
    ]);

    await user.selectOptions(within(dialog).getByRole('combobox', { name: '定义域（起点对象类型）' }), '');
    await user.tab();
    expect(within(dialog).getByText('请选择对象类型', { selector: 'p' })).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-holds')).toHaveLength(0);

    await user.selectOptions(within(dialog).getByRole('combobox', { name: '定义域（起点对象类型）' }), 'new:Slab');
    await user.selectOptions(range, 'new:Ladle');
    await user.click(within(dialog).getByRole('checkbox', { name: '必填' }));
    await user.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-holds')).toHaveLength(1));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-holds')[0]?.body).toMatchObject({
      edited: { domainRef: 'new:Slab', rangeRef: 'new:Ladle', required: true, multiple: true },
    });
  });

  it('highlights the quote in the source chunk and flags quotes without a position', async () => {
    const user = userEvent.setup();
    reviewServer();
    renderApp('/review/cs-converter');

    const source = await screen.findByRole('region', { name: '资料原文' });
    expect(source).toHaveTextContent('使用前应烘烤至规定温度');
    const mark = within(source).getByText(QUOTE);
    expect(mark.tagName).toBe('MARK');
    expect(screen.getByText('第 3 页')).toBeInTheDocument();
    expect(screen.getByText('章节：第一章 总则')).toBeInTheDocument();
    expect(screen.queryByText('未在原文中找到这段引语，请对照原文核实后再决定。')).not.toBeInTheDocument();

    await user.click(within(card(/板坯/)).getByRole('button', { name: '查看证据（1）' }));

    expect(await screen.findByText('未在原文中找到这段引语，请对照原文核实后再决定。')).toBeInTheDocument();
    expect(screen.getByText('板坯是连铸的产品')).toBeInTheDocument();
    const unlocated = await screen.findByRole('region', { name: '资料原文' });
    expect(unlocated.querySelector('mark')).toBeNull();
  });

  it('is read-only for viewers', async () => {
    const api = reviewServer({ user: userWithRole('viewer') });
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /钢包/ });
    expect(screen.queryByRole('button', { name: '接受' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '拒绝' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /修改“/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '合并到本体' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /接受全部高置信度项/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '只读' })).toHaveAccessibleDescription('你可以查看这个变更集；接受、拒绝和修改需要“审核者”角色。');
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle')).toHaveLength(0);
  });
});

const importedElements = [
  elementFixture(),
  elementFixture({ id: 'el-temperature', kind: 'property', localName: 'temperature', labelZh: '温度', labelEn: 'Temperature', domainId: 'el-molten-steel' }),
  elementFixture({ id: 'el-grade', kind: 'property', localName: 'grade', labelZh: '钢种', labelEn: 'Grade', domainId: 'el-molten-steel' }),
  elementFixture({ id: 'el-ladle', localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle' }),
  elementFixture({ id: 'el-slag', localName: 'Slag', labelZh: '炉渣', labelEn: 'Slag', status: 'deprecated' }),
  // Imported earlier: an IRI of its own and no names.
  elementFixture({ id: 'el-heat', localName: 'Heat', iri: 'urn:metals:Heat', explicitIri: true, labelZh: null, labelEn: null, definitionZh: null, origin: 'import' }),
];

const AXIOM = 'steel:Slab owl:unionOf (\n  steel:HotSlab\n  steel:ColdSlab\n) .';

/** An import change set: no confidence, no evidence; constraints, axioms, deletes and restores. */
function importItems(): ChangeItem[] {
  const imported = { confidence: null, rationale: null, evidence: [] };
  return [
    itemFixture({
      ...imported,
      id: 'item-shape',
      seq: 1,
      kind: 'constraint',
      tempRef: 'new:MoltenSteelShape',
      proposed: {
        localName: 'MoltenSteelShape',
        labelZh: '钢水校验',
        domainRef: 'el-molten-steel',
        rules: [
          {
            pathRef: 'el-temperature',
            minCount: 1,
            maxCount: 1,
            datatype: 'decimal',
            minInclusive: { lexical: '1580', datatype: 'decimal' },
            allowedValuesLost: false,
            message: [
              { lang: 'en', text: 'At least 1580 °C' },
              { lang: 'zh', text: '钢水温度不得低于 1580℃' },
            ],
          },
          { pathRef: 'el-grade', allowedValues: [{ lexical: 'Q235' }, { lexical: 'Q345' }], allowedValuesLost: true, pattern: '^Q[0-9]+$' },
        ],
      },
    }),
    itemFixture({ ...imported, id: 'item-axiom', seq: 2, kind: 'axiom', axiomCategory: 'logic', tempRef: null, flags: ['non_standard'], proposed: { turtle: AXIOM } }),
    itemFixture({
      ...imported,
      id: 'item-delete',
      seq: 3,
      op: 'delete',
      tempRef: null,
      targetElementId: 'el-ladle',
      proposed: {},
      before: { localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装和运送钢水的容器。', synonyms: [], parentRef: null },
    }),
    itemFixture({
      ...imported,
      id: 'item-restore',
      seq: 4,
      op: 'restore',
      tempRef: null,
      targetElementId: 'el-slag',
      proposed: {},
      before: { localName: 'Slag', labelZh: '炉渣', labelEn: 'Slag', definitionZh: '浮在钢水表面的熔渣。', synonyms: [], parentRef: null },
    }),
    itemFixture({
      ...imported,
      id: 'item-ladle-car',
      seq: 5,
      tempRef: 'new:LadleCar',
      proposed: { iri: 'urn:metals:LadleCar', localName: 'LadleCar', labelEn: 'Ladle car' },
    }),
    itemFixture({
      ...imported,
      id: 'item-heat',
      seq: 6,
      op: 'update',
      tempRef: null,
      targetElementId: 'el-heat',
      proposed: { definitionEn: 'One melt of the converter.' },
      before: { localName: 'Heat', labelZh: null, labelEn: null, definitionZh: null, definitionEn: null, synonyms: [], parentRef: null },
    }),
  ];
}

function importServer(extra: Record<string, RouteHandler> = {}) {
  return reviewServer({
    initial: changeSetFixture(importItems(), { id: 'cs-import', title: '导入：steel.ttl', source: 'import', documentId: null }),
    extra: { 'GET /api/ontologies/:id/elements': () => importedElements, ...extra },
  });
}

it('compares the current and edited metric definitions with names for temporary references', async () => {
  const metric = itemFixture({
    id: 'item-mean', op: 'update', kind: 'metric', tempRef: null, targetElementId: 'el-mean',
    before: {
      labelZh: '炉次指标', subjectRef: 'el-molten-steel', unit: '℃',
      metric: { aggregate: 'avg', propertyRef: 'el-temperature', decimals: 1, percent: false,
        filters: [{ propertyRef: 'el-temperature', op: 'gt', value: 1500 }] },
    },
    proposed: { unit: '%', metric: { aggregate: 'count', decimals: 0, percent: false } },
    edited: { metric: { aggregate: 'ratio', decimals: 3, percent: true, filters: [],
      numerator: [{ propertyRef: 'new:grade', op: 'in', value: ['Q235B', 'Q345'] }] } },
    rationale: null,
  });
  const grade = itemFixture({ id: 'item-grade', kind: 'property', tempRef: 'new:grade', proposed: { labelZh: '钢种' } });
  reviewServer({
    initial: changeSetFixture([metric, grade], { id: 'cs-metric', source: 'manual', documentId: null }),
    extra: { 'GET /api/ontologies/:id/elements': () => [elementFixture(), elementFixture({ id: 'el-temperature', kind: 'property', labelZh: '温度' })] },
  });
  renderApp('/review/cs-metric');
  const card = within(await screen.findByRole('article', { name: /炉次指标/ }));
  const previous = card.getByRole('region', { name: '变更前的指标' });
  const next = card.getByRole('region', { name: '变更后的指标' });
  expect(previous).toHaveTextContent('平均值');
  expect(previous).toHaveTextContent('温度 大于 1500');
  expect(previous).toHaveTextContent('℃');
  expect(next).toHaveTextContent('占比');
  expect(next).toHaveTextContent('钢水');
  expect(next).toHaveTextContent('钢种 属于');
  expect(next).toHaveTextContent('Q235B');
  expect(next).toHaveTextContent('Q345');
  expect(next).toHaveTextContent('%');
  expect(next).not.toHaveTextContent('计数');
  expect(next).not.toHaveTextContent('1500');
  expect(next).not.toHaveTextContent('new:grade');
});

it('shows two decimal places for an older proposal with omitted defaults and preserves an explicit zero', async () => {
  const metric = itemFixture({ id: 'item-count', op: 'update', kind: 'metric', targetElementId: 'el-count', tempRef: null,
    before: { labelZh: '炉次数量', subjectRef: 'el-molten-steel', metric: { aggregate: 'count', decimals: 0, percent: false } },
  });
  const changeSet = changeSetFixture([metric], { id: 'cs-sparse', source: 'manual', documentId: null });
  reviewServer({ initial: changeSet, extra: {
    // The change-set response omits unset nested fields, including defaults present in OpenAPI.
    'GET /api/change-sets/:id': () => ({ ...changeSet, items: [{ ...metric, proposed: { metric: { aggregate: 'count' } } }] }),
  } });
  renderApp('/review/cs-sparse');
  const item = within(await screen.findByRole('article', { name: /炉次数量/ }));
  const before = within(item.getByRole('region', { name: '变更前的指标' }));
  const after = within(item.getByRole('region', { name: '变更后的指标' }));
  expect(before.getByText('小数位数').nextElementSibling).toHaveTextContent(/^0$/);
  expect(after.getByText('小数位数').nextElementSibling).toHaveTextContent(/^2$/);
});

it.each(['property', 'entity_type'] as const)('shows only active direct metric references in the impact of a %s update', async (kind) => {
  const user = userEvent.setup();
  const heat = elementFixture({ id: 'heat', labelZh: '炉次' });
  const weight = elementFixture({ id: 'weight', kind: 'property', labelZh: '重量', datatype: 'decimal', domainId: heat.id });
  const target = kind === 'property' ? weight : heat;
  const total = elementFixture({ id: 'total', kind: 'metric', labelZh: '总重量', subjectId: heat.id,
    metric: { aggregate: 'sum', propertyId: weight.id, filters: [], numerator: [], decimals: 0, percent: false } });
  const indirect = elementFixture({ ...total, id: 'indirect', labelZh: '间接指标', subjectId: 'other-type',
    metric: { aggregate: 'count', propertyId: null, filters: [], numerator: [], decimals: 0, percent: false } });
  const retired = elementFixture({ ...total, id: 'retired', labelZh: '停用指标', status: 'deprecated' });
  const outside = elementFixture({ ...total, id: 'outside', labelZh: '不在影响清单内' });
  const item = itemFixture({ id: 'item-update', kind, op: 'update', targetElementId: target.id, tempRef: null,
    proposed: { definitionZh: '更新说明' }, before: { labelZh: target.labelZh } });
  reviewServer({
    initial: changeSetFixture([item], { id: 'cs-impact', source: 'manual', documentId: null }),
    extra: {
      'GET /api/ontologies/:id/elements': () => [heat, weight, total, retired, indirect, outside],
      'GET /api/ontologies/:id/elements/:elementId/impact': () => impactFixture(target.id, {
        cascade: [indirect, retired, total].map((metric) => ({ op: 'delete', element: elementRefFixture(metric) })),
      }),
    },
  });
  renderApp('/review/cs-impact');
  const card = within(await screen.findByRole('article', { name: target.labelZh ?? '' }));
  await user.click(card.getByRole('button', { name: '查看影响' }));
  const list = await card.findByRole('list', { name: '被 1 个元素引用' });
  expect(within(list).getAllByRole('listitem').map((entry) => entry.textContent)).toEqual(['指标总重量']);
  expect(card.queryByText('没有其他元素引用它。')).not.toBeInTheDocument();
});

it('shows only the recorded metric proposal after merge, even if the target has changed again', async () => {
  const metric = itemFixture({ kind: 'metric', op: 'update', tempRef: null, targetElementId: 'metric-count', decision: 'accepted',
    appliedElementId: 'metric-count', proposed: { labelZh: '炉次统计', unit: '批',
      metric: { aggregate: 'count', decimals: 0, percent: false } }, edited: { unit: '炉' },
    before: { labelZh: '后续改名', definitionZh: '后续说明', subjectRef: 'el-molten-steel', unit: '吨',
      metric: { aggregate: 'sum', decimals: 3, percent: false } },
  });
  reviewServer({ initial: changeSetFixture([metric], {
    id: 'cs-merged-metric', source: 'manual', documentId: null, status: 'merged', mergedAt: '2026-11-21T08:00:00Z',
  }) });
  renderApp('/review/cs-merged-metric');
  const card = within(await screen.findByRole('article', { name: /炉次统计/ }));
  const proposal = within(card.getByRole('region', { name: '指标提议内容' }));
  expect(proposal.getByText('计数')).toBeInTheDocument();
  expect(proposal.getByText('炉')).toBeInTheDocument();
  expect(proposal.queryByText('主体类型')).not.toBeInTheDocument();
  for (const text of ['变更前的指标', '变更后的指标', '后续说明', '后续改名', '吨', '批', '求和']) {
    expect(card.queryByText(text)).not.toBeInTheDocument();
  }
});

describe('historical metric proposals', () => {
  const count = { aggregate: 'count', decimals: 2, percent: false } as const;

  it.each([
    { source: 'import', status: 'open', proposed: count, edited: null, reason: '指标变更只接受手工编辑。' },
    { source: 'mcp', status: 'merged', proposed: count, edited: null, reason: '指标变更只接受手工编辑。' },
    { source: 'manual', status: 'open', proposed: count, edited: { metric: null }, reason: '此项将指标定义设为空。' },
    { source: 'manual', status: 'merged', proposed: null, edited: { unit: '炉' }, reason: '此项将指标定义设为空。' },
  ] as const)('explains the skipped $source metric in a $status change set', async ({ source, status, proposed, edited, reason }) => {
    const item = itemFixture({
      kind: 'metric', op: 'update', targetElementId: 'el-count', tempRef: null, decision: 'accepted',
      before: { labelZh: '旧名', subjectRef: 'el-molten-steel', metric: count },
      proposed: { labelZh: '炉次计数', metric: proposed }, edited,
    });
    reviewServer({ initial: changeSetFixture([item], { id: 'cs-legacy', source, status, documentId: null,
      mergedAt: status === 'merged' ? '2026-11-21T08:00:00Z' : null }) });
    renderApp('/review/cs-legacy');
    const card = within(await screen.findByRole('article', { name: '炉次计数' }));
    expect(card.getByText(reason)).toBeInTheDocument();
    expect(card.getByText(status === 'merged' ? '合并时已跳过此项' : '合并时会跳过此项')).toBeInTheDocument();
    for (const text of ['聚合方式', '变更前的指标', '变更后的指标', '指标提议内容', '旧名']) {
      expect(card.queryByText(text)).not.toBeInTheDocument();
    }
  });

  it.each([
    { scenario: 'omitted definition', proposed: { unit: '炉' }, edited: null },
    { scenario: 'corrected definition', proposed: { metric: null }, edited: { metric: count } },
  ])('keeps the normal manual comparison for a $scenario', async ({ proposed, edited }) => {
    const item = itemFixture({
      kind: 'metric', op: 'update', targetElementId: 'el-count', tempRef: null,
      before: { labelZh: '炉次计数', subjectRef: 'el-molten-steel', metric: count }, proposed, edited,
    });
    reviewServer({ initial: changeSetFixture([item], { id: 'cs-partial', source: 'manual', documentId: null }) });
    renderApp('/review/cs-partial');
    const card = within(await screen.findByRole('article', { name: '炉次计数' }));
    expect(card.getByRole('region', { name: '变更后的指标' })).toHaveTextContent('计数');
    expect(card.queryByText(/跳过此项/)).not.toBeInTheDocument();
  });
});

describe('import change set review', () => {
  it('describes other statements and expands the original Turtle on demand', async () => {
    const user = userEvent.setup();
    const note = '钢种来自产品目录';
    const turtle = `steel:Grade rdfs:comment "${note}"@zh .`;
    const axiom = {
      ...itemFixture({ kind: 'axiom', tempRef: null, proposed: { turtle } }),
      axiomCategory: 'annotation' as const,
      axiomNote: note,
    };
    reviewServer({
      initial: changeSetFixture([axiom], { id: 'cs-import', source: 'import', documentId: null }),
    });
    renderApp('/review/cs-import');

    expect(await screen.findByRole('heading', { name: /^其他语句/ })).toBeVisible();
    expect(screen.getByRole('button', { name: '关于其他语句' })).toHaveAccessibleDescription('表单表达不了的内容，按 Turtle 原文保留，导出不丢。');
    const item = within(screen.getByRole('article'));
    expect(item.getByText('注解')).toBeVisible();
    expect(item.getByText(note)).toBeVisible();
    const summary = item.getByText('Turtle 片段');
    expect(item.queryByText(turtle)).not.toBeVisible();
    await user.click(summary);
    expect(item.getByText(turtle)).toBeVisible();
  });

  it('shows constraints with their rules, axioms as Turtle, and deletes and restores with the current values', async () => {
    const api = importServer();
    renderApp('/review/cs-import');

    const shape = await screen.findByRole('article', { name: /钢水校验/ });
    expect(screen.getByText('导入', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /^约束/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /^其他语句/ })).toBeInTheDocument();
    // Deleted elements are loaded too, so restores name their target.
    expect(api.requests.some((request) => request.path.endsWith('/elements') && request.query.get('status') === 'all')).toBe(true);

    expect(within(shape).getByText('目标类型：钢水')).toBeInTheDocument();
    const [, temperature, grade] = within(within(shape).getByRole('table', { name: '约束规则' })).getAllByRole('row');
    expect(temperature).toHaveTextContent('温度');
    expect(temperature).toHaveTextContent('恰好 1 个');
    expect(temperature).toHaveTextContent('小数');
    expect(temperature).toHaveTextContent('≥ 1580');
    expect(temperature).toHaveTextContent('钢水温度不得低于 1580℃');
    expect(temperature).not.toHaveTextContent('At least 1580 °C');
    expect(grade).toHaveTextContent('钢种');
    expect(grade).toHaveTextContent('Q235');
    expect(grade).toHaveTextContent('Q345');
    expect(grade).toHaveTextContent('^Q[0-9]+$');
    expect(within(grade as HTMLElement).getByRole('button', { name: 'Protégé 丢掉了枚举取值' })).toBeInTheDocument();

    const axiom = card(/^逻辑公理$/);
    expect(axiom.querySelector('pre')).toHaveTextContent('steel:HotSlab steel:ColdSlab');
    expect(within(axiom).getByRole('button', { name: '非标准写法' })).toHaveAccessibleDescription('在 Protégé 中打开时会改写这条公理。');

    const removed = card(/^钢包(?!车)/);
    expect(within(removed).getByText('删除')).toBeInTheDocument();
    expect(removed).toHaveTextContent('将删除以下内容：');
    expect(removed).toHaveTextContent('盛装和运送钢水的容器。');
    const restored = card(/炉渣/);
    expect(within(restored).getByText('恢复')).toBeInTheDocument();
    expect(restored).toHaveTextContent('将恢复以下内容：');
    expect(restored).toHaveTextContent('浮在钢水表面的熔渣。');

    // Without a Chinese name an item is named by its English name, then by its local name.
    const ladleCar = card(/^Ladle car/);
    const heat = card(/^Heat/);
    expect(within(heat).getByText('修改')).toBeInTheDocument();

    // Not AI: no AI label or confidence. Elements with an IRI of their own are accepted or
    // rejected as they are: the edit form checks the platform's naming rules, not the file's.
    expect(screen.queryByText('AI 建议')).not.toBeInTheDocument();
    expect(screen.queryByText(/置信度/)).not.toBeInTheDocument();
    for (const article of [shape, axiom, removed, restored, ladleCar, heat]) {
      expect(within(article).queryByRole('button', { name: /^修改“/ })).not.toBeInTheDocument();
    }

    // Imports cite no sources: no evidence buttons and no evidence panel, and no card is selected.
    expect(screen.queryByRole('button', { name: /^查看证据/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '证据' })).not.toBeInTheDocument();
    expect(shape).not.toHaveClass('ring-1');
  });

  it('shows what an update replaces: the old rules, the auto shape switch, a deleted one-line axiom', async () => {
    // A confidence on an imported item must not show: only AI items have one that means anything.
    const imported = { confidence: 0.8, rationale: null, evidence: [], tempRef: null };
    const oneLine = 'steel:Slab owl:disjointWith steel:Slag .';
    reviewServer({
      initial: changeSetFixture(
        [
          itemFixture({
            ...imported,
            id: 'item-rules',
            op: 'update',
            kind: 'constraint',
            targetElementId: 'el-shape',
            proposed: { rules: [{ pathRef: 'el-temperature', minCount: 1, allowedValuesLost: false }] },
            before: {
              localName: 'MoltenSteelShape',
              labelZh: '钢水校验',
              domainRef: 'el-molten-steel',
              rules: [{ pathRef: 'el-temperature', minCount: 1, maxCount: 1, allowedValuesLost: false }],
            },
          }),
          itemFixture({
            ...imported,
            id: 'item-auto',
            seq: 2,
            op: 'update',
            targetElementId: 'el-ladle',
            proposed: { autoShape: false },
            before: { localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', synonyms: [], parentRef: null, autoShape: true },
          }),
          itemFixture({ ...imported, id: 'item-gone', seq: 3, op: 'delete', kind: 'axiom', targetElementId: 'el-axiom', proposed: {}, before: { turtle: oneLine } }),
        ],
        { id: 'cs-import', title: '导入：steel.ttl', source: 'import', documentId: null },
      ),
      extra: { 'GET /api/ontologies/:id/elements': () => importedElements },
    });
    renderApp('/review/cs-import');

    const rules = await screen.findByRole('article', { name: /钢水校验/ });
    const [now] = within(rules).getAllByRole('table', { name: '约束规则' });
    expect(now).toHaveTextContent('至少 1 个');
    const old = within(rules).getByRole('region', { name: '修改前的规则' });
    expect(old).toHaveTextContent('恰好 1 个');

    expect(card(/^钢包/)).toHaveTextContent('自动生成校验规则');

    const gone = card(/^其他$/);
    expect(gone).toHaveTextContent('将删除以下内容：');
    expect(gone.querySelector('pre')).toHaveTextContent(oneLine);

    expect(screen.queryByText(/置信度/)).not.toBeInTheDocument();
  });

  it('accepts every pending item at once and explains a delete skipped for dependents', async () => {
    const user = userEvent.setup();
    const api = importServer({
      'POST /api/change-sets/:id/merge': () => ({ applied: 4, skipped: [{ itemId: 'item-delete', code: 'changeset.has_dependents' }] }),
    });
    renderApp('/review/cs-import');

    expect(await screen.findByRole('article', { name: /钢水校验/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /接受全部高置信度项/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '接受全部（6）' }));

    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-import/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-import/decisions')[0]?.body).toEqual({
      itemIds: ['item-shape', 'item-axiom', 'item-delete', 'item-restore', 'item-ladle-car', 'item-heat'],
      decision: 'accepted',
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '合并到本体' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: /^接受全部（/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '合并到本体' }));
    const banner = (await screen.findByText('已合并，1 项被跳过')).closest('[role="status"]');
    expect(banner).toHaveTextContent('钢包：仍有其他元素引用它，没有删除');
  });
});

describe('accepting more items than one request takes', () => {
  const total = 10001;
  const ids = Array.from({ length: total }, (_, index) => `item-${index}`);
  // Ten thousand items take a while to render and decide in jsdom.
  const SLOW = 15_000;

  /** An import change set whose second decisions request fails once; the others are applied. */
  function batchServer() {
    const imported = ids.map((id, index) =>
      itemFixture({ id, seq: index + 1, tempRef: `new:N${index}`, proposed: { localName: `N${index}`, labelZh: `项目${index + 1}` },
        confidence: null, rationale: null, evidence: [] }),
    );
    let state = changeSetFixture(imported, { id: 'cs-import', title: '导入：steel.ttl', source: 'import', documentId: null });
    let requests = 0;
    return reviewServer({
      initial: state,
      extra: {
        'GET /api/change-sets': () => [state],
        'GET /api/change-sets/:id': () => state,
        'POST /api/change-sets/:id/decisions': ({ body }) => {
          requests += 1;
          if (requests === 2) return problemResponse(503, 'service.unavailable');
          const { itemIds, decision } = body as { itemIds: string[]; decision: ChangeItem['decision'] };
          const chosen = new Set(itemIds);
          const next = state.items.map((item) => (chosen.has(item.id) ? { ...item, decision } : item));
          state = { ...state, items: next, counts: countDecisions(next) };
          return state;
        },
      },
    });
  }

  it('sends 5000 items per request in order, stops at a failed batch, keeps the saved ones and retries the rest', async () => {
    const user = userEvent.setup();
    const api = batchServer();
    const sent = () => api.calls('POST', '/api/change-sets/cs-import/decisions').map((call) => (call.body as { itemIds: string[] }).itemIds);
    renderApp('/review/cs-import');

    await user.click(await screen.findByRole('button', { name: `接受全部（${total}）` }, { timeout: SLOW }));

    expect((await screen.findAllByText('已保存 5000/10001 项，其余没有保存，请重试', {}, { timeout: SLOW })).length).toBeGreaterThan(0);
    // The third batch is never sent once the second has failed.
    expect(sent()).toEqual([ids.slice(0, 5000), ids.slice(5000, 10000)]);
    // The first batch stays accepted: the page reloads and offers only the rest.
    const retry = await screen.findByRole('button', { name: '接受全部（5001）' }, { timeout: SLOW });

    await user.click(retry);
    await waitFor(() => expect(sent()).toHaveLength(4), { timeout: SLOW });
    expect(sent().slice(2)).toEqual([ids.slice(5000, 10000), ids.slice(10000)]);
    await waitFor(() => expect(screen.queryByRole('button', { name: /^接受全部（/ })).not.toBeInTheDocument(), { timeout: SLOW });
  }, 60_000);
});

describe('change item pagination', () => {
  const many = Array.from({ length: 120 }, (_, index) =>
    itemFixture({
      id: `item-${index}`,
      seq: index + 1,
      kind: index < 70 ? 'entity_type' : 'property',
      tempRef: `new:N${index}`,
      proposed: { localName: `N${index}`, labelZh: `项目${String(index + 1).padStart(3, '0')}`, ...(index < 70 ? {} : { domainRef: 'el-molten-steel', datatype: 'decimal' }) },
      confidence: 0.9,
      evidence: [{ id: `ev-${index}`, kind: 'document', source: null, documentId: 'doc-converter', chunkId: 'chunk-1', quote: QUOTE, charStart: null, charEnd: null }],
    }),
  );

  it('shows 50 items per page across the kind groups and keeps the page after a decision', async () => {
    const user = userEvent.setup();
    const api = reviewServer({ initial: changeSetFixture(many) });
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /项目001/ });
    expect(screen.getAllByRole('article')).toHaveLength(50);
    expect(screen.queryByRole('article', { name: /项目051/ })).not.toBeInTheDocument();
    const pager = screen.getByRole('navigation', { name: '分页' });
    expect(pager).toHaveTextContent('第 1–50 项，共 120 项');
    expect(screen.queryByRole('heading', { name: /属性/ })).not.toBeInTheDocument();

    await user.click(within(pager).getByRole('button', { name: '下一页' }));
    expect(screen.getAllByRole('article')).toHaveLength(50);
    expect(screen.getByRole('article', { name: /项目051/ })).toBeInTheDocument();
    // The property group begins on this page; each heading counts its whole group.
    expect(screen.getByRole('heading', { name: /属性\s*50/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /对象类型\s*70/ })).toBeInTheDocument();

    await user.click(within(card(/项目051/)).getByRole('button', { name: '接受' }));
    await waitFor(() => expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-50')).toHaveLength(1));
    expect(screen.getByRole('article', { name: /项目051/ })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '分页' })).toHaveTextContent('第 51–100 项，共 120 项');

    await user.click(within(screen.getByRole('navigation', { name: '分页' })).getByRole('button', { name: '下一页' }));
    expect(screen.getAllByRole('article')).toHaveLength(20);
    expect(screen.getByRole('article', { name: /项目120/ })).toBeInTheDocument();
  });

  it('shows the evidence of an item on the current page, not of the first page', async () => {
    const user = userEvent.setup();
    reviewServer({ initial: changeSetFixture(many) });
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /项目001/ });
    expect(within(screen.getByRole('region', { name: '证据' })).getByText('项目001')).toBeInTheDocument();

    await user.click(within(screen.getByRole('navigation', { name: '分页' })).getByRole('button', { name: '下一页' }));
    expect(within(screen.getByRole('region', { name: '证据' })).getByText('项目051')).toBeInTheDocument();
    expect(within(card(/项目051/)).getByRole('button', { name: /查看证据/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows no pager for 50 items or fewer', async () => {
    reviewServer();
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /钢包/ });
    expect(screen.queryByRole('navigation', { name: '分页' })).not.toBeInTheDocument();
  });
});


describe('what a merge does with items proposed against an older baseline', () => {
  const converter: ItemResolution = {
    mode: 'into',
    elementId: 'el-converter',
    elementLabel: '转炉',
    localName: null,
    keptFields: ['definitionZh'],
  };

  function planned(): ChangeItem[] {
    return [
      itemFixture({ resolution: { ...converter, elementLabel: '钢包', elementId: 'el-ladle', keptFields: [] } }),
      itemFixture({
        id: 'item-converter',
        seq: 2,
        tempRef: 'new:Bof',
        proposed: { localName: 'Bof', labelZh: '转炉', definitionZh: '吹氧炼钢的炉子。', synonyms: [] },
        resolution: converter,
      }),
      itemFixture({
        id: 'item-inverter',
        seq: 3,
        tempRef: 'new:Converter',
        proposed: { localName: 'Converter', labelZh: '变流器', synonyms: [] },
        resolution: { mode: 'rename', elementId: null, elementLabel: null, localName: 'Converter2', keptFields: [] },
      }),
      itemFixture({
        id: 'item-tundish',
        seq: 4,
        tempRef: 'new:Tundish',
        proposed: { localName: 'Tundish', labelZh: '中间包', synonyms: [] },
        resolution: { mode: 'create', elementId: null, elementLabel: null, localName: null, keptFields: [] },
      }),
      itemFixture({
        id: 'item-taps',
        seq: 5,
        kind: 'relation_type',
        tempRef: 'new:tapsInto',
        proposed: { localName: 'tapsInto', labelZh: '出钢至', domainRef: 'new:Bof', rangeRef: 'el-ladle' },
        resolution: { ...converter, elementId: 'el-taps', elementLabel: '出钢至', keptFields: [] },
      }),
    ];
  }

  it('says on the card what the merge will do and leaves those items out of the bulk accept', async () => {
    const user = userEvent.setup();
    const api = reviewServer({ initial: changeSetFixture(planned()) });
    renderApp('/review/cs-converter');

    const into = await screen.findByRole('article', { name: /^转炉/ });
    expect(within(into).getByText('合并时将并入已有的“转炉”')).toBeInTheDocument();
    expect(within(into).getByText(/引用这一项的关系和属性改为指向它/)).toBeInTheDocument();
    expect(within(into).getByText('已有元素的中文定义保持不变。')).toBeInTheDocument();
    const renamed = card(/变流器/);
    expect(within(renamed).getByText('局部名 Converter 已被本体里的其他元素使用')).toBeInTheDocument();
    expect(within(renamed).getByText('合并时改用局部名 Converter2。')).toBeInTheDocument();
    // Nothing refers to a relation: its note says only what is added.
    const taps = card(/^出钢至/);
    expect(within(taps).getByText('合并时将并入已有的“出钢至”')).toBeInTheDocument();
    expect(within(taps).queryByText(/改为指向/)).not.toBeInTheDocument();
    // A plain creation says nothing extra.
    expect(within(card(/中间包/)).queryByText(/合并时/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '接受全部高置信度项（1）' }));

    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body).toEqual({
      itemIds: ['item-tundish'],
      decision: 'accepted',
    });
  });

  it('merges with the token of what it shows, and reloads the plan when the ontology moved on', async () => {
    const user = userEvent.setup();
    const shown = changeSetFixture(
      planned().map((item) => ({ ...item, decision: 'accepted' as const })),
      { resolutionToken: 'token-shown' },
    );
    const moved = { ...shown, resolutionToken: 'token-moved' };
    let current = shown;
    const api = reviewServer({
      initial: shown,
      extra: {
        'GET /api/change-sets/:id': () => current,
        'POST /api/change-sets/:id/merge': ({ body }) =>
          (body as { resolutionToken: string }).resolutionToken === current.resolutionToken
            ? { applied: 4, skipped: [] }
            : problemResponse(409, 'changeset.resolution_changed'),
      },
    });
    renderApp('/review/cs-converter');
    await screen.findByRole('article', { name: /变流器/ });
    current = moved;

    await user.click(screen.getByRole('button', { name: '合并到本体' }));

    const notice = await screen.findByText('合并结果已与页面上显示的不同');
    expect(notice.closest('[role="status"]')).toHaveTextContent('确认后再点“合并到本体”');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.calls('POST', '/api/change-sets/cs-converter/merge')[0]?.body).toEqual({ resolutionToken: 'token-shown' });
    await waitFor(() => expect(api.calls('GET', '/api/change-sets/cs-converter').length).toBeGreaterThan(1));

    await user.click(screen.getByRole('button', { name: '合并到本体' }));

    expect(await screen.findByText('已合并到本体')).toBeInTheDocument();
    expect(api.calls('POST', '/api/change-sets/cs-converter/merge')[1]?.body).toEqual({ resolutionToken: 'token-moved' });
  });

  it('says what happened once the change set is merged', async () => {
    const done = planned().map((item) => ({ ...item, decision: 'accepted' as const, appliedElementId: 'el-any' }));
    reviewServer({ initial: changeSetFixture(done, { status: 'merged', mergedAt: '2026-11-25T08:00:00Z' }) });
    renderApp('/review/cs-converter');

    const into = await screen.findByRole('article', { name: /^转炉/ });
    expect(within(into).getByText('已并入已有的“转炉”')).toBeInTheDocument();
    expect(within(into).queryByText(/保持不变/)).not.toBeInTheDocument();
    expect(within(card(/变流器/)).getByText('已改用局部名 Converter2')).toBeInTheDocument();
  });
});

describe('alignment records on the review page', () => {
  const OTHER_SET = '识别：出钢操作规程.docx';
  const create: ItemResolution = { mode: 'create', elementId: null, elementLabel: null, localName: null, keptFields: [] };

  function aligned(): ChangeItem[] {
    // Only the alignment record carries a reason here, as for items extracted after PR 4.
    const items: ChangeItem[] = [
      itemFixture({
        id: 'item-bof',
        tempRef: 'new:Bof',
        proposed: { localName: 'Bof', labelZh: '转炉', synonyms: [] },
        confidence: 0.95,
        resolution: { mode: 'into', elementId: 'el-converter', elementLabel: '转炉', localName: null, keptFields: [] },
        match: {
          kind: 'same',
          elementId: 'el-converter',
          itemId: null,
          changeSetId: null,
          changeSetTitle: null,
          label: '转炉',
          reason: '两者都指吹氧炼钢的炉子。',
          decision: null,
          keptApart: false,
        },
      }),
      itemFixture({
        id: 'item-taphole',
        seq: 2,
        tempRef: 'new:TapHole',
        proposed: { localName: 'TapHole', labelZh: '出钢口', synonyms: [] },
        confidence: 0.9,
        flags: ['possible_duplicate'],
        resolution: create,
        match: {
          kind: 'possible',
          elementId: null,
          itemId: 'item-other-taphole',
          changeSetId: 'cs-other',
          changeSetTitle: OTHER_SET,
          label: '出钢孔',
          reason: '名称相近，所指部位相同。',
          decision: null,
          keptApart: false,
        },
      }),
      itemFixture({
        id: 'item-ladle-car',
        seq: 3,
        tempRef: 'new:SteelLadle',
        proposed: { localName: 'SteelLadle', labelZh: '钢水包', synonyms: [] },
        confidence: 0.9,
        flags: ['possible_duplicate'],
        resolution: create,
        match: {
          kind: 'possible',
          elementId: null,
          itemId: 'item-ladle',
          changeSetId: 'cs-converter',
          changeSetTitle: '识别：转炉炼钢工艺规程.docx',
          label: '钢包',
          reason: null,
          decision: null,
          keptApart: false,
        },
      }),
      itemFixture({ id: 'item-ladle', seq: 4, resolution: create }),
      itemFixture({
        id: 'item-slag',
        seq: 5,
        tempRef: 'new:Slag',
        proposed: { localName: 'Slag', labelZh: '炉渣', synonyms: [] },
        confidence: 0.9,
        flags: ['possible_duplicate'],
        resolution: create,
        match: {
          kind: 'possible',
          elementId: 'el-slag',
          itemId: null,
          changeSetId: null,
          changeSetTitle: null,
          label: '渣',
          reason: '都是冶炼的副产物。',
          decision: null,
          keptApart: true,
        },
      }),
      itemFixture({
        id: 'item-eaf',
        seq: 6,
        tempRef: 'new:Eaf',
        proposed: { localName: 'Eaf', labelZh: '电弧炉', synonyms: [] },
        confidence: 0.95,
        resolution: create,
        match: {
          kind: 'same',
          elementId: null,
          itemId: 'item-other-eaf',
          changeSetId: 'cs-other',
          changeSetTitle: OTHER_SET,
          label: '电炉',
          reason: '同一种炼钢炉的两种叫法。',
          decision: null,
          keptApart: false,
        },
      }),
    ];
    return items.map((item) => (item.match ? { ...item, rationale: null } : item));
  }

  /** Applies match decisions as the server does: "same" goes into the other one, "different" creates. */
  function alignmentServer(initial = changeSetFixture(aligned()), user?: UserInfo) {
    let state = initial;
    const update = (next: ChangeItem[]) => {
      state = { ...state, items: next, counts: countDecisions(next) };
    };
    const intoOther = (item: ChangeItem): ItemResolution => ({
      mode: 'into',
      elementId: item.match?.elementId ?? null,
      elementLabel: item.match?.label ?? null,
      localName: null,
      keptFields: [],
    });
    return reviewServer({
      initial,
      ...(user ? { user } : {}),
      extra: {
        'GET /api/change-sets/:id': () => state,
        'PATCH /api/change-sets/:id/items/:itemId': ({ params, body }) => {
          const patch = body as ItemPatch;
          update(
            state.items.map((item) => {
              if (item.id !== params.itemId) return item;
              if (patch.matchDecision === undefined || item.match === null) {
                return { ...item, ...(patch.decision ? { decision: patch.decision } : {}) };
              }
              const decision = patch.matchDecision;
              const same = decision === 'same' || (decision === null && item.match.kind === 'same');
              return { ...item, match: { ...item.match, decision }, resolution: same ? intoOther(item) : create };
            }),
          );
          return state.items.find((item) => item.id === params.itemId);
        },
        'POST /api/change-sets/:id/decisions': ({ body }) => {
          const { itemIds, decision } = body as { itemIds: string[]; decision: ChangeItem['decision'] };
          update(state.items.map((item) => (itemIds.includes(item.id) ? { ...item, decision } : item)));
          return state;
        },
      },
    });
  }

  it('says who the item matches, why, and in which place', async () => {
    alignmentServer();
    renderApp('/review/cs-converter');

    const bof = await screen.findByRole('article', { name: /^转炉/ });
    expect(within(bof).getByText('模型判为与已有元素“转炉”是同一概念')).toBeInTheDocument();
    expect(within(bof).getByText('理由：两者都指吹氧炼钢的炉子。')).toBeInTheDocument();
    // The model's reason carries the AI label next to it, besides the card's own.
    expect(within(bof).getAllByText('AI 建议')).toHaveLength(2);
    expect(within(bof).getByText('合并时将并入已有的“转炉”')).toBeInTheDocument();

    const taphole = card(/^出钢口/);
    expect(within(taphole).getByText(`可能与变更集《${OTHER_SET}》里的“出钢孔”重复`)).toBeInTheDocument();
    expect(within(taphole).getByText('理由：名称相近，所指部位相同。')).toBeInTheDocument();

    const ladleCar = card(/^钢水包/);
    expect(within(ladleCar).getByText('可能与本变更集里的“钢包”重复')).toBeInTheDocument();
    // Found without the model: no reason, so no second AI label.
    expect(within(ladleCar).queryByText(/^理由：/)).not.toBeInTheDocument();
    expect(within(ladleCar).getAllByText('AI 建议')).toHaveLength(1);

    // An item without a record shows nothing about one.
    expect(within(card(/^钢包/)).queryByText(/同一概念|重复/)).not.toBeInTheDocument();
  });

  it('does not attribute a same-concept record without a reason to the model', async () => {
    const records = aligned().map((item) =>
      item.id === 'item-eaf' && item.match ? { ...item, match: { ...item.match, reason: null } } : item,
    );
    alignmentServer(changeSetFixture(records));
    renderApp('/review/cs-converter');

    const eaf = await screen.findByRole('article', { name: /^电弧炉/ });
    expect(within(eaf).getByText(`与变更集《${OTHER_SET}》里的“电炉”是同一概念`)).toBeInTheDocument();
    expect(within(eaf).queryByText(/模型判为/)).not.toBeInTheDocument();
    expect(within(eaf).queryByText(/^理由：/)).not.toBeInTheDocument();
    expect(within(eaf).getAllByText('AI 建议')).toHaveLength(1);
  });

  it('merges a possible duplicate or keeps it apart, and pressing the decision again clears it', async () => {
    const user = userEvent.setup();
    const api = alignmentServer();
    renderApp('/review/cs-converter');

    const ladleCar = await screen.findByRole('article', { name: /^钢水包/ });
    await user.click(within(ladleCar).getByRole('button', { name: '并入' }));

    await waitFor(() => expect(within(card(/^钢水包/)).getByRole('button', { name: '并入' })).toHaveAttribute('aria-pressed', 'true'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle-car')[0]?.body).toEqual({ matchDecision: 'same' });
    expect(within(card(/^钢水包/)).getByText('已确认并入')).toBeInTheDocument();
    // It goes into what another item of this change set creates.
    expect(within(card(/^钢水包/)).getByText('合并时将并入本变更集里的“钢包”')).toBeInTheDocument();

    await user.click(within(card(/^钢水包/)).getByRole('button', { name: '并入' }));
    await waitFor(() => expect(within(card(/^钢水包/)).getByRole('button', { name: '并入' })).toHaveAttribute('aria-pressed', 'false'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-ladle-car')[1]?.body).toEqual({ matchDecision: null });

    const taphole = card(/^出钢口/);
    expect(within(taphole).getByRole('button', { name: '可能重复' })).toBeInTheDocument();
    await user.click(within(taphole).getByRole('button', { name: '保持分开' }));

    await waitFor(() => expect(within(card(/^出钢口/)).getByRole('button', { name: '保持分开' })).toHaveAttribute('aria-pressed', 'true'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-taphole')[0]?.body).toEqual({ matchDecision: 'different' });
    expect(within(card(/^出钢口/)).getByText('已确认保持分开，合并时照常新建')).toBeInTheDocument();
    // Kept apart: the duplicate flag is gone.
    expect(within(card(/^出钢口/)).queryByRole('button', { name: '可能重复' })).not.toBeInTheDocument();
  });

  it('keeps apart what the model took for the same concept', async () => {
    const user = userEvent.setup();
    const api = alignmentServer();
    renderApp('/review/cs-converter');

    const bof = await screen.findByRole('article', { name: /^转炉/ });
    // The model already said "same": only keeping apart is offered.
    expect(within(bof).queryByRole('button', { name: '并入' })).not.toBeInTheDocument();
    await user.click(within(bof).getByRole('button', { name: '保持分开' }));

    await waitFor(() => expect(within(card(/^转炉/)).getByRole('button', { name: '保持分开' })).toHaveAttribute('aria-pressed', 'true'));
    expect(api.calls('PATCH', '/api/change-sets/cs-converter/items/item-bof')[0]?.body).toEqual({ matchDecision: 'different' });
    expect(within(card(/^转炉/)).queryByText(/合并时将并入/)).not.toBeInTheDocument();
  });

  it('only shows the other reviewer’s conclusion when they kept the two apart', async () => {
    alignmentServer();
    renderApp('/review/cs-converter');

    const slag = await screen.findByRole('article', { name: /^炉渣/ });
    expect(within(slag).getByText('可能与已有元素“渣”重复')).toBeInTheDocument();
    expect(within(slag).getByText('对方的审核人已定为保持分开，合并时照常新建')).toBeInTheDocument();
    expect(within(slag).queryByRole('button', { name: '并入' })).not.toBeInTheDocument();
    expect(within(slag).queryByRole('button', { name: '保持分开' })).not.toBeInTheDocument();
  });

  it('offers no alignment decisions to viewers', async () => {
    alignmentServer(changeSetFixture(aligned()), userWithRole('viewer'));
    renderApp('/review/cs-converter');

    const taphole = await screen.findByRole('article', { name: /^出钢口/ });
    expect(within(taphole).getByText(`可能与变更集《${OTHER_SET}》里的“出钢孔”重复`)).toBeInTheDocument();
    expect(within(taphole).queryByRole('button', { name: '并入' })).not.toBeInTheDocument();
    expect(within(taphole).queryByRole('button', { name: '保持分开' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /并入已有元素/ })).not.toBeInTheDocument();
  });

  it('leaves items with a record out of the high-confidence bulk accept', async () => {
    const user = userEvent.setup();
    const api = alignmentServer();
    renderApp('/review/cs-converter');

    await user.click(await screen.findByRole('button', { name: '接受全部高置信度项（1）' }));

    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body).toEqual({ itemIds: ['item-ladle'], decision: 'accepted' });
  });

  it('accepts the items the model took for the same concept after listing where each goes', async () => {
    const user = userEvent.setup();
    const api = alignmentServer();
    renderApp('/review/cs-converter');

    await user.click(await screen.findByRole('button', { name: '并入已有元素（2）' }));

    const dialog = await screen.findByRole('dialog', { name: '并入已有元素' });
    const rows = within(dialog).getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual(['转炉将并入转炉（已有元素）', `电弧炉将并入电炉（变更集《${OTHER_SET}》）`]);
    // Nothing is sent before the reviewer confirms.
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(0);

    await user.click(within(dialog).getByRole('button', { name: '接受这 2 项' }));

    await waitFor(() => expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')).toHaveLength(1));
    expect(api.calls('POST', '/api/change-sets/cs-converter/decisions')[0]?.body).toEqual({ itemIds: ['item-bof', 'item-eaf'], decision: 'accepted' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(within(card(/^电弧炉/)).getByRole('button', { name: '接受' })).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.queryByRole('button', { name: /并入已有元素/ })).not.toBeInTheDocument();
  });

  it('counts only undecided same-concept items not kept apart', async () => {
    const user = userEvent.setup();
    const records = aligned().map((item) =>
      item.id === 'item-eaf' && item.match ? { ...item, match: { ...item.match, keptApart: true } } : item,
    );
    alignmentServer(changeSetFixture(records));
    renderApp('/review/cs-converter');

    expect(await screen.findByRole('button', { name: '并入已有元素（1）' })).toBeInTheDocument();
    await user.click(within(card(/^转炉/)).getByRole('button', { name: '保持分开' }));

    await waitFor(() => expect(screen.queryByRole('button', { name: /并入已有元素/ })).not.toBeInTheDocument());
  });

  it('offers neither merging nor keeping apart for a record of the same main name', async () => {
    const records = aligned().map((item) =>
      item.id === 'item-eaf' && item.match ? { ...item, match: { ...item.match, kind: 'name' as const, reason: null } } : item,
    );
    alignmentServer(changeSetFixture(records));
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /^电弧炉/ });
    const eaf = card(/^电弧炉/);
    expect(within(eaf).getByText(`与变更集《${OTHER_SET}》里的“电炉”主名称相同，合并时随它并入同一元素`)).toBeInTheDocument();
    expect(within(eaf).queryByRole('button', { name: '保持分开' })).not.toBeInTheDocument();
    expect(within(eaf).queryByRole('button', { name: '并入' })).not.toBeInTheDocument();
    // Not part of the same-concept bulk accept either: the merge follows the name.
    expect(await screen.findByRole('button', { name: '并入已有元素（1）' })).toBeInTheDocument();
  });

  it('offers no same-concept bulk accept outside AI extraction', async () => {
    alignmentServer(changeSetFixture(aligned(), { source: 'ai_assistant' }));
    renderApp('/review/cs-converter');

    await screen.findByRole('article', { name: /^转炉/ });
    expect(screen.queryByRole('button', { name: /并入已有元素/ })).not.toBeInTheDocument();
  });
});
