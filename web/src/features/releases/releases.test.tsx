import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import { comparisonFixture, elementChangeFixture, elementFixture, ontologyFixture, releaseFixture } from '@/test/fixtures';
import { captureDownloads, mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import type { ReleaseSummary } from './api';

function releasesServer({ extra = {}, user }: { extra?: Record<string, RouteHandler>; user?: UserInfo } = {}) {
  let releases: ReleaseSummary[] = [
    releaseFixture({ id: 'rel-two', version: 2, title: '补充精炼工艺', isActive: true, elementCount: 9 }),
    releaseFixture({ id: 'rel-one', version: 1, title: '首版', elementCount: 4 }),
  ];
  const api = mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture({ openChangeSetCount: 2, activeReleaseId: 'rel-two', activeReleaseVersion: 2 })],
      'GET /api/ontologies/:id/elements': () => [elementFixture({ id: 'el-a', labelZh: '钢包' })],
      'GET /api/ontologies/:id/releases': () => releases,
      'POST /api/ontologies/:id/releases': ({ body }) => {
        const created = releaseFixture({ id: 'rel-three', version: 3, title: (body as { title: string }).title, elementCount: 10 });
        releases = [created, ...releases];
        return created;
      },
      'GET /api/ontologies/:id/compare': () => comparisonFixture(),
      'POST /api/releases/:id/activate': ({ params }) => {
        releases = releases.map((release) => ({ ...release, isActive: release.id === params.id }));
        return releases.find((release) => release.id === params.id);
      },
      ...extra,
    },
    user ? { user } : {},
  );
  return api;
}

function row(version: string) {
  const cell = within(screen.getByRole('table', { name: '版本列表' })).getByText(version);
  const tr = cell.closest('tr');
  if (!tr) throw new Error(`No row for ${version}`);
  return tr;
}

describe('releases page', () => {
  it('lists releases with version, title, element count and the current one', async () => {
    releasesServer();
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('table', { name: '版本列表' });
    expect(within(row('v2')).getByText('补充精炼工艺')).toBeInTheDocument();
    expect(within(row('v2')).getByText('当前版本')).toBeInTheDocument();
    expect(within(row('v2')).getByText('9')).toBeInTheDocument();
    expect(within(row('v1')).queryByText('当前版本')).not.toBeInTheDocument();
    // Only releases that are not current can be made current.
    expect(within(row('v2')).queryByRole('button', { name: '设为当前版本' })).not.toBeInTheDocument();
    expect(within(row('v1')).getByRole('button', { name: '设为当前版本' })).toBeInTheDocument();
  });

  it('lists the validation problems of a refused release by element and code', async () => {
    const user = userEvent.setup();
    const api = releasesServer({
      extra: {
        'POST /api/ontologies/:id/releases': () =>
          problemResponse(422, 'release.invalid', {
            problems: [
              { code: 'release.cyclic_hierarchy', elementId: 'el-a', message: 'Backend message about a cycle' },
              { code: 'release.invalid_domain', elementId: 'el-a', message: 'Backend message about a domain' },
              { code: 'release.brand_new_check', elementId: null, message: 'Backend message' },
            ],
          }),
      },
    });
    renderApp('/releases?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '发布新版本' }));
    const dialog = await screen.findByRole('dialog', { name: '发布新版本' });
    expect(within(dialog).getByText('还有 2 个变更集未合并')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '发布版本' }));
    expect(within(dialog).getByText('请填写版本标题后再发布。')).toBeInTheDocument();
    expect(api.calls('POST', '/api/ontologies/onto-steel/releases')).toHaveLength(0);

    await user.type(within(dialog).getByRole('textbox', { name: '版本标题' }), '第三版');
    await user.click(within(dialog).getByRole('button', { name: '发布版本' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('发布校验没有通过（3 个问题）');
    expect((await within(alert).findAllByText('钢包')).length).toBe(2);
    expect(alert).toHaveTextContent('钢包：父子类型形成了循环');
    expect(alert).toHaveTextContent('钢包：所属对象类型（定义域）不存在或已停用');
    expect(alert).toHaveTextContent('没有通过发布校验，请检查这个元素。');
    expect(alert).not.toHaveTextContent('Backend message');
    expect(api.calls('POST', '/api/ontologies/onto-steel/releases')[0]?.body).toEqual({ title: '第三版' });
  });

  it('publishes a release and refreshes the list', async () => {
    const user = userEvent.setup();
    const api = releasesServer();
    renderApp('/releases?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '发布新版本' }));
    const dialog = await screen.findByRole('dialog', { name: '发布新版本' });
    await user.type(within(dialog).getByRole('textbox', { name: '版本标题' }), '第三版');
    await user.type(within(dialog).getByRole('textbox', { name: '版本说明' }), '加入热轧工艺');
    await user.click(within(dialog).getByRole('button', { name: '发布版本' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '发布新版本' })).not.toBeInTheDocument());
    expect(api.calls('POST', '/api/ontologies/onto-steel/releases')[0]?.body).toEqual({ title: '第三版', notes: '加入热轧工艺' });
    expect(await screen.findByText('第三版')).toBeInTheDocument();
    expect((await screen.findAllByText('已发布版本 v3')).length).toBeGreaterThan(0);
  });

  it('asks for confirmation before making an older release current', async () => {
    const user = userEvent.setup();
    const api = releasesServer();
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('table', { name: '版本列表' });
    await user.click(within(row('v1')).getByRole('button', { name: '设为当前版本' }));
    let dialog = await screen.findByRole('dialog', { name: '把 v1 设为当前版本？' });
    expect(dialog).toHaveTextContent('当前版本将从 v2 改为 v1。');
    expect(dialog).toHaveTextContent('之后对外提供的查询、问答和导出都使用 v1 的内容');

    await user.click(within(dialog).getByRole('button', { name: '取消' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '把 v1 设为当前版本？' })).not.toBeInTheDocument());
    expect(api.calls('POST', '/api/releases/rel-one/activate')).toHaveLength(0);

    await user.click(within(row('v1')).getByRole('button', { name: '设为当前版本' }));
    dialog = await screen.findByRole('dialog', { name: '把 v1 设为当前版本？' });
    await user.click(within(dialog).getByRole('button', { name: '设为当前版本' }));

    await waitFor(() => expect(api.calls('POST', '/api/releases/rel-one/activate')).toHaveLength(1));
    await waitFor(() => expect(within(row('v1')).getByText('当前版本')).toBeInTheDocument());
    expect(within(row('v2')).getByRole('button', { name: '设为当前版本' })).toBeInTheDocument();
  });

  it('exports a release as a Turtle file named after the ontology and version', async () => {
    const user = userEvent.setup();
    const downloads = captureDownloads();
    releasesServer({
      extra: {
        'GET /api/releases/:id/export': () => new Response('@prefix sh: <http://www.w3.org/ns/shacl#> .\n', { headers: { 'Content-Type': 'text/turtle' } }),
      },
    });
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('table', { name: '版本列表' });
    await user.click(within(row('v1')).getByRole('button', { name: '导出 v1 的 Turtle' }));
    await waitFor(() => expect(downloads.names).toEqual(['steel-v1.ttl']));
  });

  it('hides publishing and activation from viewers but keeps export', async () => {
    releasesServer({ user: userWithRole('viewer') });
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('table', { name: '版本列表' });
    expect(screen.queryByRole('button', { name: '发布新版本' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '设为当前版本' })).not.toBeInTheDocument();
    expect(within(row('v1')).getByRole('button', { name: '导出 v1 的 Turtle' })).toBeInTheDocument();
  });

  it('hides publishing from editors, who may upload but not publish', async () => {
    releasesServer({ user: userWithRole('editor') });
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('table', { name: '版本列表' });
    expect(screen.queryByRole('button', { name: '发布新版本' })).not.toBeInTheDocument();
  });
});

const ladleRef = { id: 'el-ladle', label: '钢包' };
const steelRef = { id: 'el-molten-steel', label: '钢水' };
const workingChanges = [
  elementChangeFixture({ elementId: 'el-ladle', label: '钢包', change: 'removed', level: 'breaking' }),
  elementChangeFixture({
    elementId: 'el-temperature',
    kind: 'property',
    label: '温度',
    level: 'breaking',
    fields: [
      { field: 'domainId', before: steelRef, after: ladleRef },
      { field: 'datatype', before: 'decimal', after: 'integer' },
      { field: 'required', before: false, after: true },
    ],
  }),
  elementChangeFixture({
    elementId: 'el-shape',
    kind: 'constraint',
    label: '钢水校验',
    level: 'review',
    fields: [{ field: 'rules', before: [{ pathId: 'el-temperature' }], after: [] }],
  }),
  elementChangeFixture({
    elementId: 'el-axiom',
    kind: 'axiom',
    label: 'steel:MoltenSteel owl:disjointWith steel:Slag .',
    iri: null,
    level: 'review',
    fields: [{ field: 'turtle', before: 'steel:MoltenSteel owl:disjointWith steel:Slag .', after: 'steel:MoltenSteel owl:disjointWith steel:Ladle .' }],
  }),
  elementChangeFixture({
    level: 'compatible',
    fields: [
      { field: 'labelEn', before: 'Molten steel', after: 'Liquid steel' },
      { field: 'synonyms', before: [], after: [{ lang: 'zh', text: '铁水' }, { lang: 'zh', text: '液态钢' }] },
      { field: 'parentId', before: { id: 'el-gone', label: null }, after: null },
    ],
  }),
  elementChangeFixture({ elementId: 'el-heat', label: '炉次', change: 'added', level: 'compatible' }),
  elementChangeFixture({ elementId: 'el-slab', label: '板坯', change: 'restored', level: 'compatible' }),
];

function entry(region: HTMLElement, label: string) {
  const item = within(region)
    .getAllByRole('listitem')
    .find((candidate) => within(candidate).queryByText(label) !== null);
  if (!item) throw new Error(`No change for ${label}`);
  return item;
}

describe('version comparison', () => {
  it('compares the current release with the working version by default, grouped by level with field changes', async () => {
    const api = releasesServer({ extra: { 'GET /api/ontologies/:id/compare': () => comparisonFixture(workingChanges) } });
    renderApp('/releases?ontology=onto-steel');

    expect(await screen.findByRole('heading', { name: '版本对比' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '起点' })).toHaveDisplayValue('v2 · 补充精炼工艺（当前）');
    expect(screen.getByRole('combobox', { name: '终点' })).toHaveDisplayValue('工作版本');
    await waitFor(() => expect(api.calls('GET', '/api/ontologies/onto-steel/compare').length).toBeGreaterThan(0));
    const query = api.calls('GET', '/api/ontologies/onto-steel/compare')[0]?.query;
    expect(query?.get('from')).toBe('rel-two');
    expect(query?.get('to')).toBe('working');

    const counts = await screen.findByRole('list', { name: '各级变更的数量' });
    expect(counts).toHaveTextContent('不兼容 2 项');
    expect(counts).toHaveTextContent('需确认 2 项');
    expect(counts).toHaveTextContent('兼容 3 项');

    const breaking = screen.getByRole('region', { name: '不兼容 2 项' });
    expect(entry(breaking, '钢包')).toHaveTextContent('对象类型');
    expect(entry(breaking, '钢包')).toHaveTextContent('删除');
    const temperature = entry(breaking, '温度');
    expect(temperature).toHaveTextContent('属性');
    expect(temperature).toHaveTextContent('修改');
    // References by name; a property's domain is the object type it belongs to.
    expect(temperature).toHaveTextContent('所属对象类型：钢水改为钢包');
    expect(temperature).toHaveTextContent('数据类型：小数改为整数');
    expect(temperature).toHaveTextContent('必填：否改为是');

    const review = screen.getByRole('region', { name: '需确认 2 项' });
    expect(entry(review, '钢水校验')).toHaveTextContent('约束规则：规则有变化');
    const axiom = entry(review, 'steel:MoltenSteel owl:disjointWith steel:Slag .');
    expect(axiom).toHaveTextContent('Turtle 片段：片段有变化');
    expect(axiom).not.toHaveTextContent('steel:Ladle');

    const compatible = screen.getByRole('region', { name: '兼容 3 项' });
    const moltenSteel = entry(compatible, '钢水');
    expect(moltenSteel).toHaveTextContent('英文名称：Molten steel改为Liquid steel');
    expect(moltenSteel).toHaveTextContent('同义词：无改为铁水、液态钢');
    expect(moltenSteel).toHaveTextContent('父类型：已不存在的元素改为无');
    expect(entry(compatible, '炉次')).toHaveTextContent('新增');
    expect(entry(compatible, '板坯')).toHaveTextContent('恢复');

    // No ids or internal codes on the page.
    expect(document.body).not.toHaveTextContent('el-temperature');
    expect(document.body).not.toHaveTextContent('breaking');
  });

  it('compares two releases when the user picks them', async () => {
    const user = userEvent.setup();
    const api = releasesServer({
      extra: {
        'GET /api/ontologies/:id/compare': ({ query }) =>
          query.get('to') === 'working'
            ? comparisonFixture(workingChanges)
            : comparisonFixture([], { from: { releaseId: 'rel-one', version: 1 }, to: { releaseId: 'rel-two', version: 2 } }),
      },
    });
    renderApp('/releases?ontology=onto-steel');

    await screen.findByRole('region', { name: '不兼容 2 项' });
    await user.selectOptions(screen.getByRole('combobox', { name: '起点' }), 'v1 · 首版');
    await user.selectOptions(screen.getByRole('combobox', { name: '终点' }), 'v2 · 补充精炼工艺（当前）');

    expect(await screen.findByText('两个版本没有差异')).toBeInTheDocument();
    const last = api.calls('GET', '/api/ontologies/onto-steel/compare').at(-1)?.query;
    expect(last?.get('from')).toBe('rel-one');
    expect(last?.get('to')).toBe('rel-two');
    expect(screen.queryByRole('region', { name: '不兼容 2 项' })).not.toBeInTheDocument();
  });

  it('offers no comparison before the first release', async () => {
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/releases': () => [],
      'GET /api/ontologies/:id/compare': () => comparisonFixture(),
    });
    renderApp('/releases?ontology=onto-steel');

    expect(await screen.findByText('还没有发布过版本')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '版本对比' })).not.toBeInTheDocument();
    expect(api.calls('GET', '/api/ontologies/onto-steel/compare')).toHaveLength(0);
  });
});

describe('publish dialog summary', () => {
  it('summarizes the changes since the current release and warns about breaking ones', async () => {
    const user = userEvent.setup();
    releasesServer({ extra: { 'GET /api/ontologies/:id/compare': () => comparisonFixture(workingChanges) } });
    renderApp('/releases?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '发布新版本' }));
    const dialog = await screen.findByRole('dialog', { name: '发布新版本' });
    const summary = within(dialog).getByRole('region', { name: '相对当前版本 v2 的变更' });
    expect(await within(summary).findByText('不兼容 2 项')).toBeInTheDocument();
    expect(summary).toHaveTextContent('需确认 2 项');
    expect(summary).toHaveTextContent('兼容 3 项');
    expect(within(summary).getByRole('status')).toHaveTextContent('有 2 项不兼容变更，依赖这些元素的数据和查询可能失效');
  });

  it('shows the summary without a warning when nothing breaks', async () => {
    const user = userEvent.setup();
    const compatibleOnly = workingChanges.filter((change) => change.level !== 'breaking');
    releasesServer({ extra: { 'GET /api/ontologies/:id/compare': () => comparisonFixture(compatibleOnly) } });
    renderApp('/releases?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '发布新版本' }));
    const dialog = await screen.findByRole('dialog', { name: '发布新版本' });
    const summary = within(dialog).getByRole('region', { name: '相对当前版本 v2 的变更' });
    expect(await within(summary).findByText('不兼容 0 项')).toBeInTheDocument();
    expect(summary).toHaveTextContent('需确认 2 项');
    expect(summary).not.toHaveTextContent('不兼容变更，依赖这些元素');
  });

  it('shows no summary for the first release', async () => {
    const user = userEvent.setup();
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/releases': () => [],
      'GET /api/ontologies/:id/compare': () => comparisonFixture(workingChanges),
    });
    renderApp('/releases?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '发布新版本' }));
    const dialog = await screen.findByRole('dialog', { name: '发布新版本' });
    expect(within(dialog).getByRole('textbox', { name: '版本标题' })).toBeInTheDocument();
    expect(within(dialog).queryByText(/相对当前版本/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/不兼容/)).not.toBeInTheDocument();
    expect(api.calls('GET', '/api/ontologies/onto-steel/compare')).toHaveLength(0);
  });
});
