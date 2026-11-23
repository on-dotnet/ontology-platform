import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { documentFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, renderApp, userWithRole } from '@/test/utils';

function file(name: string, size = 1024): File {
  const result = new File(['content'], name);
  Object.defineProperty(result, 'size', { value: size });
  return result;
}

const MB = 1024 * 1024;

describe('workbench upload', () => {
  it('rejects unsupported types and files over 20 MB before uploading anything', async () => {
    const api = mockApi({ 'GET /api/ontologies': () => [ontologyFixture()] });
    renderApp('/');

    const zone = (await screen.findByRole('button', { name: '选择文件' })).parentElement;
    expect(zone).not.toBeNull();
    fireEvent.drop(zone as HTMLElement, { dataTransfer: { files: [file('setup.exe'), file('规程.pdf', 21 * MB), file('空白.txt', 0)] } });

    const notice = await screen.findByRole('alert');
    expect(notice).toHaveTextContent('有 3 份资料没有上传');
    expect(notice).toHaveTextContent('setup.exe：不支持这种文件类型，请上传 docx、xlsx、pdf、md 或 txt 文件。');
    expect(notice).toHaveTextContent('规程.pdf：文件超过 20 MB，请拆分或压缩后再上传。');
    expect(notice).toHaveTextContent('空白.txt：文件是空的');
    expect(api.calls('POST', '/api/documents')).toHaveLength(0);
  });

  it('accepts a file of exactly 20 MB and uploads it into the only ontology', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const append = vi.spyOn(FormData.prototype, 'append');
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'POST /api/documents': () => documentFixture({ status: 'queued' }),
      'GET /api/documents': () => ({ items: [documentFixture({ status: 'queued' })], nextCursor: null }),
    });
    const { router } = renderApp('/');

    await user.upload(await screen.findByLabelText('选择要上传的资料文件'), file('板坯连铸.md', 20 * MB));

    await waitFor(() => expect(api.calls('POST', '/api/documents')).toHaveLength(1));
    expect(append).toHaveBeenCalledWith('ontologyId', 'onto-steel');
    expect(append).toHaveBeenCalledWith('file', expect.any(File), '板坯连铸.md');
    await waitFor(() => expect(router.state.location.pathname).toBe('/documents'));
    expect(router.state.location.search).toEqual({ ontology: 'onto-steel' });
  });

  it('asks for an ontology name first when there is none, then uploads into the new ontology', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const append = vi.spyOn(FormData.prototype, 'append');
    const created = ontologyFixture({ id: 'onto-new', key: 'ontology-abc123', name: '钢铁冶金', entityTypeCount: 0 });
    let ontologies: ReturnType<typeof ontologyFixture>[] = [];
    const api = mockApi({
      'GET /api/ontologies': () => ontologies,
      'POST /api/ontologies': () => {
        ontologies = [created];
        return created;
      },
      'POST /api/documents': () => documentFixture({ ontologyId: created.id, status: 'queued' }),
      'GET /api/documents': () => ({ items: [], nextCursor: null }),
    });
    const { router } = renderApp('/');

    await user.upload(await screen.findByLabelText('选择要上传的资料文件'), file('热轧带钢工艺规程.docx'));

    const dialog = await screen.findByRole('dialog', { name: '先给本体起个名字' });
    expect(api.calls('POST', '/api/documents')).toHaveLength(0);

    // Submitting without a name is caught on the client.
    await user.click(within(dialog).getByRole('button', { name: '创建本体' }));
    expect(within(dialog).getByText('请填写本体名称后再创建。')).toBeInTheDocument();
    expect(api.calls('POST', '/api/ontologies')).toHaveLength(0);

    await user.type(within(dialog).getByRole('textbox', { name: /本体名称/ }), '钢铁冶金');
    await user.click(within(dialog).getByRole('button', { name: '创建本体' }));

    await waitFor(() => expect(api.calls('POST', '/api/documents')).toHaveLength(1));
    expect(api.calls('POST', '/api/ontologies')[0]?.body).toEqual({ name: '钢铁冶金' });
    expect(append).toHaveBeenCalledWith('ontologyId', 'onto-new');
    await waitFor(() => expect(router.state.location.search).toEqual({ ontology: 'onto-new' }));
    expect(screen.queryByRole('dialog', { name: '先给本体起个名字' })).not.toBeInTheDocument();
  });

  it('explains which role can upload instead of showing the upload area to viewers', async () => {
    mockApi({ 'GET /api/ontologies': () => [ontologyFixture()] }, { user: userWithRole('viewer') });
    renderApp('/');

    expect(await screen.findByText('上传资料需要“编辑者”角色，请联系平台管理员开通。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '选择文件' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('选择要上传的资料文件')).not.toBeInTheDocument();
  });
});

describe('workbench overview', () => {
  it('shows the summary counts and recent activity from the API', async () => {
    mockApi({
      'GET /api/workbench/summary': () => ({
        pendingChangeSets: 3,
        entityTypes: 17,
        processingDocuments: 0,
        recentActivity: [
          {
            id: 'act-1',
            action: 'changeset.merged',
            occurredAt: new Date().toISOString(),
            actorName: '李工',
            targetType: 'change_set',
            targetId: 'cs-converter',
          },
          { id: 'act-2', action: 'something.new', occurredAt: new Date().toISOString(), actorName: null, targetType: null, targetId: null },
          {
            id: 'act-3',
            action: 'ontology.imported',
            occurredAt: new Date().toISOString(),
            actorName: '张工',
            targetType: 'ontology',
            targetId: 'onto-steel',
          },
        ],
      }),
    });
    renderApp('/');

    const overview = await screen.findByRole('region', { name: '概览' });
    await within(overview).findByText('17');
    expect(within(overview).getByText('3')).toBeInTheDocument();
    expect(within(overview).getByText('0')).toBeInTheDocument();
    const activity = within(overview).getByRole('list', { name: '最近动态' });
    expect(activity).toHaveTextContent('李工 合并了变更集');
    expect(activity).toHaveTextContent('平台 进行了操作');
    expect(activity).toHaveTextContent('张工 导入了 OWL 文件');
    expect(within(activity).getAllByRole('link', { name: '查看' }).map((link) => link.getAttribute('href'))).toEqual([
      '/review/cs-converter',
      '/ontology?ontology=onto-steel',
    ]);
  });

  it('warns that AI analysis is unavailable and what still works', async () => {
    mockApi({ 'GET /api/ai/status': () => ({ configured: true, reachable: false, model: 'gpt-test' }) });
    renderApp('/');

    const title = await screen.findByText('AI 识别暂不可用');
    expect(title.closest('[role="status"]')).toHaveTextContent('资料仍可上传和保存；识别失败的资料可在 AI 恢复后重试。');
    // The top bar shows the same state as a "!" button.
    expect(screen.getByRole('button', { name: 'AI 识别暂不可用' })).toBeInTheDocument();
  });

  it('shows no AI warning when the service is available', async () => {
    mockApi();
    renderApp('/');
    await screen.findByRole('region', { name: '概览' });
    expect(screen.queryByText('AI 识别暂不可用')).not.toBeInTheDocument();
    expect(screen.queryByText('AI 服务尚未配置')).not.toBeInTheDocument();
  });
});
