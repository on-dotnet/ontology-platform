import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import { listKey, rememberSource } from '@/features/datasources/api';
import type { EditRequest, Element } from '@/features/ontologies/api';
import i18n from '@/i18n';
import { elementDetailFixture, elementFixture, impactFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import type { CatalogTable, DataSource, RelationBindingView, TypeBindingView } from './api';
import { bindingModel, unbindEdits } from './binding-edits';

const EDITS = '/api/ontologies/onto-steel/edits';
const NOW = '2026-11-25T08:00:00Z';
const formText = i18n.getFixedT('zh-CN', 'translation', 'bindings.form');

const batch = elementFixture({ id: 'el-batch', localName: 'Batch', labelZh: '批次', labelEn: 'Batch', definitionZh: null });
const heat = elementFixture({ id: 'el-heat', localName: 'Heat', labelZh: '炉次', labelEn: 'Heat', definitionZh: null, parentId: 'el-batch' });
const cast = elementFixture({ id: 'el-cast', localName: 'Cast', labelZh: '浇次', labelEn: 'Cast', definitionZh: null });
const weight = elementFixture({
  id: 'el-weight',
  kind: 'property',
  localName: 'weight',
  labelZh: '重量',
  labelEn: 'Weight',
  definitionZh: null,
  domainId: 'el-heat',
  datatype: 'decimal',
  unit: 't',
});
const batchCode = elementFixture({
  id: 'el-batch-code',
  kind: 'property',
  localName: 'batchCode',
  labelZh: '批次号',
  labelEn: 'Batch code',
  definitionZh: null,
  domainId: 'el-batch',
  datatype: 'string',
});
const inCast = elementFixture({
  id: 'el-in-cast',
  kind: 'relation_type',
  localName: 'inCast',
  labelZh: '所属浇次',
  labelEn: 'In cast',
  definitionZh: null,
  domainId: 'el-heat',
  rangeId: 'el-cast',
});
const elements: Element[] = [batch, heat, cast, weight, batchCode, inCast];

const firstHeat = elementFixture({
  id: 'el-first-heat',
  kind: 'relation_type',
  localName: 'firstHeat',
  labelZh: '首炉',
  labelEn: 'First heat',
  definitionZh: null,
  domainId: cast.id,
  rangeId: heat.id,
});

const mes: DataSource = {
  id: 'ds-mes',
  name: 'MES',
  kind: 'postgresql',
  status: 'active',
  connection: null,
  hasCredential: true,
  credentialUpdatedAt: NOW,
  allowSamples: false,
  lastTest: null,
  catalog: { status: 'ready', refreshedAt: NOW, errorCode: null, tableCount: 2 },
  boundTypeCount: 1,
  revision: 1,
  createdAt: NOW,
  updatedAt: NOW,
};

const heatTable: CatalogTable = {
  schema: 'mes',
  name: 'heat',
  kind: 'table',
  comment: '炉次',
  columnCount: 3,
  boundType: null,
  columns: [
    { name: 'heat_no', type: 'varchar(20)', family: 'string', nullable: false, comment: '炉次号', position: 1 },
    { name: 'weight_t', type: 'numeric(8,2)', family: 'decimal', nullable: true, comment: '重量', position: 2 },
    { name: 'note', type: 'jsonb', family: 'other', nullable: true, comment: null, position: 3 },
  ],
  primaryKey: ['heat_no'],
  foreignKeys: [],
  refreshedAt: NOW,
};

/** The heat bound to mes.heat: weight to weight_t, the inherited batch code not yet, the relation's column gone. */
const boundHeat = {
  typeId: 'el-heat',
  table: {
    elementId: 'bd-heat',
    revision: 1,
    dataSource: { id: 'ds-mes', name: 'MES', status: 'active' },
    schema: 'mes',
    table: 'heat',
    keyColumns: ['heat_no'],
    check: 'ok',
  },
  properties: [
    {
      propertyId: 'el-weight',
      label: '重量',
      datatype: 'decimal',
      inherited: false,
      column: { elementId: 'bd-weight', revision: 1, column: 'weight_t', columnType: 'numeric(8,2)', check: 'ok' },
    },
    { propertyId: 'el-batch-code', label: '批次号', datatype: 'string', inherited: true, column: null },
  ],
  relations: [
    {
      relationId: 'el-in-cast',
      label: '所属浇次',
      direction: 'out',
      otherTypeId: 'el-cast',
      otherTypeLabel: '浇次',
      join: {
        elementId: 'bd-in-cast',
        revision: 1,
        join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['cast_no'] },
        check: 'missing_column',
      },
    },
  ],
  openChangeSetIds: ['cs-binding'],
} satisfies TypeBindingView;

const unboundHeat: TypeBindingView = { typeId: 'el-heat', table: null, properties: [], relations: [], openChangeSetIds: [] };

const currentHeatTable: CatalogTable = {
  ...heatTable,
  columnCount: 4,
  columns: [...heatTable.columns, { name: 'cast_no', type: 'text', family: 'string', nullable: false, comment: null, position: 4 }],
};
const archiveTable: CatalogTable = {
  ...currentHeatTable,
  name: 'archived_heat',
  columns: currentHeatTable.columns.map((column) => (column.name === 'heat_no' ? { ...column, name: 'archive_no' } : column)),
  primaryKey: ['archive_no'],
};
const castTable: CatalogTable = {
  ...heatTable,
  name: 'casting_sequence',
  comment: '浇次',
  columnCount: 2,
  columns: [
    { name: 'sequence_no', type: 'text', family: 'string', nullable: false, comment: null, position: 1 },
    { name: 'first_heat_no', type: 'text', family: 'string', nullable: true, comment: null, position: 2 },
  ],
  primaryKey: ['sequence_no'],
};

const outgoing: RelationBindingView = {
  relationId: inCast.id, label: '所属浇次', direction: 'out', otherTypeId: cast.id, otherTypeLabel: '浇次', join: null,
};
const incoming: RelationBindingView = {
  relationId: firstHeat.id, label: '首炉', direction: 'in', otherTypeId: cast.id, otherTypeLabel: '浇次', join: null,
};
const editableHeat: TypeBindingView = {
  ...boundHeat,
  table: { ...boundHeat.table, revision: 3 },
  properties: boundHeat.properties.map((property) => ({
    ...property,
    column: property.column ? { ...property.column, revision: 5 } : null,
  })),
  relations: [outgoing, incoming],
  openChangeSetIds: [],
};

const heatWithJoins: TypeBindingView = {
  ...editableHeat,
  relations: [
    {
      ...outgoing,
      join: {
        elementId: 'bd-in-cast', revision: 7, check: 'ok',
        join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['sequence_no'] },
      },
    },
    {
      ...incoming,
      join: {
        elementId: 'bd-first-heat', revision: 9, check: 'ok',
        join: { kind: 'foreign_key', side: 'source', columns: ['first_heat_no'], references: ['heat_no'] },
      },
    },
  ],
};

const nextHeat = elementFixture({
  id: 'el-next-heat',
  kind: 'relation_type',
  localName: 'nextHeat',
  labelZh: '下一炉',
  labelEn: 'Next heat',
  definitionZh: null,
  domainId: heat.id,
  rangeId: heat.id,
});
// The server lists a self-relation once in each direction.
const selfOut: RelationBindingView = {
  relationId: nextHeat.id, label: '下一炉', direction: 'out', otherTypeId: heat.id, otherTypeLabel: '炉次', join: null,
};
const selfIn: RelationBindingView = { ...selfOut, direction: 'in' };
const selfJoin: NonNullable<RelationBindingView['join']> = {
  elementId: 'bd-next', revision: 4, check: 'ok',
  join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['heat_no'] },
};
const heatWithSelfJoin: TypeBindingView = {
  ...editableHeat,
  relations: [{ ...selfOut, join: selfJoin }, { ...selfIn, join: selfJoin }],
};

interface BindingServerOptions {
  view: TypeBindingView;
  user?: UserInfo;
  ontologyElements?: Element[];
  otherViews?: TypeBindingView[];
  tables?: CatalogTable[];
  /** Read on each request, so a test can change what the data page would have changed. */
  sources?: DataSource[];
  /** Answers the data source list instead of `sources`. */
  sourceList?: RouteHandler;
  nextCursor?: string;
  editError?: string;
}

function bindingServer({
  view, user, ontologyElements = elements, otherViews = [], tables = [heatTable], sources = [mes], sourceList, nextCursor, editError,
}: BindingServerOptions) {
  const views = [view, ...otherViews];
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/elements': ({ query }) => {
        const kind = query.get('kind');
        return ontologyElements.filter((element) => !kind || element.kind === kind);
      },
      'GET /api/ontologies/:id/elements/:elementId': ({ params }) => {
        const element = ontologyElements.find((item) => item.id === params.elementId);
        return element ? elementDetailFixture(element) : problemResponse(404, 'element.not_found');
      },
      'GET /api/ontologies/:id/elements/:elementId/impact': ({ params }) => impactFixture(params.elementId ?? ''),
      'GET /api/ontologies/:id/bindings': ({ query }) => {
        const typeId = query.get('typeId');
        return views.filter((item) => (typeId ? item.typeId === typeId : item.table !== null));
      },
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
      'GET /api/data-sources': sourceList ?? (() => sources),
      'GET /api/data-sources/:id/catalog/tables': ({ query }) => ({
        // A later page holds the tables after the first, so a test can tell the pages apart.
        items: tables.slice(query.has('cursor') ? 1 : 0)
          .filter((table) => table.name.includes(query.get('q')?.toLowerCase() ?? ''))
          .map(({ schema, name, kind, comment, columnCount, boundType }) => ({ schema, name, kind, comment, columnCount, boundType })),
        nextCursor: nextCursor ?? null,
      }),
      'GET /api/data-sources/:id/catalog/tables/:schema/:table': ({ params }) =>
        tables.find((table) => params.id === mes.id && params.schema === table.schema && params.table === table.name)
          ?? problemResponse(404, 'catalog.table_not_found'),
      'POST /api/ontologies/:id/edits': ({ body }) => {
        if (editError) return problemResponse(422, editError);
        const request = body as EditRequest;
        return { changeSetId: 'cs-manual', merged: request.apply, merge: request.apply ? { applied: request.items.length, skipped: [] } : null };
      },
    },
    { user },
  );
}

async function openHeat(user: ReturnType<typeof userEvent.setup>) {
  const table = await screen.findByRole('table', { name: '本体元素' });
  await user.click(within(table).getByRole('button', { name: '炉次' }));
  const dialog = await screen.findByRole('dialog', { name: '炉次' });
  return within(dialog).findByRole('region', { name: '数据绑定' });
}

async function openEditor({
  view = editableHeat, tables = [currentHeatTable, castTable], sources, sourceList, nextCursor, editError, extraElements = [],
}: Partial<Pick<BindingServerOptions, 'view' | 'tables' | 'sources' | 'sourceList' | 'nextCursor' | 'editError'>> & {
  extraElements?: Element[];
} = {}) {
  const other: TypeBindingView = {
    typeId: cast.id,
    table: { ...boundHeat.table, elementId: 'bd-cast', table: castTable.name, keyColumns: ['sequence_no'] },
    properties: [],
    relations: view.relations.map((relation) => ({
      ...relation, direction: relation.direction === 'in' ? 'out' : 'in', otherTypeId: heat.id, otherTypeLabel: '炉次',
    })),
    openChangeSetIds: [],
  };
  const user = userEvent.setup();
  const ontologyElements = [...elements, firstHeat, ...extraElements];
  const api = bindingServer({
    view, tables, sources, sourceList, nextCursor, editError, user: userWithRole('editor'), ontologyElements, otherViews: [other],
  });
  const { queryClient } = renderApp('/ontology?ontology=onto-steel&view=list');
  const section = await openHeat(user);
  await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.edit') }));
  const dialog = within(await screen.findByRole('dialog', { name: formText('editTitle', { type: '炉次' }) }));
  return {
    api, user, dialog, ontologyElements, queryClient,
    save: () => user.click(dialog.getByRole('button', { name: formText('save') })),
  };
}

async function openBinder(user: ReturnType<typeof userEvent.setup>) {
  const section = await openHeat(user);
  await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.bind') }));
  return within(await screen.findByRole('dialog', { name: formText('createTitle', { type: '炉次' }) }));
}

async function submittedItems(api: ReturnType<typeof bindingServer>) {
  await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
  const request = api.calls('POST', EDITS)[0]?.body as EditRequest;
  expect(request.apply).toBe(false);
  return request.items;
}

async function chooseForeignKey(user: ReturnType<typeof userEvent.setup>, relation: HTMLElement, table: RegExp) {
  const group = within(relation);
  await user.selectOptions(group.getByRole('combobox', { name: formText('joinKind') }), formText('joinKinds.foreign_key'));
  const side = await group.findByRole('combobox', { name: formText('side') });
  await user.selectOptions(side, await within(side).findByRole('option', { name: table }));
  return {
    columns: await group.findByRole('group', { name: formText('columns') }),
    references: await group.findByRole('group', { name: formText('references') }),
  };
}

async function checkColumn(user: ReturnType<typeof userEvent.setup>, fieldset: HTMLElement, name: string) {
  const group = within(fieldset);
  const checkbox = await group.findByRole('checkbox', { name });
  if (!group.queryByRole('checkbox', { name, checked: true })) await user.click(checkbox);
}

describe('BindingSection', () => {
  it('shows the bound table, the property columns, the relation join and what the catalog no longer has', async () => {
    const user = userEvent.setup();
    bindingServer({ view: boundHeat, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const section = await openHeat(user);
    expect(await within(section).findByText('MES')).toBeInTheDocument();
    expect(within(section).getByText('mes.heat')).toBeInTheDocument();
    expect(within(section).getByText('heat_no')).toBeInTheDocument();

    const columns = within(section).getByRole('table', { name: '属性与列' });
    const weightRow = within(columns).getByRole('row', { name: /重量/ });
    expect(within(weightRow).getByText('weight_t')).toBeInTheDocument();
    const codeRow = within(columns).getByRole('row', { name: /批次号/ });
    expect(within(codeRow).getByText('继承')).toBeInTheDocument();
    expect(within(codeRow).getByText('未绑定')).toBeInTheDocument();

    expect(within(section).getByText('外键（在起点表）cast_no → cast_no')).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: '目录里找不到这一列，可能已被改名' })).toBeInTheDocument();

    expect(within(section).getByText('有待审核的绑定修改')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-binding');
    expect(within(section).getByRole('button', { name: '编辑绑定' })).toBeInTheDocument();
  });

  it('says which table holds the foreign key of a relation join', async () => {
    // #75: the same columns read the other way round when the key sits on the target table.
    const user = userEvent.setup();
    const relations = boundHeat.relations.map((relation) => ({
      ...relation,
      join: { ...relation.join, join: { ...relation.join.join, side: 'target' as const } },
    }));
    bindingServer({ view: { ...boundHeat, relations }, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const section = await openHeat(user);
    expect(await within(section).findByText('外键（在终点表）cast_no → cast_no')).toBeInTheDocument();
    expect(within(section).queryByText(/在起点表/)).toBeNull();
  });

  it('tells a viewer that nothing is bound, without a way to bind', async () => {
    const user = userEvent.setup();
    bindingServer({ view: unboundHeat, user: userWithRole('viewer') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const section = await openHeat(user);
    expect(await within(section).findByText('还没有绑定数据')).toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: '绑定数据' })).not.toBeInTheDocument();
  });

  it('binds a type to a table and its properties to fitting columns in one manual change set', async () => {
    const user = userEvent.setup();
    const api = bindingServer({ view: unboundHeat, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const section = await openHeat(user);
    await user.click(await within(section).findByRole('button', { name: '绑定数据' }));
    const dialog = await screen.findByRole('dialog', { name: '绑定数据：炉次' });
    expect(within(dialog).getByText('绑定并发布后，这些列的数据对平台的所有登录用户可见。')).toBeInTheDocument();
    expect(within(dialog).getByText('保存后提交审核，审核通过后生效。')).toBeInTheDocument();

    await user.selectOptions(within(dialog).getByRole('combobox', { name: '数据源' }), 'MES');
    await user.click(await within(dialog).findByRole('option', { name: /mes\.heat/ }));
    // The primary key is the default key.
    expect(await within(dialog).findByRole('checkbox', { name: 'heat_no' })).toBeChecked();

    // Only columns that fit a decimal are offered for the weight.
    const weightColumn = within(dialog).getByRole('combobox', { name: '重量' });
    expect(within(weightColumn).queryByRole('option', { name: /heat_no/ })).not.toBeInTheDocument();
    await user.selectOptions(weightColumn, 'weight_t');

    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    const request = api.calls('POST', EDITS)[0]?.body as EditRequest;
    expect(request.apply).toBe(false);
    const [table, column, ...rest] = request.items;
    expect(rest).toEqual([]);
    expect(table).toMatchObject({
      op: 'create',
      kind: 'type_binding',
      fields: {
        subjectRef: 'el-heat',
        binding: { target: 'table', dataSourceId: 'ds-mes', schema: 'mes', table: 'heat', keyColumns: ['heat_no'] },
      },
    });
    expect(table?.tempRef).toBeTruthy();
    expect(column).toEqual({
      op: 'create',
      kind: 'property_binding',
      fields: { subjectRef: 'el-weight', parentRef: table?.tempRef, binding: { target: 'column', column: 'weight_t' } },
    });
  });

  it('updates only the type binding when the editor changes the key columns', async () => {
    const { api, user, dialog, save } = await openEditor();
    expect(await dialog.findByRole('checkbox', { name: 'heat_no' })).toBeChecked();
    await user.click(dialog.getByRole('checkbox', { name: 'cast_no' }));
    await user.type(dialog.getByRole('searchbox', { name: formText('table') }), 'heat{Enter}');
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await save();

    expect(await submittedItems(api)).toEqual([{
      op: 'update', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3,
      fields: { binding: { target: 'table', dataSourceId: mes.id, schema: 'mes', table: 'heat', keyColumns: ['heat_no', 'cast_no'] } },
    }]);
  });

  it('deletes only the property binding when its column is cleared', async () => {
    const { api, user, dialog, save } = await openEditor();
    const column = await dialog.findByRole('combobox', { name: '重量' });
    await waitFor(() => expect(column).toHaveValue('weight_t'));
    await user.selectOptions(column, formText('noColumn'));
    await save();

    expect(await submittedItems(api)).toEqual([{
      op: 'delete', kind: 'property_binding', targetElementId: 'bd-weight', targetRevision: 5,
    }]);
  });

  it('deletes the old table, property and both join directions before creating bindings for the replacement table', async () => {
    const { api, user, dialog, save } = await openEditor({ view: heatWithJoins, tables: [currentHeatTable, castTable, archiveTable] });
    await user.click(await dialog.findByRole('option', { name: /mes\.archived_heat/ }));
    const codeColumn = await dialog.findByRole('combobox', { name: '批次号' });
    await within(codeColumn).findByRole('option', { name: /archive_no/ });
    await user.selectOptions(dialog.getByRole('combobox', { name: '重量' }), 'weight_t');

    const incomingGroup = within(await dialog.findByRole('group', { name: incoming.label }));
    await user.selectOptions(incomingGroup.getByRole('combobox', { name: formText('joinKind') }), formText('joinKinds.none'));
    const outgoingGroup = await dialog.findByRole('group', { name: outgoing.label });
    await user.selectOptions(within(outgoingGroup).getByRole('combobox', { name: formText('joinKind') }), formText('joinKinds.none'));
    const join = await chooseForeignKey(user, outgoingGroup, /archived_heat/);
    await checkColumn(user, join.columns, 'cast_no');
    expect(await within(join.references).findByRole('checkbox', { name: 'sequence_no' })).toBeChecked();
    await save();

    const items = await submittedItems(api);
    const deletions = [
      { op: 'delete', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3 },
      { op: 'delete', kind: 'property_binding', targetElementId: 'bd-weight', targetRevision: 5 },
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-in-cast', targetRevision: 7 },
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-first-heat', targetRevision: 9 },
    ];
    expect(items.slice(0, deletions.length)).toEqual(expect.arrayContaining(deletions));
    const created = items.slice(deletions.length);
    const newRef = created.find((item) => item.kind === 'type_binding')?.tempRef;
    expect(newRef).toMatch(/\S/);
    expect(newRef).not.toBe('bd-heat');
    expect(created).toHaveLength(3);
    expect(created).toEqual(expect.arrayContaining([
      {
        op: 'create', kind: 'type_binding', tempRef: newRef,
        fields: { subjectRef: heat.id, binding: { target: 'table', dataSourceId: mes.id, schema: 'mes', table: 'archived_heat', keyColumns: ['archive_no'] } },
      },
      { op: 'create', kind: 'property_binding', fields: { subjectRef: weight.id, parentRef: newRef, binding: { target: 'column', column: 'weight_t' } } },
      { op: 'create', kind: 'relation_binding', fields: {
        subjectRef: inCast.id, domainRef: newRef, rangeRef: 'bd-cast',
        binding: { target: 'join', join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['sequence_no'] } },
      } },
    ]));
  });

  it('confirms the table and dependent counts before unbinding and submits every delete with its revision', async () => {
    const { api, user, dialog } = await openEditor({ view: heatWithJoins });
    await user.click(dialog.getByRole('button', { name: formText('unbind') }));
    const confirmation = within(await screen.findByRole('dialog', { name: formText('unbindConfirm.title') }));
    expect(confirmation.getByText(formText('unbindConfirm.description', {
      table: 'mes.heat', properties: 1, relations: 2,
    }))).toBeVisible();
    // The confirmation says what the editor says: applied at once or sent to review.
    const outcome = [formText('appliesAtOnce'), formText('submitsForReview')].find((text) => dialog.queryByText(text));
    expect(outcome).toBeDefined();
    expect(confirmation.getByText(outcome ?? '')).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await user.click(confirmation.getByRole('button', { name: formText('unbind') }));
    expect(await submittedItems(api)).toEqual([
      { op: 'delete', kind: 'property_binding', targetElementId: 'bd-weight', targetRevision: 5 },
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-in-cast', targetRevision: 7 },
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-first-heat', targetRevision: 9 },
      { op: 'delete', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3 },
    ]);
  });

  it('does not submit when unbinding is cancelled', async () => {
    const { api, user, dialog } = await openEditor({ view: heatWithJoins });
    await user.click(dialog.getByRole('button', { name: formText('unbind') }));
    const confirmation = within(await screen.findByRole('dialog', { name: formText('unbindConfirm.title') }));
    await user.click(confirmation.getByRole('button', { name: i18n.t('common.cancel') }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: formText('unbindConfirm.title') })).not.toBeInTheDocument());
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('closes the confirmation and shows the server problem in the editor when unbinding fails', async () => {
    // Any rejected edit takes this path; the type mismatch is just a problem with a known message.
    const { api, user, dialog } = await openEditor({ view: heatWithJoins, editError: 'binding.type_mismatch' });
    await user.click(dialog.getByRole('button', { name: formText('unbind') }));
    const confirmation = within(await screen.findByRole('dialog', { name: formText('unbindConfirm.title') }));
    await user.click(confirmation.getByRole('button', { name: formText('unbind') }));
    expect(await dialog.findByText(i18n.t('errors.binding.type_mismatch'))).toBeVisible();
    expect(screen.queryByRole('dialog', { name: formText('unbindConfirm.title') })).not.toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(1);
  });

  it('keeps the binding when another editor adds a relation before unbinding', async () => {
    const { api, user, dialog, ontologyElements } = await openEditor({ view: heatWithJoins });
    await user.click(dialog.getByRole('button', { name: formText('unbind') }));
    ontologyElements.push(elementFixture({
      id: 'bd-concurrent-join', kind: 'relation_binding', subjectId: inCast.id,
      domainId: 'bd-heat', rangeId: 'bd-cast',
      binding: { target: 'join', join: { kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['sequence_no'] } },
    }));
    const confirmation = within(await screen.findByRole('dialog', { name: formText('unbindConfirm.title') }));
    await user.click(confirmation.getByRole('button', { name: formText('unbind') }));
    expect(await dialog.findByText(formText('dependenciesChanged'))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('does not offer unbinding for a type without a table binding', async () => {
    const user = userEvent.setup();
    bindingServer({ view: unboundHeat, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const dialog = await openBinder(user);
    expect(dialog.queryByRole('button', { name: formText('unbind') })).not.toBeInTheDocument();
  });

  it('deletes only the type binding when no properties or relations are bound', () => {
    const view: TypeBindingView = { ...editableHeat, properties: [], relations: [] };
    const model = bindingModel(heat, [heat], view, [view], [], []);
    expect(unbindEdits(model)).toEqual([
      { op: 'delete', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3 },
    ]);
  });

  it('keeps the draft when another editor adds a dependent binding before the table is replaced', async () => {
    const { api, user, dialog, ontologyElements, save } = await openEditor({ tables: [currentHeatTable, archiveTable, castTable] });
    await user.click(await dialog.findByRole('option', { name: /mes\.archived_heat/ }));
    expect(await dialog.findByRole('checkbox', { name: 'archive_no' })).toBeChecked();
    ontologyElements.push(elementFixture({
      id: 'bd-concurrent', kind: 'property_binding', parentId: 'bd-heat', subjectId: batchCode.id,
      binding: { target: 'column', column: 'heat_no' },
    }));
    await save();
    expect(await dialog.findByText(formText('dependenciesChanged'))).toBeVisible();
    expect(dialog.getByRole('checkbox', { name: 'archive_no' })).toBeChecked();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it.each([
    { side: 'source', table: /casting_sequence/, column: 'first_heat_no', reference: 'heat_no' },
    { side: 'target', table: /mes\.heat/, column: 'cast_no', reference: 'sequence_no' },
  ])('creates an incoming join with the foreign key on the $side table and the edited type as the range', async ({ side, table, column, reference }) => {
    const { api, user, dialog, save } = await openEditor();
    const relation = await dialog.findByRole('group', { name: incoming.label });
    const { columns, references } = await chooseForeignKey(user, relation, table);
    await checkColumn(user, columns, column);
    expect(await within(references).findByRole('checkbox', { name: reference })).toBeChecked();
    await save();

    expect(await submittedItems(api)).toEqual([{
      op: 'create', kind: 'relation_binding', fields: {
        subjectRef: firstHeat.id, domainRef: 'bd-cast', rangeRef: 'bd-heat',
        binding: { target: 'join', join: { kind: 'foreign_key', side, columns: [column], references: [reference] } },
      },
    }]);
  });

  it('keeps an empty key selection in the dialog and sends no edits', async () => {
    const { api, user, dialog, save } = await openEditor();
    const key = await dialog.findByRole('checkbox', { name: 'heat_no' });
    expect(key).toBeChecked();
    await user.click(key);
    await save();

    expect(await dialog.findByText(formText('errors.keyRequired'))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('requires an active data source and a selected catalog table before saving', async () => {
    const user = userEvent.setup();
    const api = bindingServer({ view: unboundHeat, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const section = await openHeat(user);
    await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.bind') }));
    const dialog = within(await screen.findByRole('dialog', { name: formText('createTitle', { type: '炉次' }) }));
    await user.click(dialog.getByRole('button', { name: formText('save') }));
    expect(await dialog.findByText(formText('errors.dataSourceRequired'))).toBeVisible();
    await user.selectOptions(dialog.getByRole('combobox', { name: formText('dataSource') }), mes.id);
    await dialog.findByRole('option', { name: /mes\.heat/ });
    await user.click(dialog.getByRole('button', { name: formText('save') }));
    expect(await dialog.findByText(formText('errors.tableRequired'))).toBeVisible();
    expect(dialog.getByRole('searchbox', { name: formText('table') }))
      .toHaveAccessibleDescription(`${formText('tableSearch')} ${formText('errors.tableRequired')}`);
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('rejects a foreign key whose two nonempty column lists have different lengths', async () => {
    const { api, user, dialog, save } = await openEditor();
    const relation = await dialog.findByRole('group', { name: outgoing.label });
    const { columns, references } = await chooseForeignKey(user, relation, /casting_sequence/);
    await checkColumn(user, columns, 'first_heat_no');
    await checkColumn(user, columns, 'sequence_no');
    expect(await within(references).findByRole('checkbox', { name: 'heat_no' })).toBeChecked();
    await save();

    expect(await dialog.findByText(formText('errors.columnsMismatch'))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('matches link-table columns to each endpoint key count and saves the columns in selection order', async () => {
    const view = { ...editableHeat, table: { ...boundHeat.table, keyColumns: ['heat_no', 'cast_no'] } };
    const linkTable: CatalogTable = {
      ...heatTable, schema: 'mapping', name: 'heat_cast', comment: null, columnCount: 4, primaryKey: null,
      columns: [
        { name: 'heat_cast_key', type: 'text', family: 'string', nullable: false, comment: null, position: 1 },
        { name: 'heat_key', type: 'text', family: 'string', nullable: false, comment: null, position: 2 },
        { name: 'sequence_key', type: 'text', family: 'string', nullable: false, comment: null, position: 3 },
        { name: 'sequence_line', type: 'text', family: 'string', nullable: false, comment: null, position: 4 },
      ],
    };
    const { api, user, dialog, save } = await openEditor({ view, tables: [currentHeatTable, castTable, linkTable] });
    const relation = within(await dialog.findByRole('group', { name: outgoing.label }));
    await user.selectOptions(relation.getByRole('combobox', { name: formText('joinKind') }), formText('joinKinds.link_table'));
    const picker = await relation.findByRole('listbox', { name: formText('linkTable') });
    await user.click(await within(picker).findByRole('option', { name: /mapping\.heat_cast/ }));
    const source = await relation.findByRole('group', { name: formText('sourceColumns') });
    const target = await relation.findByRole('group', { name: formText('targetColumns') });

    await checkColumn(user, source, 'heat_key');
    await checkColumn(user, target, 'sequence_key');
    await save();
    expect(await relation.findByText(formText('errors.linkColumnsMismatch', { sourceKeys: 2, targetKeys: 1 }))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    await checkColumn(user, source, 'heat_cast_key');
    await checkColumn(user, target, 'sequence_line');
    await save();
    expect(await relation.findByText(formText('errors.linkColumnsMismatch', { sourceKeys: 2, targetKeys: 1 }))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    await user.click(within(target).getByRole('checkbox', { name: 'sequence_line', checked: true }));
    await save();
    expect(await submittedItems(api)).toEqual([{
      op: 'create', kind: 'relation_binding',
      fields: {
        subjectRef: inCast.id, domainRef: 'bd-heat', rangeRef: 'bd-cast',
        binding: { target: 'join', join: {
          kind: 'link_table', schema: 'mapping', table: 'heat_cast',
          sourceColumns: ['heat_key', 'heat_cast_key'], targetColumns: ['sequence_key'],
        } },
      },
    }]);
  });

  it('sends no edit request when the populated binding form is saved unchanged', async () => {
    const { api, dialog, save } = await openEditor({ view: heatWithJoins });
    const column = await dialog.findByRole('combobox', { name: '重量' });
    expect(column).toHaveValue('weight_t');
    const relation = within(await dialog.findByRole('group', { name: incoming.label }));
    const columns = await relation.findByRole('group', { name: formText('columns') });
    expect(await within(columns).findByRole('checkbox', { name: 'first_heat_no' })).toBeChecked();
    expect(dialog.getByRole('button', { name: formText('save') })).toBeEnabled();
    await save();

    await waitFor(() => {
      const stillOpen = screen.queryByRole('dialog', { name: formText('editTitle', { type: '炉次' }) });
      if (stillOpen) expect(within(stillOpen).getByText(i18n.t('ontologyPage.form.nothingChanged'))).toBeVisible();
    });
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('asks for the affected link-table columns again when the replacement table has a different key', async () => {
    const link: CatalogTable = { ...currentHeatTable, name: 'heat_cast' };
    const view: TypeBindingView = {
      ...editableHeat,
      relations: [{ ...outgoing, join: {
        elementId: 'bd-link', revision: 2, check: 'ok',
        join: { kind: 'link_table', schema: link.schema, table: link.name, sourceColumns: ['heat_no'], targetColumns: ['cast_no'] },
      } }],
    };
    const { api, user, dialog, save } = await openEditor({ view, tables: [currentHeatTable, castTable, archiveTable, link] });
    const picker = within(await dialog.findByRole('listbox', { name: formText('table') }));
    await user.click(await picker.findByRole('option', { name: /archived_heat/ }));
    const relation = within(await dialog.findByRole('group', { name: outgoing.label }));
    const source = within(await relation.findByRole('group', { name: formText('sourceColumns') }));
    const target = within(await relation.findByRole('group', { name: formText('targetColumns') }));
    expect(source.getByRole('checkbox', { name: 'heat_no' })).not.toBeChecked();
    expect(target.getByRole('checkbox', { name: 'cast_no' })).toBeChecked();
    await save();
    expect(await relation.findByText(formText('errors.joinColumnsRequired'))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('links to the review list when several binding change sets are open', async () => {
    const user = userEvent.setup();
    bindingServer({ view: { ...boundHeat, openChangeSetIds: ['cs-binding', 'cs-later'] }, user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const section = await openHeat(user);
    const link = await within(section).findByRole('link', { name: i18n.t('bindings.pending.listLink', { count: 2 }) });
    expect(link).toHaveAttribute('href', '/review?ontology=onto-steel');
    expect(within(section).queryByRole('link', { name: i18n.t('bindings.pending.link') })).not.toBeInTheDocument();
  });

  it('names the table search by its visible label and searches only once the typing pauses', async () => {
    const { api, dialog } = await openEditor({ nextCursor: 'page-2' });
    const search = await dialog.findByRole('searchbox', { name: formText('table') });
    expect(search).toHaveAccessibleDescription(formText('tableSearch'));
    const next = await dialog.findByRole('button', { name: i18n.t('pagination.next') });
    expect(next).toBeEnabled();

    for (const value of ['h', 'he', 'hea', 'heat']) fireEvent.change(search, { target: { value } });
    // The cursor on screen belongs to the previous search until the new one is sent.
    expect(next).toBeDisabled();

    const sent = () => api.calls('GET', `/api/data-sources/${mes.id}/catalog/tables`).flatMap((call) => call.query.get('q') ?? []);
    await waitFor(() => expect(sent()).toContain('heat'));
    expect(sent()).toEqual(['heat']);
    await waitFor(() => expect(dialog.getByRole('button', { name: i18n.t('pagination.next') })).toBeEnabled());
  });

  it('keeps the page on screen until the new search is sent, then starts at its first page', async () => {
    const { api, user, dialog } = await openEditor({ nextCursor: 'page-2' });
    await user.click(await dialog.findByRole('button', { name: i18n.t('pagination.next') }));
    await waitFor(() => expect(dialog.queryByRole('option', { name: /mes\.heat/ })).not.toBeInTheDocument());
    expect(await dialog.findByRole('option', { name: /mes\.casting_sequence/ })).toBeInTheDocument();

    fireEvent.change(dialog.getByRole('searchbox', { name: formText('table') }), { target: { value: 'cast' } });
    expect(dialog.queryByRole('option', { name: /mes\.heat/ })).not.toBeInTheDocument();
    expect(dialog.getByRole('button', { name: i18n.t('pagination.previous') })).toBeDisabled();

    const calls = () => api.calls('GET', `/api/data-sources/${mes.id}/catalog/tables`);
    await waitFor(() => expect(calls().some((call) => call.query.get('q') === 'cast')).toBe(true));
    expect(calls().filter((call) => call.query.has('q') && call.query.has('cursor'))).toHaveLength(0);
  });

  it.each([
    ['listed as archived', [{ ...mes, status: 'archived' as const }]],
    ['missing from the list', []],
  ])('says that the bound data source is archived (%s) and offers only the others', async (_case, bound) => {
    const view: TypeBindingView = {
      ...editableHeat,
      table: { ...boundHeat.table, dataSource: { id: mes.id, name: mes.name, status: 'archived' } },
    };
    const { dialog } = await openEditor({ view, sources: [...bound, { ...mes, id: 'ds-lims', name: 'LIMS' }] });

    expect(await dialog.findByText(formText('sourceArchived.title'))).toBeVisible();
    expect(dialog.getByText(formText('sourceArchived.description', { name: mes.name }))).toBeVisible();
    const select = dialog.getByRole('combobox', { name: formText('dataSource') });
    expect(select).toHaveValue('');
    expect(within(select).getByRole('option', { name: 'LIMS' })).toBeInTheDocument();
    expect(within(select).queryByRole('option', { name: mes.name })).not.toBeInTheDocument();
  });

  it('follows the changes the data page makes to the data sources while the dialog is open', async () => {
    const sources = [mes];
    const { api, dialog, queryClient, save } = await openEditor({ sources });
    const select = await dialog.findByRole('combobox', { name: formText('dataSource') });
    expect(select).toHaveValue(mes.id);
    expect(dialog.queryByText(formText('sourceArchived.title'))).not.toBeInTheDocument();

    const archived: DataSource = { ...mes, status: 'archived', revision: 2 };
    sources[0] = archived;
    await act(() => rememberSource(queryClient, archived));

    expect(await dialog.findByText(formText('sourceArchived.title'))).toBeVisible();
    expect(within(select).queryByRole('option', { name: mes.name })).not.toBeInTheDocument();
    // Saving still answers, by asking for another source.
    await save();
    expect(await dialog.findByText(formText('errors.dataSourceRequired'))).toBeVisible();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('chooses the bound data source from a fresh list, not from an outdated cached one', async () => {
    const user = userEvent.setup();
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    const api = bindingServer({
      view: editableHeat, tables: [currentHeatTable], user: userWithRole('editor'),
      sourceList: async () => { await held; return [mes]; },
    });
    const { queryClient } = renderApp('/ontology?ontology=onto-steel&view=list');
    queryClient.setQueryData(listKey, []);

    const section = await openHeat(user);
    await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.edit') }));
    // Everything else the dialog reads has arrived; only the data source list is still on its way.
    await waitFor(() => {
      expect(api.calls('GET', '/api/data-sources')).toHaveLength(1);
      expect(queryClient.isFetching()).toBe(1);
    });
    await act(() => new Promise<void>((resolve) => { setTimeout(resolve, 20); }));
    expect(screen.queryByRole('combobox', { name: formText('dataSource') })).not.toBeInTheDocument();

    release();
    expect(await screen.findByRole('combobox', { name: formText('dataSource') })).toHaveValue(mes.id);
  });

  it('asks to retry a failed data source refresh instead of choosing from the cached list', async () => {
    const user = userEvent.setup();
    let failing = true;
    bindingServer({
      view: editableHeat, tables: [currentHeatTable], user: userWithRole('editor'),
      sourceList: () => (failing ? problemResponse(409, 'test.failed') : [mes]),
    });
    const { queryClient } = renderApp('/ontology?ontology=onto-steel&view=list');
    queryClient.setQueryData(listKey, []);

    const section = await openHeat(user);
    await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.edit') }));
    const dialog = within(await screen.findByRole('dialog', { name: formText('editTitle', { type: '炉次' }) }));
    const retry = await dialog.findByRole('button', { name: i18n.t('common.retry') });
    expect(dialog.queryByRole('combobox', { name: formText('dataSource') })).not.toBeInTheDocument();

    failing = false;
    await user.click(retry);
    expect(await dialog.findByRole('combobox', { name: formText('dataSource') })).toHaveValue(mes.id);
  });

  it('keeps the form and its draft when a later data source refresh fails', async () => {
    let failing = false;
    const { user, dialog, queryClient } = await openEditor({
      sourceList: () => (failing ? problemResponse(409, 'test.failed') : [mes]),
    });
    // Queried afresh each time: a removed form would keep its old checkbox state.
    const draft = () => within(dialog.getByRole('group', { name: formText('keyColumns') })).getByRole('checkbox', { name: 'cast_no' });
    await dialog.findByRole('group', { name: formText('keyColumns') });
    await user.click(draft());

    failing = true;
    await act(() => queryClient.invalidateQueries({ queryKey: listKey }));

    expect(await dialog.findByRole('button', { name: i18n.t('common.retry') })).toBeVisible();
    expect(draft()).toBeChecked();
  });

  it('updates only the relation binding, with the revision it saw, when the table stays and a join changes', async () => {
    const { api, user, dialog, save } = await openEditor({ view: heatWithJoins });
    const relation = within(await dialog.findByRole('group', { name: outgoing.label }));
    const references = await relation.findByRole('group', { name: formText('references') });
    await user.click(await within(references).findByRole('checkbox', { name: 'sequence_no', checked: true }));
    await checkColumn(user, references, 'first_heat_no');
    await save();

    expect(await submittedItems(api)).toEqual([{
      op: 'update', kind: 'relation_binding', targetElementId: 'bd-in-cast', targetRevision: 7,
      fields: { binding: { target: 'join', join: {
        kind: 'foreign_key', side: 'source', columns: ['cast_no'], references: ['first_heat_no'],
      } } },
    }]);
  });

  it('creates a self-relation join with the new table at both ends', async () => {
    const user = userEvent.setup();
    const view: TypeBindingView = { ...unboundHeat, relations: [selfOut, selfIn] };
    const api = bindingServer({
      view, tables: [currentHeatTable], ontologyElements: [...elements, nextHeat], user: userWithRole('editor'),
    });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const dialog = await openBinder(user);
    await user.selectOptions(await dialog.findByRole('combobox', { name: formText('dataSource') }), mes.id);
    await user.click(await dialog.findByRole('option', { name: /mes\.heat/ }));

    // One editor for the pair, although the relation is listed in both directions.
    expect(await dialog.findAllByRole('group', { name: '下一炉' })).toHaveLength(1);
    const relation = within(dialog.getByRole('group', { name: '下一炉' }));
    await user.selectOptions(relation.getByRole('combobox', { name: formText('joinKind') }), formText('joinKinds.foreign_key'));
    const columns = await relation.findByRole('group', { name: formText('columns') });
    const references = relation.getByRole('group', { name: formText('references') });
    expect(within(references).getByRole('checkbox', { name: 'heat_no' })).toBeChecked();
    await checkColumn(user, columns, 'cast_no');
    await user.click(dialog.getByRole('button', { name: formText('save') }));

    const items = await submittedItems(api);
    const newRef = items[0]?.tempRef;
    expect(newRef).toMatch(/\S/);
    expect(items).toEqual([
      expect.objectContaining({ op: 'create', kind: 'type_binding', tempRef: newRef }),
      { op: 'create', kind: 'relation_binding', fields: {
        subjectRef: nextHeat.id, domainRef: newRef, rangeRef: newRef, binding: { target: 'join', join: selfJoin.join },
      } },
    ]);
  });

  it('rebuilds a self-relation join on both ends of the replacement table', async () => {
    const replacement: CatalogTable = { ...currentHeatTable, name: 'heat_v2' };
    const { api, user, dialog, save } = await openEditor({
      view: heatWithSelfJoin, tables: [currentHeatTable, castTable, replacement], extraElements: [nextHeat],
    });
    await user.click(await dialog.findByRole('option', { name: /mes\.heat_v2/ }));
    const relation = within(await dialog.findByRole('group', { name: '下一炉' }));
    expect(relation.getByRole('combobox', { name: formText('joinKind') })).toHaveValue('foreign_key');
    await save();

    const items = await submittedItems(api);
    const newRef = items.find((item) => item.op === 'create' && item.kind === 'type_binding')?.tempRef;
    expect(newRef).toMatch(/\S/);
    expect(items).toHaveLength(6);
    expect(items).toEqual(expect.arrayContaining([
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-next', targetRevision: 4 },
      { op: 'delete', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3 },
      { op: 'create', kind: 'relation_binding', fields: {
        subjectRef: nextHeat.id, domainRef: newRef, rangeRef: newRef, binding: { target: 'join', join: selfJoin.join },
      } },
    ]));
  });

  it('drops a self-relation join when the replacement table lacks one of its columns', async () => {
    // archived_heat still has the foreign key column cast_no, but no heat_no for it to refer to.
    const { api, user, dialog, save } = await openEditor({
      view: heatWithSelfJoin, tables: [currentHeatTable, castTable, archiveTable], extraElements: [nextHeat],
    });
    await user.click(await dialog.findByRole('option', { name: /mes\.archived_heat/ }));
    const relation = within(await dialog.findByRole('group', { name: '下一炉' }));
    expect(relation.getByRole('combobox', { name: formText('joinKind') })).toHaveValue('none');
    await save();

    const items = await submittedItems(api);
    expect(items.filter((item) => item.kind === 'relation_binding')).toEqual([
      { op: 'delete', kind: 'relation_binding', targetElementId: 'bd-next', targetRevision: 4 },
    ]);
  });

  it('clears the link-table columns of the edited end when its key changes, until they are chosen again', async () => {
    const link: CatalogTable = {
      ...heatTable, schema: 'mapping', name: 'heat_cast', comment: null, columnCount: 3, primaryKey: null,
      columns: ['heat_key', 'heat_part', 'sequence_key'].map((name, index) => (
        { name, type: 'text', family: 'string', nullable: false, comment: null, position: index + 1 }
      )),
    };
    const linked = (sourceColumns: string[], targetColumns: string[]) => (
      { kind: 'link_table' as const, schema: link.schema, table: link.name, sourceColumns, targetColumns }
    );
    const view: TypeBindingView = {
      ...editableHeat,
      relations: [
        { ...outgoing, join: { elementId: 'bd-link-out', revision: 2, check: 'ok', join: linked(['heat_key'], ['sequence_key']) } },
        { ...incoming, join: { elementId: 'bd-link-in', revision: 6, check: 'ok', join: linked(['sequence_key'], ['heat_key']) } },
      ],
    };
    const { api, user, dialog, save } = await openEditor({ view, tables: [currentHeatTable, castTable, link] });
    const columnsOf = async (relation: string, group: 'sourceColumns' | 'targetColumns') => (
      within(await dialog.findByRole('group', { name: relation })).findByRole('group', { name: formText(group) })
    );
    const outSource = await columnsOf(outgoing.label, 'sourceColumns');
    const outTarget = await columnsOf(outgoing.label, 'targetColumns');
    const inSource = await columnsOf(incoming.label, 'sourceColumns');
    const inTarget = await columnsOf(incoming.label, 'targetColumns');
    expect(within(outSource).getByRole('checkbox', { name: 'heat_key' })).toBeChecked();

    const keys = dialog.getByRole('group', { name: formText('keyColumns') });
    await user.click(within(keys).getByRole('checkbox', { name: 'cast_no' }));

    // The edited type is the source of one relation and the target of the other.
    expect(within(outSource).queryByRole('checkbox', { checked: true })).not.toBeInTheDocument();
    expect(within(outTarget).getByRole('checkbox', { name: 'sequence_key' })).toBeChecked();
    expect(within(inSource).getByRole('checkbox', { name: 'sequence_key' })).toBeChecked();
    expect(within(inTarget).queryByRole('checkbox', { checked: true })).not.toBeInTheDocument();
    await save();
    expect(await dialog.findAllByText(formText('errors.joinColumnsRequired'))).toHaveLength(2);
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    for (const group of [outSource, inTarget]) {
      await checkColumn(user, group, 'heat_key');
      await checkColumn(user, group, 'heat_part');
    }
    await save();
    const items = await submittedItems(api);
    expect(items).toHaveLength(3);
    expect(items).toEqual(expect.arrayContaining([
      expect.objectContaining({ op: 'update', kind: 'type_binding', targetElementId: 'bd-heat', targetRevision: 3 }),
      { op: 'update', kind: 'relation_binding', targetElementId: 'bd-link-out', targetRevision: 2,
        fields: { binding: { target: 'join', join: linked(['heat_key', 'heat_part'], ['sequence_key']) } } },
      { op: 'update', kind: 'relation_binding', targetElementId: 'bd-link-in', targetRevision: 6,
        fields: { binding: { target: 'join', join: linked(['sequence_key'], ['heat_key', 'heat_part']) } } },
    ]));
  });

  it('shows the localized type mismatch inside the edit dialog when the server rejects a property binding', async () => {
    const { api, user, dialog, save } = await openEditor({ editError: 'binding.type_mismatch' });
    const column = await dialog.findByRole('combobox', { name: '批次号' });
    await within(column).findByRole('option', { name: /heat_no/ });
    await user.selectOptions(column, 'heat_no');
    await save();

    expect(await dialog.findByText(i18n.t('errors.binding.type_mismatch'))).toBeVisible();
    expect(await submittedItems(api)).toEqual([{
      op: 'create', kind: 'property_binding',
      fields: { subjectRef: batchCode.id, parentRef: 'bd-heat', binding: { target: 'column', column: 'heat_no' } },
    }]);
  });
});
