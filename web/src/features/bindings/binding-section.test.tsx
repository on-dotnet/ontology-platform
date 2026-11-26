import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import type { EditRequest, Element } from '@/features/ontologies/api';
import i18n from '@/i18n';
import { elementDetailFixture, elementFixture, impactFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole } from '@/test/utils';

import type { CatalogTable, DataSource, RelationBindingView, TypeBindingView } from './api';

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

interface BindingServerOptions {
  view: TypeBindingView;
  user?: UserInfo;
  ontologyElements?: Element[];
  otherViews?: TypeBindingView[];
  tables?: CatalogTable[];
  editError?: string;
}

function bindingServer({ view, user, ontologyElements = elements, otherViews = [], tables = [heatTable], editError }: BindingServerOptions) {
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
      'GET /api/data-sources': () => [mes],
      'GET /api/data-sources/:id/catalog/tables': ({ query }) => ({
        items: tables
          .filter((table) => table.name.includes(query.get('q')?.toLowerCase() ?? ''))
          .map(({ schema, name, kind, comment, columnCount, boundType }) => ({ schema, name, kind, comment, columnCount, boundType })),
        nextCursor: null,
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
  view = editableHeat, tables = [currentHeatTable, castTable], editError,
}: Partial<Pick<BindingServerOptions, 'view' | 'tables' | 'editError'>> = {}) {
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
  const ontologyElements = [...elements, firstHeat];
  const api = bindingServer({ view, tables, editError, user: userWithRole('editor'), ontologyElements, otherViews: [other] });
  renderApp('/ontology?ontology=onto-steel&view=list');
  const section = await openHeat(user);
  await user.click(await within(section).findByRole('button', { name: i18n.t('bindings.edit') }));
  const dialog = within(await screen.findByRole('dialog', { name: formText('editTitle', { type: '炉次' }) }));
  return { api, user, dialog, ontologyElements, save: () => user.click(dialog.getByRole('button', { name: formText('save') })) };
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

    expect(within(section).getByText('外键 cast_no → cast_no')).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: '目录里找不到这一列，可能已被改名' })).toBeInTheDocument();

    expect(within(section).getByText('有待审核的绑定修改')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-binding');
    expect(within(section).getByRole('button', { name: '编辑绑定' })).toBeInTheDocument();
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
    await user.type(dialog.getByRole('searchbox', { name: formText('tableSearch') }), 'heat{Enter}');
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
