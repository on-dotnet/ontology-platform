import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { documentFixture, ontologyFixture } from '@/test/fixtures';
import { mockApi, problemResponse, renderApp, userWithRole } from '@/test/utils';

import { DOCUMENTS_POLL_MS, type DocumentInfo } from './api';
import { stepStates } from './document-progress';

afterEach(() => {
  vi.useRealTimers();
});

describe('document progress', () => {
  it('maps status and progress to step states', () => {
    expect(stepStates({ status: 'queued', progress: { step: 'parse', done: 0, total: 1 } })).toEqual([
      'pending',
      'pending',
      'pending',
      'pending',
      'pending',
    ]);
    expect(stepStates({ status: 'parsing', progress: { step: 'parse', done: 0, total: 1 } })[0]).toBe('active');
    // Parsing finished and extraction started before the extractor reports its first step.
    expect(stepStates({ status: 'extracting', progress: { step: 'parse', done: 1, total: 1 } })).toEqual([
      'done',
      'active',
      'pending',
      'pending',
      'pending',
    ]);
    expect(stepStates({ status: 'extracting', progress: { step: 'types', done: 1, total: 3 } })).toEqual([
      'done',
      'done',
      'active',
      'pending',
      'pending',
    ]);
    expect(stepStates({ status: 'failed', progress: { step: 'relations', done: 0, total: 2 } })).toEqual([
      'done',
      'done',
      'done',
      'failed',
      'pending',
    ]);
    expect(stepStates({ status: 'ready', progress: { step: 'changeset', done: 1, total: 1 } })).toEqual([
      'done',
      'done',
      'done',
      'done',
      'done',
    ]);
  });
});

describe('documents page', () => {
  it('polls documents in progress every 3 seconds and stops once they are done', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const states: DocumentInfo[] = [
      documentFixture({ status: 'extracting', progress: { step: 'terms', done: 2, total: 5 } }),
      documentFixture({ status: 'ready', changeSetId: 'cs-converter' }),
    ];
    let served = 0;
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/documents': () => {
        const document = states[Math.min(served, states.length - 1)];
        served += 1;
        return { items: [document], nextCursor: null };
      },
    });
    renderApp('/documents?ontology=onto-steel');

    const table = await screen.findByRole('table', { name: '资料列表' });
    expect(within(table).getByText('转炉炼钢工艺规程.docx')).toBeInTheDocument();
    expect(within(table).getByText('识别术语')).toBeInTheDocument();
    expect(within(table).getByText('2/5')).toBeInTheDocument();
    expect(api.calls('GET', '/api/documents')[0]?.query.get('ontologyId')).toBe('onto-steel');
    expect(api.calls('GET', '/api/documents')[0]?.query.get('limit')).toBe('50');

    await act(() => vi.advanceTimersByTimeAsync(DOCUMENTS_POLL_MS));
    const link = await within(table).findByRole('link', { name: '查看变更集' });
    expect(link).toHaveAttribute('href', '/review/cs-converter');
    expect(api.calls('GET', '/api/documents')).toHaveLength(2);

    await act(() => vi.advanceTimersByTimeAsync(DOCUMENTS_POLL_MS * 2));
    expect(api.calls('GET', '/api/documents')).toHaveLength(2);
  });

  it('explains why a document failed and retries it', async () => {
    const user = userEvent.setup();
    let retried = false;
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/documents': () => ({
        items: [
          retried
            ? documentFixture({ status: 'queued', progress: { step: 'parse', done: 0, total: 1 } })
            : documentFixture({ status: 'failed', errorCode: 'ai.unavailable', progress: { step: 'types', done: 0, total: 1 } }),
        ],
        nextCursor: null,
      }),
      'POST /api/documents/:id/retry': ({ params }) => {
        retried = true;
        return documentFixture({ id: params.id, status: 'queued' });
      },
    });
    renderApp('/documents?ontology=onto-steel');

    const table = await screen.findByRole('table', { name: '资料列表' });
    expect(within(table).getByText('AI 识别暂不可用，资料已保存，可稍后重试。')).toBeInTheDocument();
    expect(within(table).getByText('识别类型失败')).toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: '重试' }));

    await waitFor(() => expect(api.calls('POST', '/api/documents/doc-converter/retry')).toHaveLength(1));
    expect(await within(table).findByText('排队中')).toBeInTheDocument();
    expect(within(table).queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
    expect((await screen.findAllByText('已重新开始处理')).length).toBeGreaterThan(0);
  });

  it('says when nothing new was found and explains processing failures by code', async () => {
    mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/documents': () => ({
        items: [
          documentFixture({ id: 'doc-empty', filename: '目录.txt', status: 'ready', changeSetId: null }),
          documentFixture({
            id: 'doc-invalid',
            filename: '缺陷判定规范.xlsx',
            status: 'failed',
            errorCode: 'changeset.invalid_item',
            progress: { step: 'changeset', done: 0, total: 1 },
          }),
          documentFixture({
            id: 'doc-format',
            filename: '精炼规程.pdf',
            status: 'failed',
            errorCode: 'ai.invalid_output',
            progress: { step: 'terms', done: 1, total: 4 },
          }),
          documentFixture({
            id: 'doc-scan',
            filename: '扫描件.pdf',
            status: 'failed',
            errorCode: 'documents.unreadable',
            progress: { step: 'parse', done: 0, total: 1 },
          }),
          documentFixture({
            id: 'doc-hung',
            filename: '坏文件.pdf',
            status: 'failed',
            errorCode: 'documents.parse_timeout',
            progress: { step: 'parse', done: 0, total: 1 },
          }),
        ],
        nextCursor: null,
      }),
    });
    renderApp('/documents?ontology=onto-steel');

    const table = await screen.findByRole('table', { name: '资料列表' });
    const rowOf = (name: string) => within(table).getByText(name).closest('tr') as HTMLElement;
    expect(within(rowOf('目录.txt')).getByText('没有识别出新的内容')).toBeInTheDocument();
    expect(within(rowOf('目录.txt')).queryByRole('link')).not.toBeInTheDocument();
    expect(within(rowOf('缺陷判定规范.xlsx')).getByText('AI 识别出的内容不完整，没有生成变更集，请重试。')).toBeInTheDocument();
    expect(within(rowOf('缺陷判定规范.xlsx')).getByText('生成变更集失败')).toBeInTheDocument();
    expect(within(rowOf('精炼规程.pdf')).getByText('AI 返回的结果不符合要求，资料已保存，请稍后重试。')).toBeInTheDocument();
    expect(within(rowOf('扫描件.pdf')).getByText('没有从这份资料里读出文字，文件可能已损坏，或是转写后仍无文字的扫描件。请检查文件或上传可复制文字的版本。')).toBeInTheDocument();
    expect(within(rowOf('坏文件.pdf')).getByText('解析这份资料超时，文件可能已损坏。请检查文件，或另存一份后重新上传。')).toBeInTheDocument();
  });

  it('maps unknown failure codes to a generic reason', async () => {
    mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/documents': () => ({
        items: [documentFixture({ status: 'failed', errorCode: 'internal.something_new', progress: { step: 'parse', done: 0, total: 1 } })],
        nextCursor: null,
      }),
    });
    renderApp('/documents?ontology=onto-steel');
    expect(await screen.findByText('处理没有完成，请重试。')).toBeInTheDocument();
  });

  it('keeps the selected ontology in the URL and loads its documents', async () => {
    const user = userEvent.setup();
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture(), ontologyFixture({ id: 'onto-rolling', key: 'rolling', name: '热轧' })],
      'GET /api/documents': ({ query }) => ({
        items: query.get('ontologyId') === 'onto-rolling' ? [documentFixture({ id: 'doc-rolling', ontologyId: 'onto-rolling', filename: '热轧规程.pdf' })] : [],
        nextCursor: null,
      }),
    });
    const { router } = renderApp('/documents?ontology=onto-rolling');

    expect(await screen.findByText('热轧规程.pdf')).toBeInTheDocument();
    const selector = screen.getByRole('combobox', { name: '本体' });
    expect(selector).toHaveValue('onto-rolling');

    await user.selectOptions(selector, 'onto-steel');
    await waitFor(() => expect(router.state.location.search).toEqual({ ontology: 'onto-steel' }));
    expect(await screen.findByText('上传第一份资料：把文件拖到这里，或者')).toBeInTheDocument();
    expect(api.calls('GET', '/api/documents').some((request) => request.query.get('ontologyId') === 'onto-steel')).toBe(true);
  });

  it('offers more pages when the server returns a cursor', async () => {
    const user = userEvent.setup();
    const api = mockApi({
      'GET /api/ontologies': () => [ontologyFixture()],
      'GET /api/documents': ({ query }) =>
        query.get('cursor') === 'doc-first'
          ? { items: [documentFixture({ id: 'doc-second', filename: '第二页.md' })], nextCursor: null }
          : { items: [documentFixture({ id: 'doc-first', filename: '第一页.md' })], nextCursor: 'doc-first' },
    });
    renderApp('/documents?ontology=onto-steel');

    await screen.findByText('第一页.md');
    await user.click(screen.getByRole('button', { name: '加载更多' }));
    expect(await screen.findByText('第二页.md')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '加载更多' })).not.toBeInTheDocument();
    expect(api.calls('GET', '/api/documents')[1]?.query.get('cursor')).toBe('doc-first');
  });

  it('hides upload and retry from viewers but still shows the failure reason', async () => {
    mockApi(
      {
        'GET /api/ontologies': () => [ontologyFixture()],
        'GET /api/documents': () => ({
          items: [documentFixture({ status: 'failed', errorCode: 'documents.needs_ocr', progress: { step: 'parse', done: 0, total: 1 } })],
          nextCursor: null,
        }),
      },
      { user: userWithRole('viewer') },
    );
    renderApp('/documents?ontology=onto-steel');

    expect(await screen.findByText('这份资料是扫描件，暂时无法提取文字。请上传可复制文字的版本。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '上传资料' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });

  it('shows the no-access state when the server refuses the list', async () => {
    mockApi({
      'GET /api/ontologies': () => problemResponse(403, 'auth.forbidden'),
    });
    renderApp('/documents');
    expect(await screen.findByText('没有访问权限')).toBeInTheDocument();
  });
});
