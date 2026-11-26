import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { problemResponse, renderApp } from '@/test/utils';

import { answered, detailPath, listPath, qaServer, queued } from './test-fixtures';

const askTab = '/explore?tab=ask';
const input = () => screen.findByRole('textbox', { name: i18n.t('qa.question') });
const ask = () => screen.getByRole('button', { name: i18n.t('qa.ask') });
const tick = () => act(() => vi.advanceTimersByTimeAsync(2000));
afterEach(() => { vi.useRealTimers(); });

it('offers an example for empty history and accepts at most 500 characters', async () => {
  const api = qaServer();
  const user = userEvent.setup();
  renderApp(askTab);
  const field = await input();
  expect(ask()).toBeDisabled();
  await user.type(field, '   ');
  expect(ask()).toBeDisabled();
  expect(screen.getByText(i18n.t('qa.questionLimit'))).toBeVisible();
  expect(screen.getByText(i18n.t('qa.dataNotice'))).toBeVisible();
  expect(await screen.findByText(i18n.t('qa.tryAsking'))).toBeVisible();
  expect(screen.getByText(i18n.t('qa.selectQuestion'))).toBeVisible();
  await user.click(screen.getByRole('button', { name: i18n.t('qa.example') }));
  expect(field).toHaveValue(i18n.t('qa.example'));
  await user.clear(field);
  await user.paste('卷'.repeat(501));
  expect(field).toHaveValue('卷'.repeat(500));
  await user.clear(field);
  await user.paste('🧪'.repeat(501));
  expect(field).toHaveValue('🧪'.repeat(500));
  expect(ask()).toBeEnabled();
  expect(api.calls('POST', listPath)).toHaveLength(0);
});

it('submits once, refreshes history, polls the three stages and stops at an answer', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let accept!: () => void;
  const items: (typeof queued)[] = [];
  const api = qaServer(items, {
    [`POST ${listPath}`]: async () => {
      await new Promise<void>((resolve) => { accept = resolve; });
      items.unshift(queued);
      return queued;
    },
  });
  renderApp(askTab);
  const field = await input();
  await screen.findByText(i18n.t('qa.tryAsking'));
  fireEvent.change(field, { target: { value: `  ${queued.question}  ` } });
  fireEvent.click(ask());
  await waitFor(() => expect(api.calls('POST', listPath)).toHaveLength(1));
  expect(ask()).toBeDisabled();
  expect(api.calls('POST', listPath)[0]?.body).toEqual({ question: queued.question });
  act(() => { accept(); });
  const stages = await screen.findByRole('list', { name: i18n.t('assistant.progress.label') });
  expect(stages).toHaveTextContent(/计划.*查询.*回答/);
  expect(screen.getAllByText(i18n.t('qa.queued')).length).toBeGreaterThan(0);
  await waitFor(() => expect(api.calls('GET', listPath)).toHaveLength(2));
  for (const [step, label] of [['check', '计划'], ['query', '查询'], ['answer', '回答']] as const) {
    items[0] = { ...queued, status: 'running', step };
    await tick();
    await waitFor(() => expect(within(stages).getByText(label).closest('li')).toHaveAttribute('aria-current', 'step'));
  }
  items[0] = answered;
  await tick();
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
  expect(stages).not.toBeInTheDocument();
  await waitFor(() => expect(api.calls('GET', listPath)).toHaveLength(3));
  expect(screen.getByRole('button', { name: /哪些钢卷需要复检.*已回答/ })).toBeVisible();
  const count = api.calls('GET', detailPath).length;
  await tick();
  expect(api.calls('GET', detailPath)).toHaveLength(count);
});

it('opens a history item and resumes polling the newest on return', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const items = [queued, { ...answered, id: 'older', question: '上周的产量？' }];
  const release = { id: 'release-3', version: 3 };
  const api = qaServer(items, {
    'GET /api/ontologies/:id/metrics': () => ({ release, items: [] }),
    'GET /api/ontologies/:id/objects/types': () => ({ release, items: [] }),
  });
  renderApp(askTab);
  expect(await screen.findByRole('heading', { name: queued.question })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /上周的产量/ }));
  expect(await screen.findByRole('heading', { name: '上周的产量？' })).toBeVisible();
  fireEvent.click(screen.getByRole('tab', { name: '指标与规则' }));
  await within(await screen.findByRole('tabpanel', { name: '指标与规则' })).findByRole('heading', { name: '指标' });
  const before = api.calls('GET', detailPath).length;
  await tick();
  expect(api.calls('GET', detailPath)).toHaveLength(before);
  fireEvent.click(screen.getByRole('tab', { name: '问答' }));
  expect(await screen.findByRole('heading', { name: queued.question })).toBeVisible();
  items[0] = answered;
  await tick();
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
});

it('lets a viewer ask, read both kinds of gap and see no follow-up actions', async () => {
  const missing = { ...queued, status: 'unanswerable' as const, gaps: {
    elements: [{ kind: 'property' as const, labelZh: '复检标记', description: '尚未定义复检状态。', near: [] }],
    bindings: [{ typeId: 'coil', label: '钢卷' }],
  } };
  const api = qaServer([], { 'GET /api/qa/questions/:id': () => missing });
  renderApp(askTab);
  fireEvent.change(await input(), { target: { value: queued.question } });
  fireEvent.click(ask());
  expect(await screen.findByText(i18n.t('qa.unanswerable'))).toBeVisible();
  expect(screen.getByText('复检标记')).toBeVisible();
  expect(screen.getByText('尚未定义复检状态。')).toBeVisible();
  expect(screen.getByText('钢卷')).toBeVisible();
  expect(screen.queryByRole('button', { name: /生成变更提议|去绑定数据/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /生成变更提议|去绑定数据/ })).toBeNull();
  expect(api.calls('POST', listPath)).toHaveLength(1);
  expect(api.calls('GET', listPath)[0]?.query.get('askedBy')).toBe('me');
  expect(api.calls('GET', listPath)[0]?.query.has('limit')).toBe(false);
});

it('retries a failed question as a new question with identical text', async () => {
  const failed = { ...queued, id: 'old', status: 'failed' as const, errorCode: 'qa.invalid_plan' };
  const api = qaServer([failed], { 'GET /api/qa/questions/:id': ({ params }) => params.id === failed.id ? failed : answered });
  renderApp(askTab);
  expect(await screen.findByText(i18n.t('qa.errors.qa.invalid_plan'))).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: i18n.t('qa.retry') }));
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
  expect(api.calls('POST', listPath).map((r) => r.body)).toEqual([{ question: failed.question }]);
  expect(screen.getByRole('button', { pressed: true, name: /哪些钢卷需要复检/ })).toBeVisible();
});

it.each(['elements', 'bindings'] as const)('shows only the populated gap list for %s', async (kind) => {
  qaServer([{ ...queued, status: 'unanswerable', gaps: {
    elements: kind === 'elements' ? [{ kind: 'property', labelZh: '复检标记', description: '', near: [] }] : [],
    bindings: kind === 'bindings' ? [{ typeId: 'coil', label: '钢卷' }] : [],
  } }]);
  renderApp(askTab);
  await screen.findByText(i18n.t('qa.unanswerable'));
  const elementHeading = screen.queryByRole('heading', { name: i18n.t('qa.missingElements') });
  const bindingHeading = screen.queryByRole('heading', { name: i18n.t('qa.missingBindings') });
  expect(kind === 'elements' ? elementHeading : bindingHeading).toBeVisible();
  expect(kind === 'elements' ? bindingHeading : elementHeading).toBeNull();
});

it('resumes an active detail after a transient polling error', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let recovered = false;
  qaServer([queued], { 'GET /api/qa/questions/:id': () => recovered ? answered : problemResponse(503, 'query.busy') });
  renderApp(askTab);
  expect(await screen.findByText(i18n.t('errors.query.busy'))).toBeVisible();
  recovered = true;
  await tick();
  expect(await screen.findByText(answered.answer!.text!)).toBeVisible();
});
