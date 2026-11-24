import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { changeSetFixture, importResultFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import type { ImportResult } from './api';

afterEach(() => {
  vi.restoreAllMocks();
});

function owlFile(name = 'steel.ttl', size = 2048): File {
  const file = new File(['@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'], name, { type: 'text/turtle' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

function ontologyServer(extra: Record<string, RouteHandler> = {}, user?: ReturnType<typeof userWithRole>) {
  return mockApi(
    {
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/ontologies/:id/elements': () => [],
      'GET /api/change-sets/:id': ({ params }) => changeSetFixture([], { id: params.id, source: 'import', documentId: null, title: '导入：steel.ttl' }),
      ...extra,
    },
    user ? { user } : {},
  );
}

async function openImportDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '更多操作' }));
  await user.click(await screen.findByRole('menuitem', { name: '导入 OWL' }));
  return screen.findByRole('dialog', { name: '导入 OWL 到“钢铁冶金”' });
}

describe('import OWL into the current ontology', () => {
  it('uploads the file, summarizes the change set with warnings and goes to review', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const append = vi.spyOn(FormData.prototype, 'append');
    const result: ImportResult = importResultFixture({
      counts: { create: 12, update: 3, delete: 1, restore: 2 },
      warnings: [
        { code: 'non_standard', count: 2 },
        { code: 'lost_list', count: 1 },
      ],
    });
    const api = ontologyServer({ 'POST /api/ontologies/:id/import': () => result });
    const { router } = renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openImportDialog(user);
    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile());
    expect(within(dialog).getByText('steel.ttl')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    const summary = await screen.findByRole('dialog', { name: '文件已导入' });
    expect(api.calls('POST', '/api/ontologies/onto-steel/import')).toHaveLength(1);
    expect(append).toHaveBeenCalledWith('file', expect.any(File), 'steel.ttl');

    const counts = within(summary).getByText('新增').closest('dl');
    expect(counts).toHaveTextContent('新增12');
    expect(counts).toHaveTextContent('修改3');
    expect(counts).toHaveTextContent('删除1');
    expect(counts).toHaveTextContent('恢复2');
    const warnings = within(summary).getByRole('list', { name: '需要注意的内容' });
    expect(warnings).toHaveTextContent('2 条公理在 Protégé 中会被改写');
    // The visible text names the warning; the icon only adds the explanation.
    const [rewritten] = within(warnings).getAllByRole('listitem');
    expect(within(rewritten as HTMLElement).getByRole('button', { name: '注意' })).toHaveAccessibleDescription(
      '在 Protégé 中打开时，这些公理会被改写成等价的写法。平台按原样保留，导出时不变。',
    );
    // Values the review will not get are a yellow notice, not a line in the list.
    expect(warnings).not.toHaveTextContent('枚举取值');
    const lostValues = within(summary).getByText('1 条规则的枚举取值被 Protégé 丢掉了').closest('[role="status"]');
    expect(lostValues).toHaveClass('bg-warning-soft');

    const goReview = within(summary).getByRole('link', { name: '去审核' });
    expect(goReview).toHaveAttribute('href', '/review/cs-import');
    await user.click(goReview);
    await waitFor(() => expect(router.state.location.pathname).toBe('/review/cs-import'));
  });

  it('says when the file matches the working version and offers no review', async () => {
    const user = userEvent.setup({ applyAccept: false });
    ontologyServer({
      'POST /api/ontologies/:id/import': () => importResultFixture({ changeSetId: null, counts: { create: 0, update: 0, delete: 0, restore: 0 } }),
    });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openImportDialog(user);
    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile());
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    const summary = await screen.findByRole('dialog', { name: '没有发现差异' });
    expect(summary).toHaveTextContent('文件与工作版本没有差异，没有生成变更集。');
    expect(within(summary).queryByRole('link', { name: '去审核' })).not.toBeInTheDocument();
    expect(within(summary).queryByText('新增')).not.toBeInTheDocument();
  });

  it('names the line of a syntax error and asks for a file before sending anything', async () => {
    const user = userEvent.setup({ applyAccept: false });
    let line: number | null = 12;
    const api = ontologyServer({
      // The server never knows the column.
      'POST /api/ontologies/:id/import': () => problemResponse(422, 'import.parse_error', { line, column: null }),
    });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openImportDialog(user);
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));
    expect(within(dialog).getByText('请选择要导入的文件')).toBeInTheDocument();
    expect(api.calls('POST', '/api/ontologies/onto-steel/import')).toHaveLength(0);

    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile('broken.ttl'));
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('文件没有导入');
    expect(alert).toHaveTextContent('文件第 12 行有语法错误，请修正后重新导入。');
    expect(alert).not.toHaveTextContent('Backend detail');

    // A file the parser cannot place (RDF/XML, say) gets the message without a line.
    line = null;
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));
    await waitFor(() => expect(api.calls('POST', '/api/ontologies/onto-steel/import')).toHaveLength(2));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('文件有语法错误，请修正后重新导入。');
    expect(within(dialog).getByRole('alert')).not.toHaveTextContent('第 12 行');
  });

  it('refuses a file over 5 MB without sending it', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const api = ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openImportDialog(user);
    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile('large.ttl', 5 * 1024 * 1024 + 1));
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    expect(await within(dialog).findByText('文件超过 5 MB，请拆分后再导入。')).toBeInTheDocument();
    expect(api.calls('POST', '/api/ontologies/onto-steel/import')).toHaveLength(0);
  });

  it('maps an unsupported format to a localized message', async () => {
    const user = userEvent.setup({ applyAccept: false });
    ontologyServer({ 'POST /api/ontologies/:id/import': () => problemResponse(415, 'import.unsupported_format') });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const dialog = await openImportDialog(user);
    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile('notes.xml'));
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('这不是 Turtle 或 RDF/XML 文件');
  });
});

describe('create an ontology from an OWL file', () => {
  it('imports into a new ontology from the empty page and switches to it', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const append = vi.spyOn(FormData.prototype, 'append');
    const created = ontologyFixture({ id: 'onto-pizza', key: 'pizza', name: '披萨' });
    let ontologies: ReturnType<typeof ontologyFixture>[] = [];
    const api = mockApi({
      'GET /api/ontologies': () => ontologies,
      'GET /api/ontologies/:id/elements': () => [],
      'GET /api/ontologies/:id/graph': () => ({ nodes: [], edges: [] }),
      'POST /api/ontologies/import': () => {
        ontologies = [created];
        return importResultFixture({ ontology: created, changeSetId: 'cs-pizza' });
      },
    });
    const { router } = renderApp('/ontology?view=list');

    await user.click(await screen.findByRole('button', { name: '导入 OWL 文件' }));
    const dialog = await screen.findByRole('dialog', { name: '新建本体' });
    expect(within(dialog).getByRole('radio', { name: '从 OWL 文件导入' })).toBeChecked();

    await user.upload(within(dialog).getByLabelText('选择 OWL 文件'), owlFile('pizza.owl'));
    await user.type(within(dialog).getByRole('textbox', { name: '本体名称' }), '披萨');
    await user.click(within(dialog).getByRole('button', { name: '导入文件' }));

    const summary = await screen.findByRole('dialog', { name: '已创建本体“披萨”' });
    expect(api.calls('POST', '/api/ontologies/import')).toHaveLength(1);
    expect(append).toHaveBeenCalledWith('file', expect.any(File), 'pizza.owl');
    expect(append).toHaveBeenCalledWith('name', '披萨');
    expect(within(summary).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-pizza');
    await waitFor(() => expect(router.state.location.search).toEqual({ view: 'list', ontology: 'onto-pizza' }));
  });

  it('offers a blank ontology or an import from the menu and creates the blank one', async () => {
    const user = userEvent.setup();
    const created = ontologyFixture({ id: 'onto-new', key: 'new', name: '轧钢' });
    const api = ontologyServer({ 'POST /api/ontologies': () => created });
    renderApp('/ontology?ontology=onto-steel&view=list');

    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '新建本体' }));
    const dialog = await screen.findByRole('dialog', { name: '新建本体' });
    expect(within(dialog).getByRole('radio', { name: '空白本体' })).toBeChecked();

    await user.type(within(dialog).getByRole('textbox', { name: /本体名称/ }), '轧钢');
    await user.click(within(dialog).getByRole('button', { name: '创建本体' }));

    await waitFor(() => expect(api.calls('POST', '/api/ontologies')).toHaveLength(1));
    expect(api.calls('POST', '/api/ontologies')[0]?.body).toEqual({ name: '轧钢' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建本体' })).not.toBeInTheDocument());
  });
});

describe('import entry points', () => {
  it('hides import and create for viewers', async () => {
    const user = userEvent.setup();
    ontologyServer({}, userWithRole('viewer'));
    renderApp('/ontology?ontology=onto-steel&view=list');

    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    expect(await screen.findByRole('menuitem', { name: '导出 Turtle' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: '导入 OWL' })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: '新建本体' })).not.toBeInTheDocument();
  });

  it('shows no import button on the empty page for viewers', async () => {
    mockApi({ 'GET /api/ontologies': () => [] }, { user: userWithRole('viewer') });
    renderApp('/ontology');

    expect(await screen.findByText('还没有本体')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '导入 OWL 文件' })).not.toBeInTheDocument();
  });

  it('keeps the upload dialog to naming the ontology for waiting documents', async () => {
    const user = userEvent.setup({ applyAccept: false });
    mockApi({ 'GET /api/ontologies': () => [] });
    renderApp('/');

    await user.upload(await screen.findByLabelText('选择要上传的资料文件'), new File(['text'], '规程.docx'));
    const dialog = await screen.findByRole('dialog', { name: '先给本体起个名字' });
    expect(within(dialog).queryByRole('radio', { name: '从 OWL 文件导入' })).not.toBeInTheDocument();
  });
});
