import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { changeSetFixture, documentFixture, elementFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import type { UserInfo } from '@/features/auth/api';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import { countDecisions, type ChangeItem, type ChangeSetDetail, type ItemPatch } from './api';

const CHUNK_TEXT = '第一章 总则\n钢包是盛装和运送钢水的容器，使用前应烘烤至规定温度。\n板坯由连铸机生产。';
const QUOTE = '钢包是盛装和运送钢水的容器';

function items(): ChangeItem[] {
  return [
    itemFixture({
      evidence: [
        {
          id: 'ev-ladle',
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
      evidence: [{ id: 'ev-slab', documentId: 'doc-converter', chunkId: 'chunk-1', quote: '板坯是连铸的产品', charStart: null, charEnd: null }],
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
          ? { ...item, ...(patch.decision ? { decision: patch.decision } : {}), ...(patch.edited !== undefined ? { edited: patch.edited } : {}) }
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

