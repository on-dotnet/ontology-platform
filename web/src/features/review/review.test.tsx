import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { changeSetFixture, documentFixture, elementFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import type { UserInfo } from '@/features/auth/api';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import { countDecisions, type ChangeItem, type ChangeSetDetail, type ItemPatch, type ItemResolution } from './api';

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
    itemFixture({ ...imported, id: 'item-axiom', seq: 2, kind: 'axiom', tempRef: null, flags: ['non_standard'], proposed: { turtle: AXIOM } }),
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

describe('import change set review', () => {
  it('shows constraints with their rules, axioms as Turtle, and deletes and restores with the current values', async () => {
    const api = importServer();
    renderApp('/review/cs-import');

    const shape = await screen.findByRole('article', { name: /钢水校验/ });
    expect(screen.getByText('导入', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /^约束/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /^高级公理/ })).toBeInTheDocument();
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

    const axiom = card(/steel:Slab owl:unionOf/);
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

    const gone = card(/owl:disjointWith/);
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

describe('change item pagination', () => {
  const many = Array.from({ length: 120 }, (_, index) =>
    itemFixture({
      id: `item-${index}`,
      seq: index + 1,
      kind: index < 70 ? 'entity_type' : 'property',
      tempRef: `new:N${index}`,
      proposed: { localName: `N${index}`, labelZh: `项目${String(index + 1).padStart(3, '0')}`, ...(index < 70 ? {} : { domainRef: 'el-molten-steel', datatype: 'decimal' }) },
      confidence: 0.9,
      evidence: [{ id: `ev-`, kind: 'document', source: null, documentId: 'doc-converter', chunkId: 'chunk-1', quote: QUOTE, charStart: null, charEnd: null }],
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
