import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { jsonResponse, problemResponse, renderApp, userWithRole } from '@/test/utils';

import type { Question } from './api';
import { answered, detailPath, listPath, qaServer, queued } from './test-fixtures';

const askTab = '/explore?tab=ask';
const proposalPath = `${detailPath}/gap-proposal`;
const editor = { 'GET /api/auth/me': () => userWithRole('editor') };
const missing: Question = {
  ...queued, status: 'unanswerable', gaps: {
    elements: [{ kind: 'entity_type', labelZh: '表面缺陷', description: '缺少缺陷类型。', near: [] }],
    bindings: [{ typeId: 'coil', label: '钢卷' }, { typeId: 'inspection', label: '检验' }],
  },
};
const metric: NonNullable<Question['gaps']>['elements'][number] = {
  kind: 'metric', labelZh: '成材率', description: '缺少成材率定义。', near: [],
};
function proposal(status: NonNullable<Question['gapProposal']>['status'], dropped = 0): Question {
  return { ...missing, gapProposal: {
    status, changeSetId: status === 'done' ? 'changes-1' : null, dropped,
    errorCode: status === 'failed' ? 'ai.invalid_output' : null,
  } };
}
const tick = () => act(() => vi.advanceTimersByTimeAsync(2000));
afterEach(() => { vi.useRealTimers(); });

it('submits once across repeated clicks and selection changes, then polls through running to review', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const items = [missing, { ...answered, id: 'other', question: '上周的产量？' }];
  let accept!: () => void;
  const api = qaServer(items, { ...editor, [`POST ${proposalPath}`]: async () => {
    await new Promise<void>((resolve) => { accept = resolve; });
    items[0] = proposal('queued');
    return jsonResponse(items[0], 202);
  } });
  const { queryClient } = renderApp(askTab);
  const button = await screen.findByRole('button', { name: '生成变更提议' });
  const binding = screen.getByRole('link', { name: '让 AI 建议绑定' });
  expect(button.compareDocumentPosition(binding) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  act(() => { button.click(); button.click(); });
  await waitFor(() => expect(api.calls('POST', proposalPath)).toHaveLength(1));
  expect(await screen.findByRole('button', { name: '正在生成变更提议' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: /上周的产量/ }));
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: new RegExp(missing.question) }));
  expect(await screen.findByRole('button', { name: '正在生成变更提议' })).toBeDisabled();
  act(() => { accept(); });
  await waitFor(() => expect(queryClient.isMutating()).toBe(0));
  items[0] = proposal('running');
  const before = api.calls('GET', detailPath).length;
  await tick();
  expect(api.calls('GET', detailPath).length).toBeGreaterThan(before);
  expect(screen.getByRole('button', { name: '正在生成变更提议' })).toBeDisabled();
  items[0] = proposal('done', 3);
  await tick();
  expect(await screen.findByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/changes-1');
  expect(screen.getByText('已生成变更提议')).toBeVisible();
  expect(screen.getByText('有 3 项未通过校验，已略去')).toBeVisible();
  const finished = api.calls('GET', detailPath).length;
  await tick();
  expect(api.calls('GET', detailPath)).toHaveLength(finished);
  expect(api.calls('POST', proposalPath)).toHaveLength(1);
});

it('resumes a running proposal from history after a transient detail error without submitting', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let recovered = false;
  const api = qaServer([proposal('running')], {
    ...editor, 'GET /api/qa/questions/:id': () => recovered ? proposal('done') : problemResponse(503, 'query.busy'),
  });
  renderApp(askTab);
  expect(await screen.findByText(i18n.t('errors.query.busy'))).toBeVisible();
  recovered = true;
  await tick();
  expect(await screen.findByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/changes-1');
  expect(api.calls('POST', proposalPath)).toHaveLength(0);
});

it('refreshes a previously viewed question when another session starts its proposal', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const items = [missing, { ...answered, id: 'other', question: '上周的产量？' }];
  const api = qaServer(items, editor);
  renderApp(askTab);
  expect(await screen.findByRole('button', { name: '生成变更提议' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: /上周的产量/ }));
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
  items[0] = proposal('running');
  fireEvent.click(screen.getByRole('button', { name: /哪些钢卷需要复检/ }));
  expect(await screen.findByRole('button', { name: '正在生成变更提议' })).toBeDisabled();
  items[0] = proposal('done');
  await tick();
  expect(await screen.findByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/changes-1');
  expect(api.calls('POST', proposalPath)).toHaveLength(0);
});

it('accepts an existing terminal proposal returned by an idempotent POST', async () => {
  const api = qaServer([missing], { ...editor, [`POST ${proposalPath}`]: () => jsonResponse(proposal('done'), 200) });
  renderApp(askTab);
  fireEvent.click(await screen.findByRole('button', { name: '生成变更提议' }));
  expect(await screen.findByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/changes-1');
  expect(screen.queryByText(/未通过校验/)).toBeNull();
  expect(screen.queryByRole('button', { name: '生成变更提议' })).toBeNull();
  expect(api.calls('POST', proposalPath)).toHaveLength(1);
});

it('recovers the accepted proposal from detail when its POST response is lost', async () => {
  const items = [missing];
  const api = qaServer(items, { ...editor, [`POST ${proposalPath}`]: () => {
    items[0] = proposal('done');
    throw new TypeError('Connection lost');
  } });
  renderApp(askTab);
  fireEvent.click(await screen.findByRole('button', { name: '生成变更提议' }));
  expect(await screen.findByRole('link', { name: '去审核' })).toHaveAttribute('href', '/review/changes-1');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(api.calls('POST', proposalPath)).toHaveLength(1);
});

it.each([['empty', 'qa.gapEmpty'], ['failed', 'qa.errors.ai.invalid_output']] as const)(
  'shows the localized %s result without submitting again', async (status, key) => {
    qaServer([proposal(status)], editor);
    renderApp(askTab);
    expect(await screen.findByText(i18n.t(key))).toBeVisible();
    expect(screen.queryByRole('button', { name: /生成变更提议|重试/ })).toBeNull();
    expect(screen.queryByRole('link', { name: '去审核' })).toBeNull();
  },
);

it('links a binding-only gap to the data page with the ontology and comma-separated type ids', async () => {
  qaServer([{ ...missing, gaps: { elements: [], bindings: missing.gaps!.bindings } }], editor);
  renderApp(askTab);
  const link = await screen.findByRole('link', { name: '让 AI 建议绑定' });
  const url = new URL(link.getAttribute('href')!, window.location.origin);
  expect(url.pathname).toBe('/data');
  expect(Object.fromEntries(url.searchParams)).toEqual({ ontologyId: missing.ontologyId, typeIds: 'coil,inspection' });
  expect(screen.queryByRole('button', { name: '生成变更提议' })).toBeNull();
});

it.each([false, true])('links to manual metric creation and offers AI only for other elements (mixed=%s)', async (mixed) => {
  const elements = [...(mixed ? missing.gaps!.elements : []), metric];
  qaServer([{ ...missing, gaps: { elements, bindings: [] } }], editor);
  renderApp(askTab);
  const link = await screen.findByRole('link', { name: '新建指标' });
  expect(link).toHaveAttribute('href', `/ontology?ontology=${missing.ontologyId}&view=list`);
  expect(screen.getByText(metric.description)).toBeVisible();
  expect(!!screen.queryByRole('button', { name: '生成变更提议' })).toBe(mixed);
  expect(screen.queryByRole('link', { name: '让 AI 建议绑定' })).toBeNull();
});

it('lets a viewer ask the same question again while hiding all gap actions', async () => {
  const previous: Question = { ...missing, id: 'old', askedBy: userWithRole('editor'),
    gaps: { elements: [...missing.gaps!.elements, metric], bindings: missing.gaps!.bindings } };
  const api = qaServer([previous], { 'GET /api/qa/questions/:id': ({ params }) => params.id === previous.id ? previous : answered });
  renderApp(askTab);
  const again = await screen.findByRole('button', { name: '再问一次' });
  expect(screen.queryByRole('button', { name: '生成变更提议' })).toBeNull();
  for (const name of ['让 AI 建议绑定', '去审核', '新建指标']) expect(screen.queryByRole('link', { name })).toBeNull();
  fireEvent.click(again);
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
  expect(api.calls('POST', listPath).map((request) => request.body)).toEqual([{ question: previous.question }]);
  expect(api.calls('POST', `/api/qa/questions/${previous.id}/gap-proposal`)).toHaveLength(0);
});
