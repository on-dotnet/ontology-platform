import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import type { EditRequest, Element } from '@/features/ontologies/api';
import { axiomFixture, elementDetailFixture, elementFixture, elementRefFixture, impactFixture, mergeEdits, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

const EDITS = '/api/ontologies/onto-steel/edits';

const moltenSteel = elementFixture({ revision: 3, synonyms: [{ lang: 'zh', text: '铁水' }] });
const ladle = elementFixture({ id: 'el-ladle', localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装钢水的容器。' });
const refined = elementFixture({
  id: 'el-refined',
  localName: 'RefinedSteel',
  labelZh: '精炼钢',
  labelEn: 'Refined steel',
  definitionZh: null,
  parentId: 'el-molten-steel',
});
const holds = elementFixture({
  id: 'el-holds',
  kind: 'relation_type',
  localName: 'holds',
  labelZh: '盛装',
  labelEn: 'holds',
  definitionZh: null,
  domainId: 'el-ladle',
  rangeId: 'el-molten-steel',
});
const temperature = elementFixture({
  id: 'el-temperature',
  kind: 'property',
  localName: 'temperature',
  labelZh: '温度',
  labelEn: 'Temperature',
  definitionZh: '钢水的温度。',
  domainId: 'el-molten-steel',
  datatype: 'decimal',
  unit: '℃',
});
// Imported: its IRI came with the file.
const steelShape = elementFixture({
  id: 'el-shape',
  kind: 'constraint',
  localName: 'MoltenSteelShape',
  iri: 'urn:metals:MoltenSteelShape',
  explicitIri: true,
  labelZh: '钢水校验',
  labelEn: null,
  definitionZh: null,
  domainId: 'el-molten-steel',
  rules: [
    {
      pathId: 'el-temperature',
      minCount: 1,
      minInclusive: { iri: null, lexical: '1580.0', datatype: 'decimal', lang: null },
      allowedValuesLost: false,
      message: [{ lang: 'zh', text: '钢水温度不得低于 1580℃' }],
    },
  ],
  origin: 'import',
});
// Targets the ladle; one of its rules requires molten steel, the other does not.
const ladleShape = elementFixture({
  id: 'el-ladle-shape',
  kind: 'constraint',
  localName: 'LadleShape',
  labelZh: '钢包校验',
  labelEn: null,
  definitionZh: null,
  domainId: 'el-ladle',
  rules: [
    { pathId: 'el-holds', classId: 'el-molten-steel', minCount: 1, allowedValuesLost: false },
    { pathId: 'el-holds', maxCount: 3, allowedValuesLost: false },
  ],
});
const disjoint = axiomFixture();
const heldBy = elementFixture({
  id: 'el-held-by',
  kind: 'relation_type',
  localName: 'heldBy',
  iri: 'urn:metals:heldBy',
  explicitIri: true,
  labelZh: null,
  labelEn: 'held by',
  definitionZh: null,
  inverseId: 'el-holds',
  origin: 'import',
});
const slab = elementFixture({
  id: 'el-slab',
  localName: 'Slab',
  iri: 'urn:metals:Slab',
  explicitIri: true,
  labelZh: null,
  labelEn: null,
  definitionZh: null,
  status: 'deprecated',
  revision: 2,
  origin: 'import',
});

function initialElements(): Element[] {
  return [moltenSteel, ladle, refined, holds, temperature, steelShape, ladleShape, disjoint, heldBy, slab];
}

const moltenSteelImpact = impactFixture('el-molten-steel', {
  subtypes: [elementRefFixture(refined)],
  relations: [elementRefFixture(holds)],
  properties: [elementRefFixture(temperature)],
  constraints: [elementRefFixture(steelShape), elementRefFixture(ladleShape)],
  axioms: [elementRefFixture(disjoint)],
  // The server's full cascade: `held by` does not refer to molten steel, but loses its inverse
  // because `holds` goes; the steel shape is deleted, the ladle shape only loses a rule.
  cascade: [
    { op: 'delete', element: elementRefFixture(holds) },
    { op: 'delete', element: elementRefFixture(temperature) },
    { op: 'delete', element: elementRefFixture(steelShape) },
    { op: 'delete', element: elementRefFixture(disjoint) },
    { op: 'update', element: elementRefFixture(ladleShape) },
    { op: 'update', element: elementRefFixture(refined) },
    { op: 'update', element: elementRefFixture(heldBy) },
  ],
});

interface ServerOptions {
  user?: UserInfo;
  reviewMode?: 'single' | 'separate';
  /** Elements the server holds; tests may replace entries to simulate someone else's change. */
  elements?: Element[];
  edits?: RouteHandler;
}

function editingServer({ user, reviewMode = 'single', elements = initialElements(), edits }: ServerOptions = {}) {
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/settings/platform': () => ({ reviewMode }),
      'GET /api/ontologies/:id/elements': ({ query }) => {
        const kind = query.get('kind');
        const status = query.get('status') ?? 'active';
        return elements.filter((element) => (!kind || element.kind === kind) && (status === 'all' || element.status === status));
      },
      'GET /api/ontologies/:id/elements/:elementId': ({ params }) => {
        const element = elements.find((item) => item.id === params.elementId);
        return element ? elementDetailFixture(element) : problemResponse(404, 'element.not_found');
      },
      'GET /api/ontologies/:id/elements/:elementId/impact': ({ params }) =>
        params.elementId === 'el-molten-steel' ? moltenSteelImpact : impactFixture(params.elementId ?? ''),
      'POST /api/ontologies/:id/edits':
        edits ??
        (({ body }) => {
          const request = body as EditRequest;
          // Merged at once, as the server does: the targets move to their next revision.
          if (request.apply) mergeEdits(elements, request);
          return { changeSetId: 'cs-manual', merged: request.apply, merge: request.apply ? { applied: 1, skipped: [] } : null };
        }),
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
    },
    { user },
  );
}

async function openElement(user: ReturnType<typeof userEvent.setup>, name: string) {
  const table = await screen.findByRole('table', { name: '本体元素' });
  await user.click(within(table).getByRole('button', { name }));
  return screen.findByRole('dialog', { name });
}

async function openCreateForm(user: ReturnType<typeof userEvent.setup>, kind: string, title: string) {
  await user.click(await screen.findByRole('button', { name: '新建' }));
  await user.click(await screen.findByRole('menuitem', { name: kind }));
  return screen.findByRole('dialog', { name: title });
}

const hotShare = elementFixture({
  id: 'el-hot-share', kind: 'metric', localName: 'hotShare', labelZh: '高温占比', labelEn: 'Hot share',
  subjectId: moltenSteel.id, unit: '%', revision: 4,
  metric: {
    aggregate: 'ratio', propertyId: null, filters: [{ propertyId: temperature.id, op: 'notNull' }],
    numerator: [{ propertyId: temperature.id, op: 'ge', value: '1580' }], decimals: 3, percent: true,
  },
});

describe('manual metric elements', () => {
  it('creates a ratio from subject properties and requires a numerator before submitting for review', async () => {
    const user = userEvent.setup();
    const api = editingServer({ reviewMode: 'separate' });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const form = within(await openCreateForm(user, '指标', '新建指标'));
    await user.type(form.getByRole('textbox', { name: '中文名称' }), '高温占比');
    await user.type(form.getByRole('textbox', { name: '英文名称' }), 'Hot share');
    await user.selectOptions(form.getByRole('combobox', { name: '主体类型' }), moltenSteel.id);
    await user.selectOptions(form.getByRole('combobox', { name: '聚合方式' }), 'ratio');
    await user.click(form.getByRole('button', { name: '提交审核' }));
    expect(form.getByText('请至少添加一个分子条件。')).toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    const filter = within(form.getByRole('group', { name: '总体筛选' }));
    await user.click(filter.getByRole('button', { name: '添加筛选' }));
    await user.selectOptions(filter.getByRole('combobox', { name: '选择运算符' }), 'notNull');
    await user.click(filter.getByRole('button', { name: '应用筛选' }));
    const numerator = within(form.getByRole('group', { name: '分子条件' }));
    await user.click(numerator.getByRole('button', { name: '添加筛选' }));
    await user.selectOptions(numerator.getByRole('combobox', { name: '选择运算符' }), 'ge');
    await user.type(numerator.getByRole('textbox', { name: '筛选值' }), '1580');
    await user.click(numerator.getByRole('button', { name: '应用筛选' }));
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await user.click(filter.getByRole('button', { name: '添加筛选' }));
    await user.click(form.getByRole('button', { name: '提交审核' }));
    expect(form.getByText('请先应用或取消正在填写的筛选条件。')).toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await user.click(filter.getByRole('button', { name: '取消' }));
    await user.click(form.getByRole('checkbox', { name: '显示为百分数' }));
    await user.type(form.getByRole('textbox', { name: '单位' }), '%');
    await user.click(form.getByRole('button', { name: '提交审核' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      apply: false, items: [{ op: 'create', kind: 'metric', tempRef: 'new:1', fields: {
        labelZh: '高温占比', labelEn: 'Hot share', localName: 'hotShare', definitionZh: null, definitionEn: null,
        unit: '%', subjectRef: moltenSteel.id, metric: {
          aggregate: 'ratio', propertyRef: null, decimals: 2, percent: true,
          filters: [{ propertyRef: temperature.id, op: 'notNull' }],
          numerator: [{ propertyRef: temperature.id, op: 'ge', value: '1580' }],
        },
      } }],
    });
  });

  it('filters the list by metric, displays its definition and edits stored references as a revision-checked proposal', async () => {
    const user = userEvent.setup();
    const date = elementFixture({ id: 'el-date', kind: 'property', datatype: 'date', domainId: moltenSteel.id, labelZh: '生产日期' });
    const grade = elementFixture({ id: 'el-grade', kind: 'property', datatype: 'string', domainId: moltenSteel.id, labelZh: '钢种' });
    const capacity = elementFixture({ id: 'el-capacity', kind: 'property', datatype: 'integer', domainId: ladle.id, labelZh: '容量' });
    const api = editingServer({ reviewMode: 'separate', elements: [...initialElements(), date, grade, capacity, hotShare] });
    renderApp('/ontology?ontology=onto-steel&view=list');
    await user.click(await screen.findByRole('radio', { name: '指标' }));
    const table = within(await screen.findByRole('table', { name: '本体元素' }));
    await waitFor(() => expect(table.getAllByRole('row')).toHaveLength(2));
    expect(api.requests.some((request) => request.query.get('kind') === 'metric')).toBe(true);
    const sheet = within(await openElement(user, '高温占比'));
    expect(await sheet.findByText('温度 大于或等于 1580')).toBeInTheDocument();
    expect(sheet.getByText('温度 不为空')).toBeInTheDocument();
    expect(sheet.getByText('钢水')).toBeInTheDocument();
    await user.click(sheet.getByRole('button', { name: '编辑' }));
    const form = within(await screen.findByRole('dialog', { name: '编辑“高温占比”' }));
    const aggregate = await form.findByRole('combobox', { name: '聚合方式' });
    expect(aggregate).toHaveValue('ratio');
    expect(form.getByRole('checkbox', { name: '显示为百分数' })).toBeChecked();
    await user.selectOptions(aggregate, 'min');
    const property = form.getByRole('combobox', { name: '聚合属性' });
    expect(within(property).getByRole('option', { name: '生产日期' })).toBeInTheDocument();
    await user.selectOptions(aggregate, 'sum');
    for (const name of ['生产日期', '钢种', '容量']) {
      expect(within(property).queryByRole('option', { name })).not.toBeInTheDocument();
    }
    await user.selectOptions(property, temperature.id);
    await user.click(form.getByRole('button', { name: '提交审核' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      apply: false, items: [{ op: 'update', kind: 'metric', targetElementId: hotShare.id, targetRevision: 4, fields: {
        metric: { aggregate: 'sum', propertyRef: temperature.id, filters: [{ propertyRef: temperature.id, op: 'notNull' }],
          numerator: [], decimals: 3, percent: false },
      } }],
    });
  });

  it('submits a confirmed metric deletion for review', async () => {
    const user = userEvent.setup();
    const api = editingServer({ reviewMode: 'separate', elements: [...initialElements(), hotShare] });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const sheet = within(await openElement(user, '高温占比'));
    await user.click(sheet.getByRole('button', { name: '删除' }));
    const confirm = within(await screen.findByRole('dialog', { name: '删除“高温占比”？' }));
    await confirm.findByText('没有其他元素引用它，只删除它本身。');
    await user.click(confirm.getByRole('button', { name: '提交审核' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      apply: false, items: [{ op: 'delete', kind: 'metric', targetElementId: hotShare.id, targetRevision: 4 }],
    });
  });

  it('requires replacement of filters from the old subject before proposing a subject change', async () => {
    const user = userEvent.setup();
    const capacity = elementFixture({ id: 'el-capacity', kind: 'property', labelZh: '容量', domainId: ladle.id, datatype: 'integer' });
    const api = editingServer({ reviewMode: 'separate', elements: [...initialElements(), hotShare, capacity] });
    renderApp('/ontology?ontology=onto-steel&view=list');
    const sheet = within(await openElement(user, '高温占比'));
    await user.click(sheet.getByRole('button', { name: '编辑' }));
    const form = within(await screen.findByRole('dialog', { name: '编辑“高温占比”' }));
    await user.selectOptions(await form.findByRole('combobox', { name: '主体类型' }), ladle.id);
    const submit = form.getByRole('button', { name: '提交审核' });
    await user.click(submit);
    const filters = within(form.getByRole('group', { name: '总体筛选' }));
    const numerator = within(form.getByRole('group', { name: '分子条件' }));
    for (const group of [filters, numerator]) {
      expect(group.getByText('部分条件不适用于当前主体，请移除后重新选择。')).toBeInTheDocument();
      await user.click(group.getByRole('button', { name: /移除筛选：温度/ }));
    }
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await user.click(numerator.getByRole('button', { name: '添加筛选' }));
    const property = numerator.getByRole('combobox', { name: '选择属性' });
    expect(property).toHaveValue(capacity.id);
    expect(within(property).queryByRole('option', { name: '温度' })).not.toBeInTheDocument();
    await user.selectOptions(numerator.getByRole('combobox', { name: '选择运算符' }), 'notNull');
    await user.click(numerator.getByRole('button', { name: '应用筛选' }));
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    await user.click(submit);
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toMatchObject({
      items: [{ fields: { subjectRef: ladle.id, metric: { filters: [], numerator: [{ propertyRef: capacity.id, op: 'notNull' }] } } }],
    });
  });
});

describe('creating elements by hand', () => {
  it('validates on blur and on save, suggests the local name and saves at once for a reviewer in single mode', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '对象类型', '新建对象类型');
    const save = await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByText('保存后立即生效。')).toBeInTheDocument();

    const labelZh = within(dialog).getByRole('textbox', { name: '中文名称' });
    await user.click(labelZh);
    await user.tab();
    expect(within(dialog).getByText('请输入中文名称')).toBeInTheDocument();

    await user.type(within(dialog).getByRole('textbox', { name: '英文名称' }), 'Steel slab');
    expect(within(dialog).getByRole('textbox', { name: '局部名' })).toHaveValue('SteelSlab');

    await user.click(save);
    expect(within(dialog).getByText('有 1 处需要修改，请按提示修正后再保存。')).toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    await user.type(labelZh, '钢坯');
    await user.type(within(dialog).getByRole('textbox', { name: '中文同义词' }), '板坯、扁坯');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '父类型' }), '钢水');
    await user.click(save);

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [
        {
          op: 'create',
          kind: 'entity_type',
          tempRef: 'new:1',
          fields: {
            localName: 'SteelSlab',
            labelZh: '钢坯',
            labelEn: 'Steel slab',
            definitionZh: null,
            definitionEn: null,
            synonyms: [
              { lang: 'zh', text: '板坯' },
              { lang: 'zh', text: '扁坯' },
            ],
            parentRef: 'el-molten-steel',
          },
        },
      ],
      apply: true,
    });
    expect(await screen.findByText('已保存')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建对象类型' })).not.toBeInTheDocument());
  });

  it('suggests camelCase for properties until the user types a local name of their own', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '属性', '新建属性');
    const save = await within(dialog).findByRole('button', { name: '保存' });
    const labelEn = within(dialog).getByRole('textbox', { name: '英文名称' });
    const localName = within(dialog).getByRole('textbox', { name: '局部名' });

    await user.type(labelEn, 'Slab thickness');
    expect(localName).toHaveValue('slabThickness');

    await user.clear(localName);
    await user.type(localName, 'Thickness');
    await user.tab();
    expect(within(dialog).getByText('局部名需以小写字母开头，只含字母和数字，例如 producedBy')).toBeInTheDocument();

    await user.clear(localName);
    await user.type(localName, 'thickness');
    await user.type(labelEn, ' value');
    expect(localName).toHaveValue('thickness');

    await user.type(within(dialog).getByRole('textbox', { name: '中文名称' }), '厚度');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '所属对象类型' }), '钢包');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '数据类型' }), '小数');
    await user.type(within(dialog).getByRole('textbox', { name: '单位' }), 'mm');
    await user.click(within(dialog).getByRole('checkbox', { name: '必填' }));
    await user.click(save);

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [
        {
          op: 'create',
          kind: 'property',
          tempRef: 'new:1',
          fields: {
            localName: 'thickness',
            labelZh: '厚度',
            labelEn: 'Slab thickness value',
            definitionZh: null,
            definitionEn: null,
            synonyms: [],
            domainRef: 'el-ladle',
            datatype: 'decimal',
            unit: 'mm',
            required: true,
            multiple: false,
          },
        },
      ],
      apply: true,
    });
  });

  it('creates a constraint with rules edited in the form', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '约束', '新建约束');
    const save = await within(dialog).findByRole('button', { name: '保存' });
    await user.type(within(dialog).getByRole('textbox', { name: '中文名称' }), '钢包温度校验');
    await user.type(within(dialog).getByRole('textbox', { name: '英文名称' }), 'Ladle temperature check');
    expect(within(dialog).getByRole('textbox', { name: '局部名' })).toHaveValue('LadleTemperatureCheck');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '目标类型' }), '钢包');

    const first = within(dialog).getByRole('region', { name: '规则 1' });
    await user.selectOptions(within(first).getByRole('combobox', { name: '属性或关系' }), '温度');
    await user.type(within(first).getByRole('textbox', { name: '最少个数' }), '1');
    await user.type(within(first).getByRole('textbox', { name: '最小值' }), '1500');
    await user.type(within(first).getByRole('textbox', { name: '最大值' }), '1700');
    await user.selectOptions(within(first).getByRole('combobox', { name: '最大值是否包含本身' }), '不含');
    await user.type(within(first).getByRole('textbox', { name: '中文提示信息' }), '温度超出范围');

    await user.click(within(dialog).getByRole('button', { name: '添加规则' }));
    const second = within(dialog).getByRole('region', { name: '规则 2' });
    await user.selectOptions(within(second).getByRole('combobox', { name: '属性或关系' }), '盛装');
    const maxCount = within(second).getByRole('textbox', { name: '最多个数' });
    await user.type(maxCount, 'x');
    await user.tab();
    expect(within(second).getByText('请输入 0 或正整数')).toBeInTheDocument();
    await user.clear(maxCount);
    await user.type(maxCount, '1');

    await user.click(within(dialog).getByRole('button', { name: '添加规则' }));
    await user.click(within(within(dialog).getByRole('region', { name: '规则 3' })).getByRole('button', { name: '删除规则 3' }));
    expect(within(dialog).queryByRole('region', { name: '规则 3' })).not.toBeInTheDocument();

    await user.click(save);
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    const empty = {
      classRef: null,
      minCount: null,
      maxCount: null,
      datatype: null,
      nodeKind: null,
      allowedValues: null,
      allowedValuesLost: false,
      minInclusive: null,
      maxInclusive: null,
      minExclusive: null,
      maxExclusive: null,
      minLength: null,
      maxLength: null,
      pattern: null,
      flags: null,
      message: [],
    };
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [
        {
          op: 'create',
          kind: 'constraint',
          tempRef: 'new:1',
          fields: {
            localName: 'LadleTemperatureCheck',
            labelZh: '钢包温度校验',
            labelEn: 'Ladle temperature check',
            definitionZh: null,
            definitionEn: null,
            domainRef: 'el-ladle',
            rules: [
              {
                ...empty,
                pathRef: 'el-temperature',
                minCount: 1,
                // Typed like the property the rule constrains.
                minInclusive: { iri: null, lexical: '1500', datatype: 'decimal', lang: null },
                maxExclusive: { iri: null, lexical: '1700', datatype: 'decimal', lang: null },
                message: [{ lang: 'zh', text: '温度超出范围' }],
              },
              { ...empty, pathRef: 'el-holds', maxCount: 1 },
            ],
          },
        },
      ],
      apply: true,
    });
  });

  it('submits for review when the user may not apply their own edits, and links to the change set', async () => {
    const user = userEvent.setup();
    const api = editingServer({ user: userWithRole('editor') });
    const { router } = renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '对象类型', '新建对象类型');
    const submit = await within(dialog).findByRole('button', { name: '提交审核' });
    expect(within(dialog).getByText('保存后生成变更集，审核通过后才会生效。')).toBeInTheDocument();
    await user.type(within(dialog).getByRole('textbox', { name: '中文名称' }), '钢坯');
    await user.type(within(dialog).getByRole('textbox', { name: '英文名称' }), 'Slab');
    await user.click(submit);

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toMatchObject({ apply: false });
    expect(await screen.findByText('已提交审核，审核通过后生效')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: '去审核' });
    expect(link).toHaveAttribute('href', '/review/cs-manual');
    await user.click(link);
    await waitFor(() => expect(router.state.location.pathname).toBe('/review/cs-manual'));
  });

  it('shows a taken local name under the field', async () => {
    const user = userEvent.setup();
    editingServer({ edits: () => problemResponse(409, 'element.name_taken') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '对象类型', '新建对象类型');
    await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByRole('textbox', { name: '中文名称' })).toHaveAttribute('aria-required', 'true');
    expect(within(dialog).getByRole('textbox', { name: '中文名称' })).toHaveAttribute('maxlength', '200');
    await user.type(within(dialog).getByRole('textbox', { name: '中文名称' }), '钢水');
    await user.type(within(dialog).getByRole('textbox', { name: '英文名称' }), 'Molten steel');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    const localName = within(dialog).getByRole('textbox', { name: '局部名' });
    await waitFor(() => expect(localName).toHaveAttribute('aria-invalid', 'true'));
    expect(localName).toHaveAccessibleDescription('局部名或 IRI 已被占用（包括已删除的元素），请换一个。');
    expect(localName).toHaveFocus();
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();

    await user.type(localName, '2');
    expect(localName).not.toHaveAttribute('aria-invalid');
  });

  it('submits for review for a reviewer in separate review mode', async () => {
    const user = userEvent.setup();
    editingServer({ user: userWithRole('reviewer'), reviewMode: 'separate' });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openCreateForm(user, '关系', '新建关系');
    expect(await within(dialog).findByRole('button', { name: '提交审核' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: '保存' })).not.toBeInTheDocument();
  });
});

describe('editing elements by hand', () => {
  it('sends only the changed fields with the revision it read', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    const save = await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByRole('textbox', { name: '局部名' })).toHaveAttribute('readonly');
    expect(within(dialog).getByRole('textbox', { name: '中文同义词' })).toHaveValue('铁水');
    expect(within(dialog).getByRole('textbox', { name: '英文同义词' })).toHaveValue('');

    await user.click(save);
    expect(within(dialog).getByText('还没有修改任何内容。')).toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    const definition = within(dialog).getByRole('textbox', { name: '中文定义' });
    await user.clear(definition);
    await user.type(definition, '转炉出钢时的液态钢。');
    await user.click(save);

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [
        {
          op: 'update',
          kind: 'entity_type',
          targetElementId: 'el-molten-steel',
          targetRevision: 3,
          fields: { definitionZh: '转炉出钢时的液态钢。' },
        },
      ],
      apply: true,
    });
    // Merging raised the revision while the save finished; the dialog still closes.
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '编辑“钢水”' })).not.toBeInTheDocument());
    expect(screen.getByRole('dialog', { name: '钢水' })).toBeInTheDocument();
  });

  it('keeps the synonyms of a language left alone as stored, separators and all', async () => {
    const user = userEvent.setup();
    const elements = initialElements();
    elements[0] = {
      ...moltenSteel,
      synonyms: [
        { lang: 'zh', text: '铁水' },
        { lang: 'en', text: 'Steel, molten' },
      ],
    };
    const api = editingServer({ elements });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    await user.type(await within(dialog).findByRole('textbox', { name: '中文同义词' }), '、钢液');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect((api.calls('POST', EDITS)[0]?.body as EditRequest).items[0]?.fields).toEqual({
      synonyms: [
        { lang: 'zh', text: '铁水' },
        { lang: 'zh', text: '钢液' },
        { lang: 'en', text: 'Steel, molten' },
      ],
    });
  });

  it('asks before discarding unsaved changes, and closes at once without them', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    let dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    await within(dialog).findByRole('button', { name: '保存' });
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '编辑“钢水”' })).not.toBeInTheDocument());

    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    const definition = await within(dialog).findByRole('textbox', { name: '英文定义' });
    await user.type(definition, 'Liquid steel.');

    await user.keyboard('{Escape}');
    const confirm = await screen.findByRole('dialog', { name: '放弃未保存的修改？' });
    expect(confirm).toHaveTextContent('这里的修改还没有保存，关闭后会丢失。');
    await user.click(within(confirm).getByRole('button', { name: '继续编辑' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '放弃未保存的修改？' })).not.toBeInTheDocument());
    expect(within(dialog).getByRole('textbox', { name: '英文定义' })).toHaveValue('Liquid steel.');

    await user.click(within(dialog).getByRole('button', { name: '取消' }));
    await user.click(within(await screen.findByRole('dialog', { name: '放弃未保存的修改？' })).getByRole('button', { name: '放弃修改' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '编辑“钢水”' })).not.toBeInTheDocument());
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('brings an imported element into the platform’s shape when its cardinality changes', async () => {
    const user = userEvent.setup();
    const elements = initialElements().map((element) => (element.id === 'el-held-by' ? { ...element, autoShape: false } : element));
    const api = editingServer({ elements });
    renderApp('/ontology?ontology=onto-steel&view=list');

    let sheet = await openElement(user, '盛装');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    let dialog = await screen.findByRole('dialog', { name: '编辑“盛装”' });
    await within(dialog).findByRole('button', { name: '保存' });
    // Already in the shape: nothing to explain.
    expect(within(dialog).queryByRole('button', { name: '关于校验规则' })).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '取消' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '编辑“盛装”' })).not.toBeInTheDocument());
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '盛装' })).not.toBeInTheDocument());

    sheet = await openElement(user, 'held by');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    dialog = await screen.findByRole('dialog', { name: '编辑“held by”' });
    await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByRole('button', { name: '关于校验规则' })).toHaveAccessibleDescription(
      '这个元素来自导入，必填和允许多个还没有写进平台的校验规则。修改这两项并保存后，平台会为它生成校验规则。',
    );

    await user.type(within(dialog).getByRole('textbox', { name: '中文名称' }), '被盛装');
    await user.click(within(dialog).getByRole('checkbox', { name: '必填' }));
    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect((api.calls('POST', EDITS)[0]?.body as EditRequest).items[0]?.fields).toEqual({ labelZh: '被盛装', required: true, autoShape: true });
  });

  it('explains a save that the merge rolled back in a whole sentence', async () => {
    const user = userEvent.setup();
    editingServer({ edits: () => problemResponse(409, 'changeset.has_dependents') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    await user.type(await within(dialog).findByRole('textbox', { name: '英文定义' }), 'Liquid steel.');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('没有保存');
    expect(alert).toHaveTextContent('还有其他元素引用要删除的元素，这次修改没有保存。请刷新后查看引用情况，先修改引用它的元素再删除。');
  });

  it('tells the user when someone else changed the element and reloads it on request', async () => {
    const user = userEvent.setup();
    const elements = initialElements();
    let attempts = 0;
    const api = editingServer({
      elements,
      edits: () => {
        attempts += 1;
        if (attempts > 1) return { changeSetId: 'cs-manual', merged: true, merge: { applied: 1, skipped: [] } };
        // Someone else saved in the meantime.
        elements[0] = { ...moltenSteel, revision: 4, definitionZh: '其他人改过的定义。' };
        return problemResponse(409, 'element.stale');
      },
    });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“钢水”' });
    await within(dialog).findByRole('button', { name: '保存' });
    await user.type(within(dialog).getByRole('textbox', { name: '英文定义' }), 'Liquid steel.');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('该元素已被其他人修改');
    await user.click(within(alert).getByRole('button', { name: '刷新' }));

    await waitFor(() => expect(within(dialog).getByRole('textbox', { name: '中文定义' })).toHaveValue('其他人改过的定义。'));
    expect(within(dialog).getByRole('textbox', { name: '英文定义' })).toHaveValue('');
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();

    await user.type(within(dialog).getByRole('textbox', { name: '英文定义' }), 'Liquid steel.');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(2));
    expect(api.calls('POST', EDITS)[1]?.body).toMatchObject({
      items: [{ op: 'update', targetElementId: 'el-molten-steel', targetRevision: 4, fields: { definitionEn: 'Liquid steel.' } }],
    });
  });

  it('keeps the rules of an imported constraint as stored unless they change', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水校验');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“钢水校验”' });
    const save = await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByText('urn:metals:MoltenSteelShape')).toBeInTheDocument();
    const rule = within(dialog).getByRole('region', { name: '规则 1' });
    expect(within(rule).getByRole('textbox', { name: '最小值' })).toHaveValue('1580.0');

    await user.type(within(dialog).getByRole('textbox', { name: '英文名称' }), 'Molten steel check');
    await user.click(save);
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toMatchObject({
      items: [{ op: 'update', kind: 'constraint', targetElementId: 'el-shape', targetRevision: 1, fields: { labelEn: 'Molten steel check' } }],
    });
    expect((api.calls('POST', EDITS)[0]?.body as EditRequest).items[0]?.fields).toEqual({ labelEn: 'Molten steel check' });

    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const again = await screen.findByRole('dialog', { name: '编辑“钢水校验”' });
    await within(again).findByRole('button', { name: '保存' });
    const message = within(within(again).getByRole('region', { name: '规则 1' })).getByRole('textbox', { name: '中文提示信息' });
    await user.clear(message);
    await user.type(message, '温度过低');
    await user.click(within(again).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(2));
    expect((api.calls('POST', EDITS)[1]?.body as EditRequest).items[0]?.fields).toEqual({
      rules: [
        {
          pathRef: 'el-temperature',
          classRef: null,
          minCount: 1,
          maxCount: null,
          datatype: null,
          nodeKind: null,
          allowedValues: null,
          allowedValuesLost: false,
          minInclusive: { iri: null, lexical: '1580.0', datatype: 'decimal', lang: null },
          maxInclusive: null,
          minExclusive: null,
          maxExclusive: null,
          minLength: null,
          maxLength: null,
          pattern: null,
          flags: null,
          message: [{ lang: 'zh', text: '温度过低' }],
        },
      ],
    });
  });

  it('shows the IRI of an imported element, keeps its local name and does not require a Chinese name', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, 'held by');
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑“held by”' });
    const save = await within(dialog).findByRole('button', { name: '保存' });
    expect(within(dialog).getByText('urn:metals:heldBy')).toBeInTheDocument();
    expect(within(dialog).getByRole('textbox', { name: '局部名' })).toHaveAttribute('readonly');
    expect(within(dialog).getByText('中文名称')).not.toHaveTextContent('*');
    expect(within(dialog).getByRole('combobox', { name: '互逆关系' })).toHaveValue('el-holds');

    const labelEn = within(dialog).getByRole('textbox', { name: '英文名称' });
    await user.clear(labelEn);
    await user.type(labelEn, 'is held by');
    await user.click(save);

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect((api.calls('POST', EDITS)[0]?.body as EditRequest).items[0]?.fields).toEqual({ labelEn: 'is held by' });
  });
});

describe('deleting and restoring elements', () => {
  it('lists the whole cascade from the server before deleting it and sends only the delete', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    await user.click(within(sheet).getByRole('button', { name: '删除' }));
    const dialog = await screen.findByRole('dialog', { name: '删除“钢水”？' });

    expect(await within(dialog).findByText('删除时会一并处理 7 个元素')).toBeInTheDocument();
    const deleted = within(dialog).getByRole('list', { name: '一并删除（4）' });
    expect(within(deleted).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '关系盛装',
      '属性温度',
      '约束钢水校验',
      '高级公理steel:MoltenSteel owl:disjointWith steel:Slag .',
    ]);
    const changed = within(dialog).getByRole('list', { name: '清除引用（3）' });
    expect(within(changed).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '约束钢包校验移除引用它的规则',
      '对象类型精炼钢清空父类型',
      '关系held by清空互逆关系',
    ]);

    await user.click(within(dialog).getByRole('button', { name: '删除' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [{ op: 'delete', kind: 'entity_type', targetElementId: 'el-molten-steel', targetRevision: 3 }],
      apply: true,
    });
    expect(await screen.findByText('已删除“钢水”')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '删除“钢水”？' })).not.toBeInTheDocument());
  });

  it('says when nothing refers to the element', async () => {
    const user = userEvent.setup();
    editingServer({ user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢包');
    await user.click(within(sheet).getByRole('button', { name: '删除' }));
    const dialog = await screen.findByRole('dialog', { name: '删除“钢包”？' });
    expect(await within(dialog).findByText('没有其他元素引用它，只删除它本身。')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '提交审核' })).toBeEnabled();
    // The delete waits for review; the dialog says so.
    expect(dialog).toHaveTextContent('提交后生成变更集，审核通过后才会删除');
    expect(dialog).not.toHaveTextContent('删除后它不再导出，列表默认也不显示');
  });

  it('submits a restore for review when the user may not apply it', async () => {
    const user = userEvent.setup();
    const api = editingServer({ user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(screen.getByRole('group', { name: '按状态筛选' })).getByRole('radio', { name: '已删除' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).queryByRole('button', { name: '恢复“Slab”' })).not.toBeInTheDocument();
    await user.click(within(table).getByRole('button', { name: '提交恢复“Slab”' }));

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [{ op: 'restore', kind: 'entity_type', targetElementId: 'el-slab', targetRevision: 2 }],
      apply: false,
    });
    expect(await screen.findByText('已提交审核，审核通过后生效')).toBeInTheDocument();

    const sheet = await openElement(user, 'Slab');
    expect(within(sheet).getByRole('button', { name: '提交恢复' })).toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: '恢复' })).not.toBeInTheDocument();
  });

  it('filters deleted elements with a removable chip and restores one', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    expect(within(table).queryByRole('button', { name: 'Slab' })).not.toBeInTheDocument();
    await user.click(within(screen.getByRole('group', { name: '按状态筛选' })).getByRole('radio', { name: '已删除' }));

    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(api.requests.some((request) => request.path.endsWith('/elements') && request.query.get('status') === 'deprecated')).toBe(true);
    expect(screen.getByRole('list', { name: '当前筛选条件' })).toHaveTextContent('状态：已删除');
    const [, row] = within(table).getAllByRole('row');
    expect(row).toHaveTextContent('已删除');

    await user.click(within(row as HTMLElement).getByRole('button', { name: '恢复“Slab”' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [{ op: 'restore', kind: 'entity_type', targetElementId: 'el-slab', targetRevision: 2 }],
      apply: true,
    });
    expect(await screen.findByText('已恢复“Slab”')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '移除筛选条件“状态：已删除”' }));
    // Back to the elements in use, which now include the restored one.
    await waitFor(() => expect(screen.queryByRole('list', { name: '当前筛选条件' })).not.toBeInTheDocument());
    // Nothing was left deleted, so the list was empty; it is a new table now.
    const inUse = await screen.findByRole('table', { name: '本体元素' });
    await waitFor(() => expect(within(inUse).getAllByRole('row')).toHaveLength(initialElements().filter((element) => element.status === 'active').length + 2));
    const restored = within(inUse).getByRole('button', { name: 'Slab' }).closest('tr');
    expect(restored).not.toHaveTextContent('已删除');
  });

  it('restores a deleted element from its panel', async () => {
    const user = userEvent.setup();
    const api = editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(screen.getByRole('group', { name: '按状态筛选' })).getByRole('radio', { name: '全部' }));
    const sheet = await openElement(user, 'Slab');
    expect(within(sheet).queryByRole('button', { name: '编辑' })).not.toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: '删除' })).not.toBeInTheDocument();
    await user.click(within(sheet).getByRole('button', { name: '恢复' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toMatchObject({ items: [{ op: 'restore', targetElementId: 'el-slab', targetRevision: 2 }] });
  });
});

describe('referenced by', () => {
  it('lists what refers to an element and opens it in the panel', async () => {
    const user = userEvent.setup();
    editingServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const sheet = await openElement(user, '钢水');
    const subtypes = await within(sheet).findByText('子类型（1）');
    expect(within(sheet).getByText('约束（2）').nextElementSibling).toHaveTextContent('钢水校验钢包校验');
    expect(within(sheet).getByText('公理（1）')).toBeInTheDocument();
    await user.click(within(subtypes.nextElementSibling as HTMLElement).getByRole('button', { name: '精炼钢' }));

    const child = await screen.findByRole('dialog', { name: '精炼钢' });
    expect(await within(child).findByText('没有其他元素引用它。')).toBeInTheDocument();
  });
});

describe('permissions', () => {
  it('shows no write actions to a viewer', async () => {
    const user = userEvent.setup();
    editingServer({ user: userWithRole('viewer') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    expect(screen.queryByRole('button', { name: '新建' })).not.toBeInTheDocument();

    const sheet = await openElement(user, '钢水');
    expect(await within(sheet).findByText('子类型（1）')).toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: '编辑' })).not.toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: '删除' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '钢水' })).not.toBeInTheDocument());

    await user.click(within(screen.getByRole('group', { name: '按状态筛选' })).getByRole('radio', { name: '已删除' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).queryByRole('button', { name: /恢复/ })).not.toBeInTheDocument();
    expect(within(table).queryByRole('columnheader', { name: '操作' })).not.toBeInTheDocument();
  });
});
