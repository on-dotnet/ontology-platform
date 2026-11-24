import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import type { EditRequest, Element, ImportResult } from '@/features/ontologies/api';
import { axiomFixture, elementDetailFixture, elementFixture, impactFixture, importResultFixture, mergeEdits, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

// jsdom cannot type into CodeMirror; the stand-in has the same props and handle.
vi.mock('@/components/code/turtle-editor', () => import('@/test/turtle-editor-stub'));

const EDITS = '/api/ontologies/onto-steel/edits';
const TURTLE = '/api/ontologies/onto-steel/turtle';

const EXPORT = [
  '@prefix owl: <http://www.w3.org/2002/07/owl#> .',
  '@prefix steel: <https://example.org/ontology/steel#> .',
  '',
  'steel:Ladle a owl:Class .',
  'steel:MoltenSteel a owl:Class .',
  '',
].join('\n');

const moltenSteel = elementFixture({ revision: 3 });
const ladle = elementFixture({ id: 'el-ladle', localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装钢水的容器。' });
const disjoint = axiomFixture({ revision: 2 });
const keyed = axiomFixture({ id: 'el-axiom-keys', turtle: 'steel:MoltenSteel owl:hasKey ( steel:heatNumber ) .' });
const ladleAxiom = axiomFixture({ id: 'el-axiom-ladle', turtle: 'steel:Ladle owl:disjointWith steel:Slag .', subjectId: 'el-ladle' });
const imports = axiomFixture({ id: 'el-axiom-imports', turtle: '<https://example.org/ontology/steel> owl:imports <https://example.org/units> .', subjectId: null });

interface ServerOptions {
  user?: UserInfo;
  reviewMode?: 'single' | 'separate';
  elements?: Element[];
  turtle?: RouteHandler;
  edits?: RouteHandler;
}

function expertServer({ user, reviewMode = 'single', elements = [moltenSteel, ladle, disjoint, keyed, ladleAxiom, imports], turtle, edits }: ServerOptions = {}) {
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/settings/platform': () => ({ reviewMode }),
      'GET /api/ontologies/:id/export': () => new Response(EXPORT, { headers: { 'Content-Type': 'text/turtle' } }),
      'GET /api/ontologies/:id/elements': ({ query }) => {
        const kind = query.get('kind');
        const status = query.get('status') ?? 'active';
        return elements.filter((element) => (!kind || element.kind === kind) && (status === 'all' || element.status === status));
      },
      'GET /api/ontologies/:id/elements/:elementId': ({ params }) => {
        const element = elements.find((item) => item.id === params.elementId);
        return element ? elementDetailFixture(element) : problemResponse(404, 'element.not_found');
      },
      'GET /api/ontologies/:id/elements/:elementId/impact': ({ params }) => impactFixture(params.elementId ?? ''),
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
      'POST /api/ontologies/:id/turtle': turtle ?? (() => importResultFixture({ changeSetId: 'cs-turtle', counts: { create: 1, update: 0, delete: 0, restore: 0 } })),
      'POST /api/ontologies/:id/edits':
        edits ??
        (({ body }) => {
          const request = body as EditRequest;
          // Merged at once, as the server does: the targets move to their next revision.
          if (request.apply) mergeEdits(elements, request);
          return { changeSetId: 'cs-manual', merged: request.apply, merge: request.apply ? { applied: 1, skipped: [] } : null };
        }),
    },
    { user },
  );
}

function turtleBox() {
  return screen.findByRole('textbox', { name: '工作版本的 Turtle' });
}

async function startEditing(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '编辑' }));
  const box = await turtleBox();
  expect(box).not.toHaveAttribute('readonly');
  return box;
}

describe('expert mode: the Turtle view', () => {
  it('shows the working version read-only, and offers editing only to those who may write', async () => {
    expertServer({ user: userWithRole('viewer') });
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await turtleBox();
    expect(box).toHaveValue(EXPORT);
    expect(box).toHaveAttribute('readonly');
    expect(screen.getByRole('radio', { name: 'Turtle' })).toBeChecked();
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument();
  });

  it('switches to the Turtle view and keeps it in the URL', async () => {
    const user = userEvent.setup();
    const api = expertServer();
    const { router } = renderApp('/ontology?ontology=onto-steel&view=list');

    await screen.findByRole('table', { name: '本体元素' });
    await user.click(screen.getByRole('radio', { name: 'Turtle' }));
    expect(await turtleBox()).toHaveValue(EXPORT);
    expect(router.state.location.search).toEqual({ ontology: 'onto-steel', view: 'turtle' });
    expect(api.calls('GET', '/api/ontologies/onto-steel/export')[0]?.query.get('format')).toBe('turtle');
  });

  it('turns edited Turtle into a change set for review and summarizes it like an import', async () => {
    const user = userEvent.setup();
    const result: ImportResult = importResultFixture({
      changeSetId: 'cs-turtle',
      counts: { create: 1, update: 2, delete: 0, restore: 0 },
      warnings: [{ code: 'non_standard', count: 1 }],
    });
    const api = expertServer({ turtle: () => result });
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await startEditing(user);
    // Even a reviewer in single review mode only proposes: the change set always goes to review.
    expect(screen.getByText('生成的变更集一律进入审核，合并后才会生效。')).toBeInTheDocument();
    await user.type(box, 'steel:Slab a owl:Class .');
    await user.click(screen.getByRole('button', { name: '生成变更集' }));

    const summary = await screen.findByRole('dialog', { name: '已生成变更集' });
    expect(api.calls('POST', TURTLE)).toHaveLength(1);
    expect(api.calls('POST', TURTLE)[0]?.body).toEqual({ turtle: `${EXPORT}steel:Slab a owl:Class .` });
    expect(api.calls('POST', EDITS)).toHaveLength(0);
    expect(summary).toHaveTextContent('修改已整理成变更集，审核并合并后才会进入本体。');
    const counts = within(summary).getByText('新增').closest('dl');
    expect(counts).toHaveTextContent('新增1');
    expect(counts).toHaveTextContent('修改2');
    expect(within(summary).getByRole('list', { name: '需要注意的内容' })).toHaveTextContent('1 条公理在 Protégé 中会被改写');
    expect(within(summary).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-turtle');

    // Back to reading the working version.
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '已生成变更集' })).not.toBeInTheDocument());
    expect(await turtleBox()).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: '编辑' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成变更集' })).not.toBeInTheDocument();
  });

  it('says so when the Turtle has no differences from the working version', async () => {
    const user = userEvent.setup();
    expertServer({ turtle: () => importResultFixture({ changeSetId: null, counts: { create: 0, update: 0, delete: 0, restore: 0 } }) });
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await startEditing(user);
    await user.type(box, '\n');
    await user.click(screen.getByRole('button', { name: '生成变更集' }));

    const summary = await screen.findByRole('dialog', { name: '没有发现差异' });
    expect(summary).toHaveTextContent('Turtle 与工作版本没有差异，没有生成变更集。');
    expect(within(summary).queryByRole('link', { name: '去审核' })).not.toBeInTheDocument();
  });

  it('names the line of a syntax error and puts the cursor there', async () => {
    const user = userEvent.setup();
    const api = expertServer({ turtle: () => problemResponse(422, 'import.parse_error', { line: 4, column: null }) });
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = (await startEditing(user)) as HTMLTextAreaElement;
    await user.type(box, 'steel:Slab a .');
    await user.click(screen.getByRole('button', { name: '生成变更集' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Turtle 有语法错误');
    expect(alert).toHaveTextContent('第 4 行有语法错误');
    expect(api.calls('POST', TURTLE)).toHaveLength(1);
    const lineFour = EXPORT.split('\n').slice(0, 3).join('\n').length + 1;
    await waitFor(() => expect(box).toHaveFocus());
    expect(box.selectionStart).toBe(lineFour);
    expect(box).toHaveAttribute('aria-invalid', 'true');

    // The edits stay; the notice can take the cursor back to the line.
    expect(box.value).toBe(`${EXPORT}steel:Slab a .`);
    box.setSelectionRange(0, 0);
    await user.click(within(alert).getByRole('button', { name: '定位到第 4 行' }));
    expect(box.selectionStart).toBe(lineFour);
  });

  it('refuses empty Turtle and unchanged Turtle without asking the server', async () => {
    const user = userEvent.setup();
    const api = expertServer();
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await startEditing(user);
    await user.click(screen.getByRole('button', { name: '生成变更集' }));
    expect(await screen.findByText('还没有修改任何内容。')).toBeInTheDocument();

    await user.clear(box);
    await user.click(screen.getByRole('button', { name: '生成变更集' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Turtle 内容不能为空');
    expect(api.calls('POST', TURTLE)).toHaveLength(0);
  });

  it('discards the edits on cancel', async () => {
    const user = userEvent.setup();
    expertServer();
    renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await startEditing(user);
    await user.type(box, 'steel:Slab a owl:Class .');
    await user.click(screen.getByRole('button', { name: '取消' }));

    expect(box).toHaveValue(EXPORT);
    expect(box).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: '编辑' })).toBeInTheDocument();
  });

  it('asks before leaving with unsaved edits, and leaves at once without them', async () => {
    const user = userEvent.setup();
    expertServer();
    const { router } = renderApp('/ontology?ontology=onto-steel&view=turtle');

    const box = await startEditing(user);
    await user.type(box, 'steel:Slab a owl:Class .');
    await user.click(screen.getByRole('radio', { name: '列表' }));

    const confirm = await screen.findByRole('dialog', { name: '放弃未保存的修改？' });
    await user.click(within(confirm).getByRole('button', { name: '继续编辑' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '放弃未保存的修改？' })).not.toBeInTheDocument());
    expect(router.state.location.search).toEqual({ ontology: 'onto-steel', view: 'turtle' });
    expect(box).toHaveValue(`${EXPORT}steel:Slab a owl:Class .`);

    await user.click(screen.getByRole('radio', { name: '列表' }));
    await user.click(within(await screen.findByRole('dialog', { name: '放弃未保存的修改？' })).getByRole('button', { name: '放弃修改' }));
    expect(await screen.findByRole('table', { name: '本体元素' })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ ontology: 'onto-steel', view: 'list' });

    // Editing without changes: nothing to lose, nothing to ask.
    await user.click(screen.getByRole('radio', { name: 'Turtle' }));
    await startEditing(user);
    await user.click(screen.getByRole('radio', { name: '列表' }));
    expect(await screen.findByRole('table', { name: '本体元素' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '放弃未保存的修改？' })).not.toBeInTheDocument();
  });
});

describe('expert mode: single axioms', () => {
  it('writes a new axiom with the ontology prefixes at hand and saves it like other edits', async () => {
    const user = userEvent.setup();
    const api = expertServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    await user.click(await screen.findByRole('button', { name: '新建' }));
    await user.click(await screen.findByRole('menuitem', { name: '高级公理' }));
    const dialog = await screen.findByRole('dialog', { name: '新建高级公理' });
    expect(within(dialog).getByText('保存后立即生效。')).toBeInTheDocument();
    const fragment = within(dialog).getByRole('textbox', { name: 'Turtle 片段' });
    expect(fragment).toHaveAccessibleDescription('可以使用本体的前缀。');

    // The prefixes are folded away until asked for.
    const toggle = await within(dialog).findByRole('button', { name: '查看前缀（2）' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(dialog).queryByRole('list', { name: '本体的前缀' })).not.toBeInTheDocument();
    await user.click(toggle);
    const prefixes = within(dialog).getByRole('list', { name: '本体的前缀' });
    expect(within(prefixes).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'owl:http://www.w3.org/2002/07/owl#',
      'steel:https://example.org/ontology/steel#',
    ]);
    expect(within(dialog).getByRole('button', { name: '收起前缀' })).toHaveAttribute('aria-expanded', 'true');

    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    expect(within(dialog).getByText('请输入 Turtle 片段')).toBeInTheDocument();
    expect(fragment).toHaveAttribute('aria-invalid', 'true');
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    await user.type(fragment, 'steel:Ladle owl:disjointWith steel:MoltenSteel .');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [{ op: 'create', kind: 'axiom', tempRef: 'new:1', fields: { turtle: 'steel:Ladle owl:disjointWith steel:MoltenSteel .' } }],
      apply: true,
    });
    expect(await screen.findByText('已保存')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建高级公理' })).not.toBeInTheDocument());
  });

  it.each([
    ['axiom.maps_to_element', '这段内容可以用元素的表单表达，请到对应元素上编辑。'],
    ['axiom.invalid', '公理片段无法解析、不是恰好一条公理，或本体里已有这条公理，请检查后再保存。'],
  ])('explains a fragment the server refuses (%s) in the dialog', async (code, text) => {
    const user = userEvent.setup();
    expertServer({ edits: () => problemResponse(422, code) });
    renderApp('/ontology?ontology=onto-steel&view=list');

    await user.click(await screen.findByRole('button', { name: '新建' }));
    await user.click(await screen.findByRole('menuitem', { name: '高级公理' }));
    const dialog = await screen.findByRole('dialog', { name: '新建高级公理' });
    await user.type(within(dialog).getByRole('textbox', { name: 'Turtle 片段' }), 'steel:Ladle rdfs:label "钢包"@zh .');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('没有保存');
    expect(alert).toHaveTextContent(text);
    expect(screen.getByRole('dialog', { name: '新建高级公理' })).toBeInTheDocument();
  });

  it('rewrites an axiom from its panel with the revision it read, and submits it for review when it must', async () => {
    const user = userEvent.setup();
    const api = expertServer({ user: userWithRole('editor') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: 'steel:MoltenSteel owl:disjointWith steel:Slag .' }));
    const sheet = await screen.findByRole('dialog', { name: '高级公理' });
    await user.click(within(sheet).getByRole('button', { name: '编辑' }));

    const dialog = await screen.findByRole('dialog', { name: '编辑高级公理' });
    expect(within(dialog).getByText('保存后生成变更集，审核通过后才会生效。')).toBeInTheDocument();
    const fragment = within(dialog).getByRole('textbox', { name: 'Turtle 片段' });
    expect(fragment).toHaveValue('steel:MoltenSteel owl:disjointWith steel:Slag .');

    await user.click(within(dialog).getByRole('button', { name: '提交审核' }));
    expect(within(dialog).getByText('还没有修改任何内容。')).toBeInTheDocument();
    expect(api.calls('POST', EDITS)).toHaveLength(0);

    await user.clear(fragment);
    await user.type(fragment, 'steel:MoltenSteel owl:disjointWith steel:Slag, steel:Ladle .');
    await user.click(within(dialog).getByRole('button', { name: '提交审核' }));
    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toEqual({
      items: [
        {
          op: 'update',
          kind: 'axiom',
          targetElementId: 'el-axiom-disjoint',
          targetRevision: 2,
          fields: { turtle: 'steel:MoltenSteel owl:disjointWith steel:Slag, steel:Ladle .' },
        },
      ],
      apply: false,
    });
    expect(await screen.findByText('已提交审核，审核通过后生效')).toBeInTheDocument();
  });

  it('closes after rewriting an axiom that takes effect at once, although the merge raised its revision', async () => {
    const user = userEvent.setup();
    const api = expertServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: 'steel:MoltenSteel owl:disjointWith steel:Slag .' }));
    await user.click(within(await screen.findByRole('dialog', { name: '高级公理' })).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑高级公理' });
    const fragment = within(dialog).getByRole('textbox', { name: 'Turtle 片段' });
    await user.clear(fragment);
    await user.type(fragment, 'steel:MoltenSteel owl:disjointWith steel:Ladle .');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() => expect(api.calls('POST', EDITS)).toHaveLength(1));
    expect(api.calls('POST', EDITS)[0]?.body).toMatchObject({ items: [{ op: 'update', targetRevision: 2 }], apply: true });
    expect(await screen.findByText('已保存')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '编辑高级公理' })).not.toBeInTheDocument());
  });

  it('asks before discarding an unsaved fragment', async () => {
    const user = userEvent.setup();
    const api = expertServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    await user.click(await screen.findByRole('button', { name: '新建' }));
    await user.click(await screen.findByRole('menuitem', { name: '高级公理' }));
    const dialog = await screen.findByRole('dialog', { name: '新建高级公理' });
    await user.type(within(dialog).getByRole('textbox', { name: 'Turtle 片段' }), 'steel:Ladle owl:disjointWith steel:Slag .');

    await user.keyboard('{Escape}');
    const confirm = await screen.findByRole('dialog', { name: '放弃未保存的修改？' });
    await user.click(within(confirm).getByRole('button', { name: '继续编辑' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '放弃未保存的修改？' })).not.toBeInTheDocument());
    expect(within(dialog).getByRole('textbox', { name: 'Turtle 片段' })).toHaveValue('steel:Ladle owl:disjointWith steel:Slag .');

    await user.click(within(dialog).getByRole('button', { name: '取消' }));
    await user.click(within(await screen.findByRole('dialog', { name: '放弃未保存的修改？' })).getByRole('button', { name: '放弃修改' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建高级公理' })).not.toBeInTheDocument());
    expect(api.calls('POST', EDITS)).toHaveLength(0);
  });

  it('groups the axioms list by the element they belong to, with axioms about no element last', async () => {
    const user = userEvent.setup();
    expertServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(screen.getByRole('radio', { name: '高级公理' }));

    const steelGroup = await within(table).findByRole('rowgroup', { name: '钢水' });
    const bodies = within(table)
      .getAllByRole('rowgroup')
      .filter((group) => group.tagName === 'TBODY');
    expect(bodies.map((group) => group.querySelector('th')?.textContent)).toEqual(['钢包1 条', '钢水2 条', '不属于任何元素1 条']);
    expect(
      within(steelGroup)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['steel:MoltenSteel owl:disjointWith steel:Slag .', 'steel:MoltenSteel owl:hasKey ( steel:heatNumber ) .']);
    // The group names the subject, so the rows do not repeat it.
    expect(within(steelGroup).queryByText('所属：钢水')).not.toBeInTheDocument();
    const annotations = within(table).getByRole('rowgroup', { name: '不属于任何元素' });
    expect(within(annotations).getByRole('button', { name: /owl:imports/ })).toBeInTheDocument();
  });
});
