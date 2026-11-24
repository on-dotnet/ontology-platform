import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { UserInfo } from '@/features/auth/api';
import type { OntologySummary } from '@/features/ontologies/api';
import {
  assistantRequestFixture,
  changeSetFixture,
  elementDetailFixture,
  elementFixture,
  impactFixture,
  itemFixture,
  ontologyFixture,
} from '@/test/fixtures';
import { jsonResponse, mockApi, problemResponse, renderApp, userWithRole, type RouteHandler } from '@/test/utils';

import { ASSISTANT_POLL_MS, type AssistantRequest, type AssistantRequestCreate } from './api';
import { failureReason, stepStates } from './request-entry';

afterEach(() => {
  vi.useRealTimers();
});

const steel = ontologyFixture();
const copper = ontologyFixture({ id: 'onto-copper', key: 'copper', name: '铜冶炼' });
const moltenSteel = elementFixture();

interface ServerOptions {
  ontologies?: OntologySummary[];
  /** Requests already made, newest first. */
  requests?: AssistantRequest[];
  /** What polling a request answers; by default the request as the list holds it. */
  poll?: (id: string) => unknown;
  user?: UserInfo;
  extra?: Record<string, RouteHandler>;
}

function assistantServer({ ontologies = [steel], requests = [], poll, user, extra = {} }: ServerOptions = {}) {
  const list = [...requests];
  let created = 0;
  return mockApi(
    {
      'GET /api/ontologies': () => ontologies,
      'GET /api/ontologies/:id/assistant/requests': ({ params }) => list.filter((request) => request.ontologyId === params.id),
      'POST /api/ontologies/:id/assistant/requests': ({ params, body }) => {
        created += 1;
        const { message, context } = body as AssistantRequestCreate;
        const request = assistantRequestFixture({
          id: `req-new-${created}`,
          ontologyId: params.id,
          message,
          context: { page: context.page, elementId: context.elementId ?? null },
        });
        list.unshift(request);
        return jsonResponse(request, 201);
      },
      'GET /api/assistant/requests/:id': ({ params }) =>
        poll ? poll(params.id ?? '') : list.find((request) => request.id === params.id),
      'GET /api/change-sets/:id': ({ params }) =>
        changeSetFixture(
          [
            itemFixture(),
            itemFixture({ id: 'item-update', op: 'update', targetElementId: 'el-molten-steel', tempRef: null, confidence: 0.7 }),
          ],
          { id: params.id, title: '助手：给钢包加一个属性', source: 'ai_assistant', documentId: null },
        ),
      ...extra,
    },
    user ? { user } : {},
  );
}

/** Elements by ontology: the molten steel belongs to the steel ontology only. */
const elementRoutes: Record<string, RouteHandler> = {
  'GET /api/ontologies/:id/elements': ({ params }) => [moltenSteel].filter((element) => element.ontologyId === params.id),
  'GET /api/ontologies/:id/elements/:elementId': ({ params }) =>
    params.id === moltenSteel.ontologyId && params.elementId === moltenSteel.id
      ? elementDetailFixture(moltenSteel)
      : problemResponse(404, 'element.not_found'),
  'GET /api/ontologies/:id/elements/:elementId/impact': ({ params }) => impactFixture(params.elementId ?? ''),
};

async function openAssistant(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('navigation', { name: '主导航' });
  await user.keyboard('{Control>}j{/Control}');
  return screen.findByRole('complementary', { name: 'AI 助手' });
}

function entries(list: HTMLElement): HTMLElement[] {
  return within(list)
    .getAllByRole('listitem')
    .filter((item) => item.parentElement === list);
}

/** The panel's live region, which says when a request ends. */
function liveRegion(panel: HTMLElement): HTMLElement {
  const region = panel.querySelector<HTMLElement>('[aria-live="polite"]');
  if (!region) throw new Error('No live region');
  return region;
}

const FIELD = '告诉 AI 助手要做的修改';
const STEEL_REQUESTS = '/api/ontologies/onto-steel/assistant/requests';

describe('assistant progress', () => {
  it('maps status and step to step states', () => {
    expect(stepStates({ status: 'queued', step: null })).toEqual(['pending', 'pending', 'pending']);
    expect(stepStates({ status: 'running', step: 'context' })).toEqual(['active', 'pending', 'pending']);
    expect(stepStates({ status: 'running', step: 'changeset' })).toEqual(['done', 'done', 'active']);
    expect(stepStates({ status: 'succeeded', step: 'changeset' })).toEqual(['done', 'done', 'done']);
  });

  it('tells configuration problems apart from passing outages', () => {
    expect(failureReason('ai.not_configured')).toBe('not_configured');
    expect(failureReason('ai.unavailable')).toBe('unavailable');
    expect(failureReason('ai.invalid_output')).toBe('invalid_output');
    expect(failureReason('internal.error')).toBe('other');
    expect(failureReason(null)).toBe('other');
  });
});

describe('assistant panel', () => {
  it('sends an instruction with the page, polls it every 2 seconds and shows the proposed changes with a link to review', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    // The server moves on only when the test says so, so an extra poll cannot skip a state.
    let state: Partial<AssistantRequest> = { status: 'running', step: 'model' };
    const api = assistantServer({ poll: (id) => assistantRequestFixture({ id, ...state }) });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const field = await within(panel).findByRole('textbox', { name: FIELD });
    await waitFor(() => expect(field).toHaveFocus());
    expect(within(panel).getByText('当前页面：探索')).toBeInTheDocument();
    expect(within(panel).getByText('钢铁冶金')).toBeInTheDocument();
    expect(await within(panel).findByText('告诉 AI 助手你想怎样修改本体')).toBeInTheDocument();

    await user.type(field, '给钢包加一个属性');
    await user.keyboard('{Enter}');

    const list = await within(panel).findByRole('list', { name: '最近的请求' });
    // Right after it appears the request is queued and not polled yet: polling waits 2 seconds.
    expect(api.calls('GET', '/api/assistant/requests/req-new-1')).toHaveLength(0);
    expect(list).toHaveTextContent('排队中');
    expect(within(list).getByRole('list', { name: '处理进度' })).toHaveTextContent('读取本体：未开始');
    expect(within(list).getByText('给钢包加一个属性')).toBeInTheDocument();
    expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(1);
    expect(api.calls('POST', STEEL_REQUESTS)[0]?.body).toEqual({ message: '给钢包加一个属性', context: { page: 'explore', elementId: null } });
    await waitFor(() => expect(field).toHaveValue(''));
    // The list is fetched again after adding the request, so an older answer cannot drop it.
    await waitFor(() => expect(api.calls('GET', STEEL_REQUESTS)).toHaveLength(2));

    await act(() => vi.advanceTimersByTimeAsync(ASSISTANT_POLL_MS));
    await waitFor(() => expect(within(list).getByRole('list', { name: '处理进度' })).toHaveTextContent('调用模型：进行中'));
    expect(within(list).getByRole('list', { name: '处理进度' })).toHaveTextContent('读取本体：已完成');
    expect(list).toHaveTextContent('正在处理');
    expect(liveRegion(panel).textContent).toBe('');

    state = {
      status: 'succeeded',
      step: 'changeset',
      reply: '已为钢包新增属性“容量”，并补充了钢水的定义。',
      changeSetId: 'cs-assistant',
      finishedAt: '2026-11-20T08:01:00Z',
    };
    await act(() => vi.advanceTimersByTimeAsync(ASSISTANT_POLL_MS));
    expect(await within(list).findByText('已为钢包新增属性“容量”，并补充了钢水的定义。')).toBeInTheDocument();
    expect(within(list).getByText('AI 建议')).toBeInTheDocument();
    expect(within(list).queryByRole('list', { name: '处理进度' })).not.toBeInTheDocument();
    expect(await within(list).findByText('变更集共 2 项：新建 1 项、修改 1 项')).toBeInTheDocument();
    expect(within(list).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-assistant');
    expect(within(list).queryByText(/无法执行/)).not.toBeInTheDocument();
    expect(liveRegion(panel)).toHaveTextContent('请求已完成');

    // Finished requests are no longer polled.
    const polls = api.calls('GET', '/api/assistant/requests/req-new-1').length;
    await act(() => vi.advanceTimersByTimeAsync(ASSISTANT_POLL_MS * 3));
    expect(api.calls('GET', '/api/assistant/requests/req-new-1')).toHaveLength(polls);
  });

  it('sends nothing on an Enter that confirms an input method candidate, and stays open on its Escape', async () => {
    const user = userEvent.setup();
    const api = assistantServer();
    renderApp('/explore');

    const panel = await openAssistant(user);
    const field = await within(panel).findByRole('textbox', { name: FIELD });
    await user.type(field, '新增对象类型');

    fireEvent.keyDown(field, { key: 'Enter', isComposing: true });
    fireEvent.keyDown(field, { key: 'Enter', keyCode: 229 });
    fireEvent.keyDown(field, { key: 'Escape', isComposing: true });
    fireEvent.keyDown(field, { key: 'Escape', keyCode: 229 });
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(0);
    expect(field).toHaveValue('新增对象类型');
    expect(screen.getByRole('complementary', { name: 'AI 助手' })).toBeInTheDocument();

    // A plain Enter does send.
    fireEvent.keyDown(field, { key: 'Enter' });
    await waitFor(() => expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(1));
  });

  it('takes the element last opened on the ontology page as context', async () => {
    const user = userEvent.setup();
    const api = assistantServer({ extra: elementRoutes });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: '钢水' }));
    await screen.findByRole('dialog', { name: '钢水' });
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '钢水' })).not.toBeInTheDocument());

    const panel = await openAssistant(user);
    expect(within(panel).getByText('当前页面：本体')).toBeInTheDocument();
    expect(await within(panel).findByText('选中')).toBeInTheDocument();
    expect(within(panel).getByText('钢水')).toBeInTheDocument();

    await user.type(within(panel).getByRole('textbox', { name: FIELD }), '把钢水的英文名改成 Liquid steel');
    await user.click(within(panel).getByRole('button', { name: '发送' }));

    await waitFor(() => expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(1));
    expect(api.calls('POST', STEEL_REQUESTS)[0]?.body).toEqual({
      message: '把钢水的英文名改成 Liquid steel',
      context: { page: 'ontology', elementId: 'el-molten-steel' },
    });
  });

  it('leaves the element out after switching to another ontology', async () => {
    const user = userEvent.setup();
    const api = assistantServer({ ontologies: [steel, copper], extra: elementRoutes });
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: '钢水' }));
    await screen.findByRole('dialog', { name: '钢水' });
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '钢水' })).not.toBeInTheDocument());
    await user.selectOptions(screen.getByRole('combobox', { name: '本体' }), '铜冶炼');

    const panel = await openAssistant(user);
    expect(await within(panel).findByText('铜冶炼')).toBeInTheDocument();
    expect(within(panel).queryByText('选中')).not.toBeInTheDocument();

    await user.type(within(panel).getByRole('textbox', { name: FIELD }), '新增对象类型“阳极板”{Enter}');
    await waitFor(() => expect(api.calls('POST', '/api/ontologies/onto-copper/assistant/requests')).toHaveLength(1));
    expect(api.calls('POST', '/api/ontologies/onto-copper/assistant/requests')[0]?.body).toEqual({
      message: '新增对象类型“阳极板”',
      context: { page: 'ontology', elementId: null },
    });
    // The steel element was never offered as the copper ontology's context.
    expect(api.calls('GET', '/api/ontologies/onto-copper/elements/el-molten-steel')).toHaveLength(0);
    expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(0);
  });

  it("works on the change set's ontology on its review page", async () => {
    const user = userEvent.setup();
    const api = assistantServer({
      ontologies: [steel, copper],
      extra: {
        'GET /api/change-sets/:id': ({ params }) =>
          changeSetFixture([itemFixture()], { id: params.id, ontologyId: 'onto-copper', source: 'manual', documentId: null }),
        'GET /api/ontologies/:id/elements': () => [],
      },
    });
    renderApp('/review/cs-copper');

    const panel = await openAssistant(user);
    expect(await within(panel).findByText('铜冶炼')).toBeInTheDocument();
    expect(within(panel).queryByText('钢铁冶金')).not.toBeInTheDocument();
    expect(within(panel).getByText('当前页面：审核')).toBeInTheDocument();

    await user.type(within(panel).getByRole('textbox', { name: FIELD }), '把阳极板改名为阳极{Enter}');
    await waitFor(() => expect(api.calls('POST', '/api/ontologies/onto-copper/assistant/requests')).toHaveLength(1));
    expect(api.calls('POST', '/api/ontologies/onto-copper/assistant/requests')[0]?.body).toEqual({
      message: '把阳极板改名为阳极',
      context: { page: 'review', elementId: null },
    });
    expect(api.calls('GET', STEEL_REQUESTS)).toHaveLength(0);
    expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(0);
  });

  it('waits for the change set before choosing an ontology, and does not guess when it fails to load', async () => {
    const user = userEvent.setup();
    const api = assistantServer({
      ontologies: [steel, copper],
      extra: {
        'GET /api/change-sets/:id': ({ params }) =>
          params.id === 'cs-missing' ? problemResponse(404, 'changeset.not_found') : new Promise<Response>(() => undefined),
        'GET /api/ontologies/:id/elements': () => [],
      },
    });
    const { router } = renderApp('/review/cs-slow');

    let panel = await openAssistant(user);
    expect(within(panel).getByRole('status')).toHaveTextContent('正在加载…');
    expect(within(panel).queryByText('钢铁冶金')).not.toBeInTheDocument();
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument();

    await act(() => router.navigate({ to: '/review/$changeSetId', params: { changeSetId: 'cs-missing' } }));
    panel = await screen.findByRole('complementary', { name: 'AI 助手' });
    expect(await within(panel).findByText('无法确定要修改哪个本体')).toBeInTheDocument();
    expect(within(panel).queryByText('钢铁冶金')).not.toBeInTheDocument();
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument();
    expect(api.calls('GET', STEEL_REQUESTS)).toHaveLength(0);
  });

  it('says when the assistant only replied, and how many proposed changes it ignored', async () => {
    const user = userEvent.setup();
    const api = assistantServer({
      requests: [
        assistantRequestFixture({
          id: 'req-question',
          message: '钢包和钢水是什么关系？',
          status: 'succeeded',
          step: 'changeset',
          reply: '这类问题将在后续版本支持。',
        }),
        assistantRequestFixture({
          id: 'req-partly',
          message: '删除所有属性并新增“炉次”',
          status: 'succeeded',
          step: 'changeset',
          reply: '已新增对象类型“炉次”。',
          dropped: 2,
          changeSetId: 'cs-partly',
        }),
      ],
    });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const list = await within(panel).findByRole('list', { name: '最近的请求' });
    const [question, partly] = entries(list);
    if (!question || !partly) throw new Error('Expected two requests');

    expect(question).toHaveTextContent('钢包和钢水是什么关系？');
    expect(question).toHaveTextContent('这类问题将在后续版本支持。');
    expect(question).toHaveTextContent('没有生成修改，本体保持不变。');
    expect(within(question).queryByRole('link', { name: '去审核' })).not.toBeInTheDocument();
    expect(question).not.toHaveTextContent('无法执行');

    expect(partly).toHaveTextContent('已新增对象类型“炉次”。');
    expect(partly).toHaveTextContent('有 2 项无法执行，已忽略');
    expect(within(partly).getByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/cs-partly');
    await waitFor(() => expect(api.calls('GET', '/api/change-sets/cs-partly')).toHaveLength(1));
    // Finished requests from the list are not polled.
    expect(api.requests.some((request) => request.path.startsWith('/api/assistant/requests/'))).toBe(false);
  });

  it('explains past failures by their cause without reading them out, and retries with the same words and context', async () => {
    const user = userEvent.setup();
    const api = assistantServer({
      requests: [
        assistantRequestFixture({
          id: 'req-unavailable',
          message: '给钢包加一个属性“容量”',
          context: { page: 'ontology', elementId: 'el-ladle' },
          status: 'failed',
          step: 'model',
          errorCode: 'ai.unavailable',
        }),
        assistantRequestFixture({ id: 'req-unconfigured', message: '新增对象类型“炉次”', status: 'failed', step: 'model', errorCode: 'ai.not_configured' }),
      ],
    });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const list = await within(panel).findByRole('list', { name: '最近的请求' });
    const [unavailable, unconfigured] = entries(list);
    if (!unavailable || !unconfigured) throw new Error('Expected two failures');
    expect(unavailable).toHaveTextContent('AI 助手暂不可用');
    expect(unavailable).toHaveTextContent('本体没有被修改，请稍后重试。');
    expect(unconfigured).toHaveTextContent('AI 服务尚未配置');
    expect(unconfigured).toHaveTextContent('请联系平台管理员配置模型服务后重试。');
    expect(list).not.toHaveTextContent('ai.unavailable');
    expect(within(panel).queryAllByRole('alert')).toHaveLength(0);

    await user.click(within(unavailable).getByRole('button', { name: '重试' }));

    await waitFor(() => expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(1));
    expect(api.calls('POST', STEEL_REQUESTS)[0]?.body).toEqual({
      message: '给钢包加一个属性“容量”',
      context: { page: 'ontology', elementId: 'el-ladle' },
    });
    // The new attempt is listed first, in progress; the failed one stays below it.
    await waitFor(() => expect(entries(list)).toHaveLength(3));
    expect(entries(list)[0]).toHaveTextContent('排队中');
    expect(entries(list)[1]).toHaveTextContent('AI 助手暂不可用');
    // The composer was not busy while the retry was sent.
    expect(within(panel).getByRole('button', { name: '发送' })).not.toHaveAttribute('aria-busy');
  });

  it('shows why a retry was not sent with the request it retried', async () => {
    const user = userEvent.setup();
    assistantServer({
      requests: [
        assistantRequestFixture({ id: 'req-unavailable', message: '新增对象类型“炉次”', status: 'failed', step: 'model', errorCode: 'ai.unavailable' }),
      ],
      extra: { 'POST /api/ontologies/:id/assistant/requests': () => problemResponse(403, 'auth.forbidden') },
    });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const list = await within(panel).findByRole('list', { name: '最近的请求' });
    const [failed] = entries(list);
    if (!failed) throw new Error('Expected the failed request');
    await user.click(within(failed).getByRole('button', { name: '重试' }));

    const alert = await within(failed).findByRole('alert');
    expect(alert).toHaveTextContent('没有重新提交');
    expect(alert).toHaveTextContent('你没有执行此操作的权限，请联系平台管理员。');
    // Only there: the composer above the list shows no failure.
    expect(within(panel).getAllByRole('alert')).toHaveLength(1);
    expect(within(panel).queryByText('请求没有发出')).not.toBeInTheDocument();
  });

  it('stops following a request the server no longer gives out, and says so', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = assistantServer({
      requests: [assistantRequestFixture({ id: 'req-gone', status: 'running', step: 'model' })],
      poll: () => problemResponse(404, 'assistant.not_found'),
    });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const list = await within(panel).findByRole('list', { name: '最近的请求' });
    expect(list).toHaveTextContent('调用模型：进行中');

    await act(() => vi.advanceTimersByTimeAsync(ASSISTANT_POLL_MS));
    expect(await within(list).findByText('无法获取这条请求的进度')).toBeInTheDocument();
    expect(list).toHaveTextContent('这条请求不存在，或不是你发起的。');
    expect(within(list).queryByRole('list', { name: '处理进度' })).not.toBeInTheDocument();
    expect(liveRegion(panel)).toHaveTextContent('无法获取请求的结果');

    const polls = api.calls('GET', '/api/assistant/requests/req-gone').length;
    expect(polls).toBe(1);
    await act(() => vi.advanceTimersByTimeAsync(ASSISTANT_POLL_MS * 3));
    expect(api.calls('GET', '/api/assistant/requests/req-gone')).toHaveLength(polls);
  });

  it('checks the instruction before sending and keeps it when sending fails', async () => {
    const user = userEvent.setup();
    const api = assistantServer({
      extra: { 'POST /api/ontologies/:id/assistant/requests': () => problemResponse(403, 'auth.forbidden') },
    });
    renderApp('/explore');

    const panel = await openAssistant(user);
    const field = await within(panel).findByRole('textbox', { name: FIELD });

    await user.click(field);
    await user.keyboard('{Enter}');
    expect(within(panel).getByText('请先写下要让 AI 助手做的修改。')).toBeInTheDocument();
    expect(field).toHaveAttribute('aria-invalid', 'true');

    // Shift + Enter starts a new line instead of sending.
    await user.type(field, '第一行{Shift>}{Enter}{/Shift}第二行');
    expect(field).toHaveValue('第一行\n第二行');
    expect(within(panel).queryByText('请先写下要让 AI 助手做的修改。')).not.toBeInTheDocument();

    await user.clear(field);
    await user.paste('长'.repeat(2001));
    expect(within(panel).getByText('最多 2000 字，请精简后再发送。')).toBeInTheDocument();
    expect(within(panel).getByText('2001/2000')).toBeInTheDocument();
    await user.click(within(panel).getByRole('button', { name: '发送' }));
    expect(api.calls('POST', STEEL_REQUESTS)).toHaveLength(0);

    await user.clear(field);
    await user.type(field, '新增对象类型“炉次”{Enter}');
    const alert = await within(panel).findByRole('alert');
    expect(alert).toHaveTextContent('请求没有发出');
    expect(alert).toHaveTextContent('你没有执行此操作的权限，请联系平台管理员。');
    expect(field).toHaveValue('新增对象类型“炉次”');
  });

  it('tells viewers that asking needs the editor role and shows no input', async () => {
    const user = userEvent.setup();
    assistantServer({ user: userWithRole('viewer') });
    renderApp('/explore');

    const panel = await openAssistant(user);
    expect(await within(panel).findByText('需要编辑者角色')).toBeInTheDocument();
    expect(within(panel).getByText(/需要“编辑者”或更高的角色/)).toBeInTheDocument();
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: '发送' })).not.toBeInTheDocument();
  });

  it('points to the ontology page when there is no ontology yet', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/explore');

    const panel = await openAssistant(user);
    expect(await within(panel).findByText('还没有本体')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: '前往本体页' })).toHaveAttribute('href', '/ontology');
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('closes with Escape and gives focus back to the assistant button', async () => {
    const user = userEvent.setup();
    assistantServer();
    renderApp('/explore');

    const panel = await openAssistant(user);
    const field = await within(panel).findByRole('textbox', { name: FIELD });
    await waitFor(() => expect(field).toHaveFocus());

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'AI 助手' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: '打开 AI 助手' })).toHaveFocus();
  });
});
