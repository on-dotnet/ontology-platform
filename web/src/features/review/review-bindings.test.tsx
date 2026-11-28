import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Join } from '@/features/bindings/api';
import { changeSetFixture, elementFixture, itemFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, renderApp, userWithRole } from '@/test/utils';

import type { BindingImpact, ChangeItem, ChangeSetDetail } from './api';

const heat = elementFixture({ id: 'el-heat', localName: 'Heat', labelZh: '炉次', labelEn: 'Heat' });
const weight = elementFixture({ id: 'el-weight', kind: 'property', localName: 'weight', labelZh: '重量', domainId: 'el-heat', datatype: 'decimal' });
const inCast = elementFixture({ id: 'el-in-cast', kind: 'relation_type', localName: 'inCast', labelZh: '所属浇次', domainId: 'el-heat' });

const catalog = (id: string, fact: 'table' | 'column' | 'primary_key' | 'foreign_key', quote: string, column: string | null = null) => ({
  id,
  kind: 'catalog' as const,
  documentId: null,
  chunkId: null,
  source: { dataSourceId: 'ds-mes', schema: 'mes', table: 'heat_v', column, fact },
  quote,
  charStart: null,
  charEnd: null,
});

function bindingItems(): ChangeItem[] {
  return [
    itemFixture({
      id: 'item-table',
      kind: 'type_binding',
      tempRef: 'b:heat',
      confidence: 0.86,
      flags: ['key_unverified'],
      decision: 'rejected',
      proposed: {
        subjectRef: 'el-heat',
        binding: { target: 'table', dataSourceId: 'ds-mes', schema: 'mes', table: 'heat_v', keyColumns: ['heat_no'] },
      },
      evidence: [
        catalog('ev-pk', 'column', 'heat_no varchar(20) NOT NULL，注释：炉次号', 'heat_no'),
        catalog('ev-table', 'table', 'VIEW mes.heat_v，注释：炉次'),
      ],
    }),
    itemFixture({
      id: 'item-weight',
      seq: 2,
      kind: 'property_binding',
      tempRef: null,
      confidence: 0.9,
      proposed: { subjectRef: 'el-weight', parentRef: 'b:heat', binding: { target: 'column', column: 'weight_t' } },
    }),
    itemFixture({
      id: 'item-relation',
      seq: 3,
      op: 'update',
      kind: 'relation_binding',
      tempRef: null,
      targetElementId: 'bd-in-cast',
      confidence: 0.7,
      proposed: { binding: { target: 'join', join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['cast_no'] } } },
      before: {
        subjectRef: 'el-in-cast',
        domainRef: 'bd-heat',
        rangeRef: 'bd-cast',
        binding: { target: 'join', join: { kind: 'foreign_key', side: 'source', columns: ['cast_id'], references: ['id'] } },
      },
    }),
  ];
}

function server(changeSet: ChangeSetDetail, impacts: { items: BindingImpact[] } | Response = { items: [] }, onDecision?: () => void) {
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture({ openChangeSetCount: 1 })],
      'GET /api/change-sets': () => [changeSet],
      'GET /api/change-sets/:id': () => changeSet,
      'GET /api/ontologies/:ontologyId/change-sets/:id/binding-impacts': () => impacts,
      'PATCH /api/change-sets/:id/items/:itemId': ({ params }) => {
        onDecision?.();
        return { ...changeSet.items.find((item) => item.id === params.itemId), decision: 'rejected' };
      },
      'GET /api/ontologies/:id/elements': () => [heat, weight, inCast],
    },
    { user: userWithRole('reviewer') },
  );
}

describe('existing binding impacts', () => {
  const changeSet = changeSetFixture([], { id: 'cs-impacts', title: '修改本体', source: 'manual', documentId: null });

  it('shows the count, names and reasons of affected bindings', async () => {
    server(changeSet, { items: [
      { elementId: 'binding-a', kind: 'property_binding', label: '重量 → mes.heat.weight_t', code: 'binding.invalid', message: 'invalid' },
      { elementId: 'binding-b', kind: 'property_binding', label: '编号 → mes.heat.heat_no', code: 'binding.duplicate', message: 'duplicate' },
    ] });
    renderApp('/review/cs-impacts');
    expect(await screen.findByText('合并后有 2 条已有绑定会失效')).toBeInTheDocument();
    expect(screen.getByText('重量 → mes.heat.weight_t')).toBeInTheDocument();
    expect(screen.getByText('编号 → mes.heat.heat_no')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === 'LI' && element.textContent?.includes('重量 → mes.heat.weight_t') === true)).toHaveTextContent('引用或结构不再有效');
  });

  it('falls back to a generic reason for an unknown code', async () => {
    server(changeSet, { items: [
      { elementId: 'binding-a', kind: 'property_binding', label: '重量 → mes.heat.weight_t', code: 'binding.new_problem', message: 'unknown' },
    ] });
    renderApp('/review/cs-impacts');
    await screen.findByText('合并后有 1 条已有绑定会失效');
    expect(screen.getByText((_, element) => element?.tagName === 'LI' && element.textContent?.includes('重量 → mes.heat.weight_t') === true)).toHaveTextContent('绑定校验不通过');
  });

  it('refreshes impacts after an item decision and removes the notice', async () => {
    const user = userEvent.setup();
    const impactResponse: { items: BindingImpact[] } = { items: [
      { elementId: 'binding-a', kind: 'property_binding', label: '重量 → mes.heat.weight_t', code: 'binding.invalid', message: 'invalid' },
    ] };
    const detail = changeSetFixture([itemFixture({ id: 'item-domain', op: 'update', kind: 'property', targetElementId: weight.id, proposed: { domainRef: 'el-other' } })], {
      id: 'cs-impacts', title: '修改本体', source: 'manual', documentId: null,
    });
    const api = server(detail, impactResponse, () => { impactResponse.items = []; });
    renderApp('/review/cs-impacts');
    expect(await screen.findByText('合并后有 1 条已有绑定会失效')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '拒绝' }));
    await waitFor(() => expect(api.calls('GET', '/api/ontologies/onto-steel/change-sets/cs-impacts/binding-impacts')).toHaveLength(2));
    await waitFor(() => expect(screen.queryByText(/已有绑定会失效/)).not.toBeInTheDocument());
  });

  it('hides the notice for an empty response', async () => {
    const api = server(changeSet);
    renderApp('/review/cs-impacts');
    await screen.findByText('修改本体');
    await waitFor(() => expect(api.calls('GET', '/api/ontologies/onto-steel/change-sets/cs-impacts/binding-impacts')).toHaveLength(1));
    expect(screen.queryByText(/已有绑定会失效/)).not.toBeInTheDocument();
  });

  it('hides the notice when the API fails', async () => {
    const api = server(changeSet, new Response(null, { status: 500 }));
    renderApp('/review/cs-impacts');
    await screen.findByText('修改本体');
    await waitFor(() => expect(api.calls('GET', '/api/ontologies/onto-steel/change-sets/cs-impacts/binding-impacts')).toHaveLength(1));
    expect(screen.queryByText(/已有绑定会失效/)).not.toBeInTheDocument();
  });

  it('does not request impacts for a closed change set', async () => {
    const api = server({ ...changeSet, status: 'merged' });
    renderApp('/review/cs-impacts');
    await screen.findByText('修改本体');
    expect(api.calls('GET', '/api/ontologies/onto-steel/change-sets/cs-impacts/binding-impacts')).toHaveLength(0);
  });
});

describe('binding items in review', () => {
  it('says what each binding does in one sentence, with the AI label, the key notice and what a rejected table takes along', async () => {
    const user = userEvent.setup();
    server(changeSetFixture(bindingItems(), { id: 'cs-binding', title: 'AI 绑定建议：MES', source: 'ai_binding', documentId: null }));
    renderApp('/review/cs-binding');

    const table = await screen.findByRole('article', { name: '炉次 → 表 mes.heat_v（主键 heat_no）' });
    expect(within(table).getByText('AI 建议')).toBeInTheDocument();
    expect(within(table).getByText('置信度高')).toBeInTheDocument();
    expect(within(table).getByText('请确认主键列')).toBeInTheDocument();
    expect(within(table).getByText(/这张表没有主键约束/)).toBeInTheDocument();
    // The notice replaces the flag's "!".
    expect(within(table).queryByRole('button', { name: '主键未经约束确认' })).not.toBeInTheDocument();

    const column = screen.getByRole('article', { name: '属性 重量 → 列 weight_t' });
    expect(within(column).getByText('所属的表绑定未被接受，这一项不会生效')).toBeInTheDocument();
    expect(within(table).queryByText('所属的表绑定未被接受，这一项不会生效')).not.toBeInTheDocument();

    const relation = screen.getByRole('article', { name: '关系 所属浇次 → 外键（在起点表）cast_no → cast_no' });
    expect(within(relation).getByText('外键（在起点表）cast_id → id')).toBeInTheDocument();
    expect(within(relation).getByText('外键（在起点表）cast_no → cast_no')).toBeInTheDocument();

    // Catalog evidence is listed fact by fact, the table first, not as a document excerpt.
    await user.click(within(table).getByRole('button', { name: /证据/ }));
    const facts = await screen.findByRole('list', { name: '目录依据' });
    const entries = within(facts).getAllByRole('listitem');
    expect(entries.map((entry) => entry.textContent)).toEqual([
      expect.stringContaining('VIEW mes.heat_v，注释：炉次'),
      expect.stringContaining('heat_no varchar(20) NOT NULL，注释：炉次号'),
    ]);
    expect(within(entries[1] as HTMLElement).getByText('mes.heat_v.heat_no')).toBeInTheDocument();
  });

  it('compares updates that change only the side of a foreign key or only the link-table columns', async () => {
    const join = (value: Join) => ({ binding: { target: 'join' as const, join: value } });
    const ends = { subjectRef: 'el-in-cast', domainRef: 'bd-heat', rangeRef: 'bd-cast' };
    const fk = { kind: 'foreign_key' as const, columns: ['cast_no'], references: ['cast_no'] };
    const link = { kind: 'link_table' as const, schema: 'mes', table: 'heat_cast' };
    server(
      changeSetFixture(
        [
          itemFixture({
            id: 'item-side',
            op: 'update',
            kind: 'relation_binding',
            tempRef: null,
            targetElementId: 'bd-in-cast',
            proposed: join({ ...fk, side: 'target' }),
            before: { ...ends, ...join({ ...fk, side: 'source' }) },
          }),
          itemFixture({
            id: 'item-link',
            seq: 2,
            op: 'update',
            kind: 'relation_binding',
            tempRef: null,
            targetElementId: 'bd-in-cast-2',
            proposed: join({ ...link, sourceColumns: ['heat_key'], targetColumns: ['cast_key'] }),
            before: { ...ends, ...join({ ...link, sourceColumns: ['heat_id'], targetColumns: ['cast_key'] }) },
          }),
        ],
        { id: 'cs-joins', title: '改连接', source: 'manual', documentId: null },
      ),
    );
    renderApp('/review/cs-joins');

    const side = await screen.findByRole('article', { name: '关系 所属浇次 → 外键（在终点表）cast_no → cast_no' });
    expect(within(side).getByText('外键（在起点表）cast_no → cast_no')).toBeInTheDocument();
    const columns = screen.getByRole('article', { name: '关系 所属浇次 → 连接表 mes.heat_cast（起点 heat_key；终点 cast_key）' });
    expect(within(columns).getByText('连接表 mes.heat_cast（起点 heat_id；终点 cast_key）')).toBeInTheDocument();
  });

  it('names who submitted a change set through MCP', async () => {
    server(
      changeSetFixture(bindingItems(), {
        id: 'cs-mcp',
        title: 'MCP 提议',
        source: 'mcp',
        documentId: null,
        createdBy: '00000000-0000-4000-8000-000000000999',
        createdByName: '张工',
      }),
    );
    renderApp('/review/cs-mcp');

    expect(await screen.findByText('提交人：张工')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
    // Not an AI proposal: no AI label on the items.
    expect(screen.queryByText('AI 建议')).not.toBeInTheDocument();
  });

  it('lists the MCP submitter in the change set list, and a removed user as such', async () => {
    server(changeSetFixture([], { id: 'cs-mcp', title: 'MCP 提议', source: 'mcp', documentId: null, createdByName: null }));
    renderApp('/review');

    const row = (await screen.findByRole('link', { name: 'MCP 提议' })).closest('tr') as HTMLElement;
    expect(within(row).getByText('提交人：已不存在的用户')).toBeInTheDocument();
  });
});
